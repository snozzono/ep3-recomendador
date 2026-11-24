import json
import logging
from collections import Counter
from pathlib import Path

import numpy as np

log = logging.getLogger("modelo")

NOMBRE_FACTORIZACION = "svd-als"
NOMBRE_POPULARIDAD = "popularidad-fallback"


class UsuarioNoEncontrado(Exception):
    pass


class Recomendador:
    """Factorización: puntaje[p] = V[p] @ U[u], sin productos ya vistos por el usuario.

    user_ids[i] es el user_id de la fila i de U; item_ids[j] el parent_asin de la fila j de V.
    vistos_ptr/vistos son la matriz dispersa CSR usuario x producto del entrenamiento: los productos
    de la fila u están en vistos[vistos_ptr[u]:vistos_ptr[u+1]].
    """

    nombre = NOMBRE_FACTORIZACION

    def __init__(
        self,
        U: np.ndarray,
        V: np.ndarray,
        vistos_ptr: np.ndarray,
        vistos: np.ndarray,
        user_ids: np.ndarray,
        item_ids: np.ndarray,
    ):
        if U.ndim != 2 or V.ndim != 2 or U.shape[1] != V.shape[1]:
            raise ValueError(f"Forma inválida: U {U.shape}, V {V.shape}")
        if len(vistos_ptr) != U.shape[0] + 1:
            raise ValueError(f"vistos_ptr debe tener {U.shape[0] + 1} entradas, tiene {len(vistos_ptr)}")
        if len(user_ids) != U.shape[0] or len(item_ids) != V.shape[0]:
            raise ValueError("user_ids/item_ids no coinciden con las filas de U/V")
        self.U = U
        self.V = V
        self.vistos_ptr = vistos_ptr
        self.vistos = vistos
        self.item_ids = np.asarray(item_ids, dtype=str)
        self._fila_usuario = {str(u): i for i, u in enumerate(np.asarray(user_ids, dtype=str).tolist())}

    @property
    def n_usuarios(self) -> int:
        return self.U.shape[0]

    @property
    def n_productos(self) -> int:
        return self.V.shape[0]

    def existe_usuario(self, usuario: str) -> bool:
        return usuario in self._fila_usuario

    def productos_vistos(self, usuario: str) -> np.ndarray:
        fila = self._fila_usuario[usuario]
        return self.vistos[self.vistos_ptr[fila]:self.vistos_ptr[fila + 1]]

    def recomendar(self, usuario: str, n: int) -> list[dict]:
        if not self.existe_usuario(usuario):
            raise UsuarioNoEncontrado(usuario)
        if n < 1:
            raise ValueError("n debe ser >= 1")
        fila = self._fila_usuario[usuario]
        puntajes = self.V @ self.U[fila]
        vistos = self.productos_vistos(usuario)
        puntajes[vistos] = -np.inf
        disponibles = np.flatnonzero(np.isfinite(puntajes))
        n = min(n, disponibles.size)
        if n == 0:
            return []
        top = disponibles[np.argpartition(-puntajes[disponibles], n - 1)[:n]]
        top = top[np.argsort(-puntajes[top], kind="stable")]
        return [{"parent_asin": str(self.item_ids[j]), "score": float(puntajes[j])} for j in top]


class RecomendadorPopularidad:
    """Respaldo sin modelo entrenado: recomienda los productos más valorados según eventos.jsonl.

    No personaliza: todos los usuarios reciben el mismo ranking. Cuenta interacciones por producto
    (el consumidor escribe una línea por evento) y desempata por parent_asin. Si no hay eventos,
    el catálogo queda vacío y las recomendaciones son [].
    """

    nombre = NOMBRE_POPULARIDAD

    def __init__(self, conteos: Counter):
        orden = sorted(conteos.items(), key=lambda kv: (-kv[1], kv[0]))
        self.productos = [(str(p), float(c)) for p, c in orden]

    @classmethod
    def desde_eventos(cls, ruta: Path) -> "RecomendadorPopularidad":
        conteos: Counter = Counter()
        if Path(ruta).is_file():
            with open(ruta, encoding="utf-8") as f:
                for linea in f:
                    if linea.strip():
                        conteos[str(json.loads(linea)["producto"])] += 1
        else:
            log.warning("No existe %s; el respaldo por popularidad arranca sin catálogo", ruta)
        return cls(conteos)

    @property
    def n_productos(self) -> int:
        return len(self.productos)

    def existe_usuario(self, usuario: str) -> bool:
        return True

    def recomendar(self, usuario: str, n: int) -> list[dict]:
        if not self.existe_usuario(usuario):
            raise UsuarioNoEncontrado(usuario)
        return [{"parent_asin": p, "score": c} for p, c in self.productos[:n]]


def cargar_recomendador(model_path, eventos_path):
    ruta = Path(model_path)
    if ruta.is_file():
        with np.load(ruta) as datos:
            recomendador = Recomendador(
                datos["U"],
                datos["V"],
                datos["vistos_ptr"],
                datos["vistos"],
                datos["user_ids"],
                datos["item_ids"],
            )
        log.info("Modelo cargado desde %s (%d usuarios, %d productos)", ruta, recomendador.n_usuarios, recomendador.n_productos)
        return recomendador
    log.warning("MODEL_PATH=%s no existe; se usa el modelo de respaldo por popularidad", ruta)
    return RecomendadorPopularidad.desde_eventos(eventos_path)
