import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from mensajeria import PublicadorRabbit
from modelo import UsuarioNoEncontrado, cargar_recomendador
from schemas import AceptadoOut, InteraccionIn, RecomendacionOut, SaludOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

# Carpeta padre de servicio/: en Docker (/app) resuelve a /modelo, donde compose monta ./modelo.
MODEL_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "modelo" / "modelo.npz"
EVENTOS_PATH_DEFAULT = Path(__file__).resolve().parent / "eventos.jsonl"
RABBITMQ_URL_DEFAULT = "amqp://guest:guest@localhost:5672/"


def crear_app(recomendador=None, publicador=None) -> FastAPI:
    if recomendador is None:
        recomendador = cargar_recomendador(
            os.getenv("MODEL_PATH", MODEL_PATH_DEFAULT),
            os.getenv("EVENTOS_PATH", EVENTOS_PATH_DEFAULT),
        )
    if publicador is None:
        publicador = PublicadorRabbit(os.getenv("RABBITMQ_URL", RABBITMQ_URL_DEFAULT))

    app = FastAPI(
        title="Servicio de recomendación de productos",
        version="1.0.0",
        description="Recomendaciones por usuario y registro de interacciones publicadas en RabbitMQ.",
    )

    @app.get("/salud", response_model=SaludOut, tags=["sistema"])
    def salud():
        return {"estado": "ok"}

    @app.get(
        "/recomendar",
        response_model=RecomendacionOut,
        tags=["recomendaciones"],
        responses={404: {"description": "Usuario no existe"}, 422: {"description": "Parámetros inválidos"}},
    )
    def recomendar(
        usuario: int = Query(..., description="Id del usuario (índice en la matriz U)"),
        n: int = Query(5, ge=1, le=100, description="Cantidad de productos a recomendar"),
    ):
        try:
            recomendaciones = recomendador.recomendar(usuario, n)
        except UsuarioNoEncontrado:
            raise HTTPException(status_code=404, detail=f"El usuario {usuario} no existe")
        return {"usuario": usuario, "recomendaciones": recomendaciones, "modelo": recomendador.nombre}

    @app.post(
        "/interacciones",
        status_code=202,
        response_model=AceptadoOut,
        tags=["interacciones"],
        responses={422: {"description": "Evento inválido"}, 503: {"description": "RabbitMQ no disponible"}},
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
