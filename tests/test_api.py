import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import crear_app
from conftest import CLAVE, N_PRODUCTOS, N_USUARIOS, N_VISTOS
from modelo import Recomendador

INTERACCION_VALIDA = {
    "usuario": "u3",
    "producto": "p17",
    "rating": 4.5,
    "timestamp": "2026-11-21T10:00:00Z",
}


def vistos_de(recomendador, usuario):
    return set(recomendador.item_ids[recomendador.productos_vistos(usuario)].tolist())


def test_salud_responde_ok(client):
    r = client.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok"}


def test_recomendar_sin_clave_401(client_sin_clave):
    r = client_sin_clave.get("/recomendar", params={"usuario": "u3", "n": 5})
    assert r.status_code == 401


def test_recomendar_clave_incorrecta_401(client_sin_clave):
    r = client_sin_clave.get("/recomendar", params={"usuario": "u3", "n": 5}, headers={"X-API-Key": "mala"})
    assert r.status_code == 401


def test_recomendar_con_clave_correcta_200(client_sin_clave):
    r = client_sin_clave.get("/recomendar", params={"usuario": "u3", "n": 5}, headers={"X-API-Key": CLAVE})
    assert r.status_code == 200


def test_interaccion_sin_clave_401_y_no_publica(client_sin_clave, publicador):
    r = client_sin_clave.post("/interacciones", json=INTERACCION_VALIDA)
    assert r.status_code == 401
    assert publicador.mensajes == []


def test_salud_docs_y_dashboard_sin_clave(client_sin_clave):
    assert client_sin_clave.get("/salud").status_code == 200
    assert client_sin_clave.get("/docs").status_code == 200
    assert client_sin_clave.get("/openapi.json").status_code == 200
    assert client_sin_clave.get("/dashboard").status_code == 200


def test_sin_clave_configurada_responde_500(recomendador, publicador):
    cliente = TestClient(crear_app(recomendador=recomendador, publicador=publicador, api_key=""))
    r = cliente.get("/recomendar", params={"usuario": "u3"}, headers={"X-API-Key": CLAVE})
    assert r.status_code == 500
    assert "API_KEY" in r.json()["detail"]


def test_rate_limit_responde_429_con_retry_after(recomendador, publicador):
    limite = 5
    cliente = TestClient(
        crear_app(recomendador=recomendador, publicador=publicador, api_key=CLAVE, limite_por_minuto=limite),
        headers={"X-API-Key": CLAVE},
    )
    for _ in range(limite):
        assert cliente.get("/recomendar", params={"usuario": "u3", "n": 1}).status_code == 200
    r = cliente.get("/recomendar", params={"usuario": "u3", "n": 1})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_rate_limit_cuenta_401_y_otras_rutas(recomendador, publicador):
    limite = 5
    cliente = TestClient(crear_app(recomendador=recomendador, publicador=publicador, api_key=CLAVE, limite_por_minuto=limite))
    assert cliente.get("/salud").status_code == 200
    assert cliente.get("/recomendar", params={"usuario": "u3", "n": 1}).status_code == 401
    for _ in range(limite - 2):
        assert cliente.get("/recomendar", params={"usuario": "u3", "n": 1}, headers={"X-API-Key": CLAVE}).status_code == 200
    assert cliente.get("/recomendar", params={"usuario": "u3", "n": 1}, headers={"X-API-Key": CLAVE}).status_code == 429


def test_recomendar_usuario_valido_devuelve_estructura(client, recomendador_directo):
    r = client.get("/recomendar", params={"usuario": "u3", "n": 5})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["usuario"] == "u3"
    assert cuerpo["modelo"] == "svd-als"
    assert len(cuerpo["recomendaciones"]) == 5
    catalogo = set(recomendador_directo.item_ids.tolist())
    for rec in cuerpo["recomendaciones"]:
        assert set(rec) == {"parent_asin", "score"}
        assert isinstance(rec["parent_asin"], str) and rec["parent_asin"] in catalogo
        assert isinstance(rec["score"], float)


def test_recomendar_scores_en_orden_descendente(client):
    scores = [rec["score"] for rec in client.get("/recomendar", params={"usuario": "u5", "n": 10}).json()["recomendaciones"]]
    assert scores == sorted(scores, reverse=True)


