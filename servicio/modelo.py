import json
import logging
from collections import Counter
from pathlib import Path

import numpy as np

log = logging.getLogger("modelo")

NOMBRE_FACTORIZACION = "factorizacion-npz"
NOMBRE_POPULARIDAD = "popularidad-fallback"


class UsuarioNoEncontrado(Exception):
    pass


class Recomendador:
    """Factorización: puntaje[u, p] = U[u] @ V[p]. Espera claves U (usuarios x k) y V (productos x k) en el .npz."""

    nombre = NOMBRE_FACTORIZACION

    def __init__(self, U: np.ndarray, V: np.ndarray):
        if U.ndim != 2 or V.ndim != 2 or U.shape[1] != V.shape[1]:
            raise ValueError(f"Forma inválida: U {U.shape}, V {V.shape}")
        self.U = U
        self.V = V

    @property
    def n_usuarios(self) -> int:
        return self.U.shape[0]

    @property
    def n_productos(self) -> int:
        return self.V.shape[0]

    def existe_usuario(self, usuario: int) -> bool:
        return 0 <= usuario < self.n_usuarios

    def recomendar(self, usuario: int, n: int) -> list[int]:
        if not self.existe_usuario(usuario):
            raise UsuarioNoEncontrado(usuario)
        if n < 1:
            raise ValueError("n debe ser >= 1")
        puntajes = self.U[usuario] @ self.V.T
        n = min(n, self.n_productos)
        top = np.argpartition(-puntajes, n - 1)[:n]
        top = top[np.argsort(-puntajes[top], kind="stable")]
        return [int(p) for p in top]


class RecomendadorPopularidad:
    """Respaldo sin modelo entrenado: recomienda los productos más valorados según eventos.jsonl.

    No personaliza: todos los usuarios reciben el mismo ranking. Cuenta interacciones por producto
    (el consumidor escribe una línea por evento) y desempata por id de producto. Si no hay eventos,
    el catálogo queda vacío y las recomendaciones son [].
    """

    nombre = NOMBRE_POPULARIDAD

    def __init__(self, conteos: Counter):
        orden = sorted(conteos.items(), key=lambda kv: (-kv[1], kv[0]))
        self.productos = [int(p) for p, _ in orden]

    @classmethod
    def desde_eventos(cls, ruta: Path) -> "RecomendadorPopularidad":
        conteos: Counter = Counter()
        if Path(ruta).is_file():
            with open(ruta, encoding="utf-8") as f:
                for linea in f:
                    if linea.strip():
                        conteos[int(json.loads(linea)["producto"])] += 1
        else:
            log.warning("No existe %s; el respaldo por popularidad arranca sin catálogo", ruta)
        return cls(conteos)

    @property
    def n_productos(self) -> int:
        return len(self.productos)

    def existe_usuario(self, usuario: int) -> bool:
        return usuario >= 0

    def recomendar(self, usuario: int, n: int) -> list[int]:
        if not self.existe_usuario(usuario):
            raise UsuarioNoEncontrado(usuario)
        return self.productos[:n]


def cargar_recomendador(model_path, eventos_path):
    ruta = Path(model_path)
    if ruta.is_file():
        with np.load(ruta) as datos:
            recomendador = Recomendador(datos["U"], datos["V"])
        log.info("Modelo cargado desde %s (%d usuarios, %d productos)", ruta, recomendador.n_usuarios, recomendador.n_productos)
        return recomendador
    log.warning("MODEL_PATH=%s no existe; se usa el modelo de respaldo por popularidad", ruta)
    return RecomendadorPopularidad.desde_eventos(eventos_path)
