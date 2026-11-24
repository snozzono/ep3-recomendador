import os
import random
from datetime import datetime, timezone
from pathlib import Path

from locust import HttpUser, between, task

MUESTRAS = Path(__file__).resolve().parent
CABECERAS = {"X-API-Key": os.environ.get("API_KEY", "cambiar-esta-clave")}


def _leer_muestra(nombre: str) -> list[str]:
    with open(MUESTRAS / nombre, encoding="utf-8") as f:
        return [linea.strip() for linea in f if linea.strip()]


USUARIOS = _leer_muestra("usuarios_muestra.txt")
PRODUCTOS = _leer_muestra("productos_muestra.txt")


class UsuarioTienda(HttpUser):
    wait_time = between(0.1, 1.0)

    @task(4)
    def recomendar(self):
        usuario = random.choice(USUARIOS)
        with self.client.get(
            "/recomendar",
            params={"usuario": usuario, "n": 5},
            headers=CABECERAS,
            name="/recomendar",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")

    @task(1)
    def registrar_interaccion(self):
        evento = {
            "usuario": random.choice(USUARIOS),
            "producto": random.choice(PRODUCTOS),
            "rating": random.randint(1, 5),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self.client.post(
            "/interacciones",
            json=evento,
            headers=CABECERAS,
            name="/interacciones",
            catch_response=True,
        ) as r:
            if r.status_code != 202:
                r.failure(f"status {r.status_code}")
