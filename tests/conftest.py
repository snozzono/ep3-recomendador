from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import crear_app
from modelo import Recomendador, cargar_recomendador

TESTS = Path(__file__).resolve().parent
MODELO_SINTETICO = TESTS / "modelo_sintetico.npz"
N_USUARIOS = 20
N_PRODUCTOS = 50
K = 8


def generar_modelo_sintetico(ruta: Path) -> None:
    rng = np.random.default_rng(42)
    U = rng.normal(size=(N_USUARIOS, K)).astype(np.float32)
    V = rng.normal(size=(N_PRODUCTOS, K)).astype(np.float32)
    np.savez(ruta, U=U, V=V)


if not MODELO_SINTETICO.exists():
    generar_modelo_sintetico(MODELO_SINTETICO)


class PublicadorFalso:
    def __init__(self):
        self.mensajes = []
        self.fallar = False

    def publicar(self, mensaje: dict) -> None:
        if self.fallar:
            raise ConnectionError("broker caído (simulado)")
        self.mensajes.append(mensaje)


@pytest.fixture
def publicador():
    return PublicadorFalso()


@pytest.fixture
def recomendador():
    return cargar_recomendador(MODELO_SINTETICO, eventos_path=TESTS / "no_existe.jsonl")


@pytest.fixture
def client(recomendador, publicador):
    return TestClient(crear_app(recomendador=recomendador, publicador=publicador))


@pytest.fixture
def modelo_sintetico_path():
    return MODELO_SINTETICO


@pytest.fixture
def recomendador_directo():
    with np.load(MODELO_SINTETICO) as datos:
        return Recomendador(datos["U"], datos["V"])
