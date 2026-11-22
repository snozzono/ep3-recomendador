import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import crear_app
from conftest import N_PRODUCTOS, N_USUARIOS

INTERACCION_VALIDA = {
    "usuario": 3,
    "producto": 17,
    "rating": 4.5,
    "timestamp": "2026-11-21T10:00:00Z",
}


def test_salud_responde_ok(client):
    r = client.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok"}


def test_recomendar_usuario_valido_devuelve_estructura(client):
    r = client.get("/recomendar", params={"usuario": 3, "n": 5})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["usuario"] == 3
    assert cuerpo["modelo"] == "factorizacion-npz"
    assert len(cuerpo["recomendaciones"]) == 5
    assert all(isinstance(p, int) and 0 <= p < N_PRODUCTOS for p in cuerpo["recomendaciones"])


def test_recomendar_n_por_defecto_es_5(client):
    r = client.get("/recomendar", params={"usuario": 0})
    assert r.status_code == 200
    assert len(r.json()["recomendaciones"]) == 5


def test_recomendar_usuario_fuera_de_rango_404(client):
    r = client.get("/recomendar", params={"usuario": N_USUARIOS, "n": 5})
    assert r.status_code == 404
    assert "no existe" in r.json()["detail"]


def test_recomendar_usuario_negativo_404(client):
    r = client.get("/recomendar", params={"usuario": -1})
    assert r.status_code == 404


@pytest.mark.parametrize("n", [0, -3, 101, "abc"])
def test_recomendar_n_invalido_422(client, n):
    r = client.get("/recomendar", params={"usuario": 1, "n": n})
    assert r.status_code == 422


def test_recomendar_sin_productos_repetidos(client):
    recs = client.get("/recomendar", params={"usuario": 2, "n": 20}).json()["recomendaciones"]
    assert len(recs) == len(set(recs)) == 20


def test_recomendar_n_menor_que_total_devuelve_los_mejores(client, recomendador_directo):
    recs = client.get("/recomendar", params={"usuario": 4, "n": 3}).json()["recomendaciones"]
    puntajes = recomendador_directo.U[4] @ recomendador_directo.V.T
    esperados = list(np.argsort(-puntajes)[:3])
    assert recs == [int(p) for p in esperados]


def test_recomendar_n_mayor_que_catalogo_no_falla(client):
    recs = client.get("/recomendar", params={"usuario": 0, "n": 100}).json()["recomendaciones"]
    assert len(recs) == N_PRODUCTOS


def test_post_interaccion_valida_202_y_publica(client, publicador):
    r = client.post("/interacciones", json=INTERACCION_VALIDA)
    assert r.status_code == 202
    assert r.json() == {"estado": "aceptado"}
    assert len(publicador.mensajes) == 1
    mensaje = publicador.mensajes[0]
    assert mensaje["usuario"] == 3
    assert mensaje["producto"] == 17
    assert mensaje["rating"] == 4.5


@pytest.mark.parametrize("rating", [0, 0.5, 5.1, 6])
def test_post_rating_fuera_de_rango_422(client, publicador, rating):
    r = client.post("/interacciones", json={**INTERACCION_VALIDA, "rating": rating})
    assert r.status_code == 422
    assert publicador.mensajes == []


def test_post_sin_campos_obligatorios_422(client, publicador):
    r = client.post("/interacciones", json={"usuario": 1})
    assert r.status_code == 422
    assert publicador.mensajes == []


def test_post_timestamp_invalido_422(client):
    r = client.post("/interacciones", json={**INTERACCION_VALIDA, "timestamp": "ayer"})
    assert r.status_code == 422


def test_post_con_broker_caido_responde_503(client, publicador):
    publicador.fallar = True
    r = client.post("/interacciones", json=INTERACCION_VALIDA)
    assert r.status_code == 503


def test_swagger_y_openapi_disponibles(client):
    assert client.get("/docs").status_code == 200
    esquema = client.get("/openapi.json").json()
    assert {"/recomendar", "/interacciones", "/salud"} <= set(esquema["paths"])


def test_fallback_sin_modelo_arranca_con_popularidad(monkeypatch, tmp_path, publicador):
    eventos = tmp_path / "eventos.jsonl"
    filas = [
        {"usuario": 1, "producto": 7, "rating": 5, "timestamp": "2026-01-01T00:00:00Z"},
        {"usuario": 2, "producto": 7, "rating": 4, "timestamp": "2026-01-01T00:00:00Z"},
        {"usuario": 2, "producto": 9, "rating": 3, "timestamp": "2026-01-01T00:00:00Z"},
    ]
    eventos.write_text("\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "no_existe.npz"))
    monkeypatch.setenv("EVENTOS_PATH", str(eventos))

    client = TestClient(crear_app(publicador=publicador))
    r = client.get("/recomendar", params={"usuario": 999, "n": 2})
    assert r.status_code == 200
    assert r.json()["modelo"] == "popularidad-fallback"
    assert r.json()["recomendaciones"] == [7, 9]
    assert client.get("/recomendar", params={"usuario": -1}).status_code == 404


def test_modelo_path_por_variable_de_entorno(monkeypatch, modelo_sintetico_path, publicador):
    monkeypatch.setenv("MODEL_PATH", str(modelo_sintetico_path))
    client = TestClient(crear_app(publicador=publicador))
    r = client.get("/recomendar", params={"usuario": 0})
    assert r.json()["modelo"] == "factorizacion-npz"
