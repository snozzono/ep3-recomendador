import hmac
import logging
import math
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader

from mensajeria import PublicadorRabbit
from modelo import UsuarioNoEncontrado, cargar_recomendador
from schemas import AceptadoOut, InteraccionIn, RecomendacionOut, SaludOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

# Carpeta padre de servicio/: en Docker (/app) resuelve a /modelo, donde compose monta ./modelo.
MODEL_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "modelo" / "modelo.npz"
EVENTOS_PATH_DEFAULT = Path(__file__).resolve().parent / "eventos.jsonl"
STATIC_DIR = Path(__file__).resolve().parent / "static"
RABBITMQ_URL_DEFAULT = "amqp://guest:guest@localhost:5672/"
RATE_LIMIT_DEFAULT = 60


class LimitadorIP:
    """Ventana deslizante en memoria: como máximo `limite` peticiones por IP en `ventana` segundos."""

    def __init__(self, limite: int, ventana: float = 60.0):
        self.limite = limite
        self.ventana = ventana
        self._peticiones: dict[str, deque] = defaultdict(deque)
        self._cerrojo = threading.Lock()

    def permitir(self, ip: str) -> float:
        """Registra la petición. Devuelve 0 si entra; si no, los segundos hasta liberar un cupo."""
        ahora = time.monotonic()
        with self._cerrojo:
            historial = self._peticiones[ip]
            while historial and ahora - historial[0] >= self.ventana:
                historial.popleft()
            if len(historial) >= self.limite:
                return historial[0] + self.ventana - ahora
            historial.append(ahora)
            return 0.0


def crear_app(recomendador=None, publicador=None, api_key=None, limite_por_minuto=None) -> FastAPI:
    if recomendador is None:
        recomendador = cargar_recomendador(
            os.getenv("MODEL_PATH", MODEL_PATH_DEFAULT),
            os.getenv("EVENTOS_PATH", EVENTOS_PATH_DEFAULT),
        )
    if publicador is None:
        publicador = PublicadorRabbit(os.getenv("RABBITMQ_URL", RABBITMQ_URL_DEFAULT))
    clave_configurada = api_key if api_key is not None else os.getenv("API_KEY", "")
    if limite_por_minuto is None:
        limite_por_minuto = int(os.getenv("RATE_LIMIT_POR_MINUTO", RATE_LIMIT_DEFAULT))
    limitador = LimitadorIP(limite_por_minuto)

    app = FastAPI(
        title="Servicio de recomendación de productos",
        version="1.0.0",
        description=(
            "Recomendaciones por usuario y registro de interacciones publicadas en RabbitMQ. "
            "/recomendar e /interacciones requieren la cabecera X-API-Key."
        ),
    )

    clave_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Clave de acceso a la API")

    def exigir_clave(clave: str | None = Security(clave_header)):
        if not clave_configurada:
            raise HTTPException(status_code=500, detail="API_KEY no está configurada en el servidor")
        if clave is None or not hmac.compare_digest(clave.encode("utf-8"), clave_configurada.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Clave API ausente o incorrecta")

    @app.middleware("http")
    async def limitar_por_ip(request: Request, call_next):
        ip = request.client.host if request.client else "desconocida"
        espera = limitador.permitir(ip)
        if espera > 0:
            return JSONResponse(
                status_code=429,
                content={"detail": "Demasiadas solicitudes; intente más tarde"},
                headers={"Retry-After": str(math.ceil(espera))},
            )
        return await call_next(request)

    @app.get("/salud", response_model=SaludOut, tags=["sistema"])
    def salud():
        return {"estado": "ok"}

    @app.get(
        "/recomendar",
        response_model=RecomendacionOut,
        tags=["recomendaciones"],
        dependencies=[Depends(exigir_clave)],
        responses={
            401: {"description": "Clave API ausente o incorrecta"},
            404: {"description": "Usuario no existe"},
            422: {"description": "Parámetros inválidos"},
            429: {"description": "Límite de peticiones por IP excedido"},
        },
    )
    def recomendar(
        usuario: str = Query(..., min_length=1, max_length=100, description="user_id del usuario"),
        n: int = Query(5, ge=1, le=100, description="Cantidad de productos a recomendar"),
    ):
        try:
            recomendaciones = recomendador.recomendar(usuario, n)
        except UsuarioNoEncontrado:
            raise HTTPException(status_code=404, detail=f"El usuario {usuario} no existe")
        return {"usuario": usuario, "recomendaciones": recomendaciones, "modelo": recomendador.nombre}

    @app.get("/dashboard", include_in_schema=False)
    def dashboard():
        return FileResponse(STATIC_DIR / "dashboard.html")

    @app.post(
        "/interacciones",
        status_code=202,
        response_model=AceptadoOut,
        tags=["interacciones"],
        dependencies=[Depends(exigir_clave)],
        responses={
            401: {"description": "Clave API ausente o incorrecta"},
            422: {"description": "Evento inválido"},
            429: {"description": "Límite de peticiones por IP excedido"},
            503: {"description": "RabbitMQ no disponible"},
        },
    )
    def registrar_interaccion(evento: InteraccionIn):
        try:
            publicador.publicar(evento.model_dump(mode="json"))
        except Exception:
            log.exception("No se pudo publicar la interacción del usuario %s", evento.usuario)
            raise HTTPException(status_code=503, detail="No se pudo registrar la interacción; intente más tarde")
        return {"estado": "aceptado"}

    return app


app = crear_app()