def test_recomendar_n_por_defecto_es_5(client):
    r = client.get("/recomendar", params={"usuario": "u0"})
    assert r.status_code == 200
    assert len(r.json()["recomendaciones"]) == 5


def test_recomendar_usuario_inexistente_404(client):
    r = client.get("/recomendar", params={"usuario": "u_no_existe", "n": 5})
    assert r.status_code == 404
    assert "no existe" in r.json()["detail"]


def test_recomendar_usuario_fuera_del_modelo_404(client):
    r = client.get("/recomendar", params={"usuario": f"u{N_USUARIOS}", "n": 5})
    assert r.status_code == 404


def test_recomendar_usuario_vacio_422(client):
    r = client.get("/recomendar", params={"usuario": "", "n": 5})
    assert r.status_code == 422


@pytest.mark.parametrize("n", [0, -3, 101, "abc"])
def test_recomendar_n_invalido_422(client, n):
    r = client.get("/recomendar", params={"usuario": "u1", "n": n})
    assert r.status_code == 422


def test_recomendar_sin_productos_repetidos(client):
    recs = client.get("/recomendar", params={"usuario": "u2", "n": 20}).json()["recomendaciones"]
    nombres = [rec["parent_asin"] for rec in recs]
    assert len(nombres) == len(set(nombres)) == 20


def test_recomendar_n_menor_que_total_devuelve_los_mejores(client, recomendador_directo):
    recs = client.get("/recomendar", params={"usuario": "u4", "n": 3}).json()["recomendaciones"]
    puntajes = recomendador_directo.V @ recomendador_directo.U[4]
    puntajes[recomendador_directo.productos_vistos("u4")] = -np.inf
    esperados = np.argsort(-puntajes)[:3]
    assert [rec["parent_asin"] for rec in recs] == [recomendador_directo.item_ids[j] for j in esperados]


def test_recomendar_n_mayor_que_catalogo_no_falla(client, recomendador_directo):
    recs = client.get("/recomendar", params={"usuario": "u0", "n": 100}).json()["recomendaciones"]
    assert len(recs) == N_PRODUCTOS - len(recomendador_directo.productos_vistos("u0"))


def json_estandar(texto):
    def rechazar(constante):
        raise ValueError(f"JSON no estándar: {constante}")

    return json.loads(texto, parse_constant=rechazar)


def test_recomendar_solo_scores_finitos_y_json_estandar(client):
    for usuario in [f"u{i}" for i in range(N_USUARIOS)]:
        r = client.get("/recomendar", params={"usuario": usuario, "n": 100})
        assert r.status_code == 200
        cuerpo = json_estandar(r.text)
        assert all(math.isfinite(rec["score"]) for rec in cuerpo["recomendaciones"])
        assert len(cuerpo["recomendaciones"]) == N_PRODUCTOS - N_VISTOS


def test_recomendar_con_pocos_no_vistos_omite_los_vistos(recomendador_directo, publicador):
    vistos = np.arange(N_PRODUCTOS - 2)
    recomendador = Recomendador(
        recomendador_directo.U,
        recomendador_directo.V,
        np.array([0, len(vistos)] + [len(vistos)] * (N_USUARIOS - 1), dtype=np.int64),
        vistos.astype(np.int32),
        np.array([f"u{i}" for i in range(N_USUARIOS)], dtype=str),
        recomendador_directo.item_ids,
    )
    cliente = TestClient(crear_app(recomendador=recomendador, publicador=publicador, api_key=CLAVE), headers={"X-API-Key": CLAVE})
    r = cliente.get("/recomendar", params={"usuario": "u0", "n": 10})
    assert r.status_code == 200
    recs = json_estandar(r.text)["recomendaciones"]
    assert len(recs) == 2
    assert all(math.isfinite(rec["score"]) for rec in recs)
    assert {rec["parent_asin"] for rec in recs} == {"p48", "p49"}


def test_recomendar_excluye_productos_vistos(client, recomendador_directo):
    for usuario in [f"u{i}" for i in range(N_USUARIOS)]:
        recs = client.get("/recomendar", params={"usuario": usuario, "n": 5}).json()["recomendaciones"]
        assert len(recs) == 5
        assert not vistos_de(recomendador_directo, usuario) & {rec["parent_asin"] for rec in recs}


