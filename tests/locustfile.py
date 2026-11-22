import os
import random
from datetime import datetime, timezone

from locust import HttpUser, between, task

USUARIOS_MAX = int(os.getenv("USUARIOS_MAX", "1000"))
PRODUCTOS_MAX = int(os.getenv("PRODUCTOS_MAX", "1000"))


class UsuarioTienda(HttpUser):
    wait_time = between(0.1, 1.0)

    @task(4)
    def recomendar(self):
        usuario = random.randrange(USUARIOS_MAX)
        with self.client.get(
            "/recomendar",
            params={"usuario": usuario, "n": 5},
            name="/recomendar",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")

    @task(1)
    def registrar_interaccion(self):
        evento = {
            "usuario": random.randrange(USUARIOS_MAX),
            "producto": random.randrange(PRODUCTOS_MAX),
            "rating": random.randint(1, 5),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self.client.post(
            "/interacciones",
            json=evento,
            name="/interacciones",
            catch_response=True,
        ) as r:
            if r.status_code != 202:
                r.failure(f"status {r.status_code}")