def test_primer_recomendado_no_esta_en_vistos(client, recomendador_directo):
    for usuario in ["u0", "u7", "u13"]:
        primero = client.get("/recomendar", params={"usuario": usuario, "n": 1}).json()["recomendaciones"][0]
        assert primero["parent_asin"] not in vistos_de(recomendador_directo, usuario)


def test_recomendar_devuelve_n_no_vistos_si_hay_suficientes(client, recomendador_directo):
    recs = client.get("/recomendar", params={"usuario": "u7", "n": 20}).json()["recomendaciones"]
    assert len(recs) == 20
    assert not vistos_de(recomendador_directo, "u7") & {rec["parent_asin"] for rec in recs}


def test_post_interaccion_valida_202_y_publica(client, publicador):
    r = client.post("/interacciones", json=INTERACCION_VALIDA)
    assert r.status_code == 202
    assert r.json() == {"estado": "aceptado"}
    assert len(publicador.mensajes) == 1
    mensaje = publicador.mensajes[0]
    assert mensaje["usuario"] == "u3"
    assert mensaje["producto"] == "p17"
    assert mensaje["rating"] == 4.5


def test_post_producto_numerico_422(client, publicador):
    r = client.post("/interacciones", json={**INTERACCION_VALIDA, "producto": 17})
    assert r.status_code == 422
    assert publicador.mensajes == []


@pytest.mark.parametrize("rating", [0, 0.5, 5.1, 6])
def test_post_rating_fuera_de_rango_422(client, publicador, rating):
    r = client.post("/interacciones", json={**INTERACCION_VALIDA, "rating": rating})
    assert r.status_code == 422
    assert publicador.mensajes == []


def test_post_sin_campos_obligatorios_422(client, publicador):
    r = client.post("/interacciones", json={"usuario": "u1"})
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


def test_dashboard_sirve_html(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "/recomendar" in r.text


def test_dashboard_carga_metricas_y_carga_estaticas(client_sin_clave):
    html = client_sin_clave.get("/dashboard").text
    assert "/static/metricas.json" in html and "/static/carga.json" in html
    metricas = client_sin_clave.get("/static/metricas.json")
    assert metricas.status_code == 200
    assert len(metricas.json()["modelos"]) == 2
    carga = client_sin_clave.get("/static/carga.json")
    assert carga.status_code == 200
    assert carga.json()["tiempos_ms_y_rps"][-1]["endpoint"] == "Agregado"


def test_fallback_sin_modelo_arranca_con_popularidad(monkeypatch, tmp_path, publicador):
    eventos = tmp_path / "eventos.jsonl"
    filas = [
        {"usuario": "u1", "producto": "B0007", "rating": 5, "timestamp": "2026-01-01T00:00:00Z"},
        {"usuario": "u2", "producto": "B0007", "rating": 4, "timestamp": "2026-01-01T00:00:00Z"},
        {"usuario": "u2", "producto": "B0009", "rating": 3, "timestamp": "2026-01-01T00:00:00Z"},
    ]
    eventos.write_text("\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "no_existe.npz"))
    monkeypatch.setenv("EVENTOS_PATH", str(eventos))

    client = TestClient(crear_app(publicador=publicador, api_key=CLAVE), headers={"X-API-Key": CLAVE})
    r = client.get("/recomendar", params={"usuario": "u999", "n": 2})
    assert r.status_code == 200
    assert r.json()["modelo"] == "popularidad-fallback"
    assert [rec["parent_asin"] for rec in r.json()["recomendaciones"]] == ["B0007", "B0009"]
    assert [rec["score"] for rec in r.json()["recomendaciones"]] == [2.0, 1.0]


def test_modelo_path_por_variable_de_entorno(monkeypatch, modelo_sintetico_path, publicador):
    monkeypatch.setenv("MODEL_PATH", str(modelo_sintetico_path))
    client = TestClient(crear_app(publicador=publicador, api_key=CLAVE), headers={"X-API-Key": CLAVE})
    r = client.get("/recomendar", params={"usuario": "u0"})
    assert r.json()["modelo"] == "svd-als"
