import json
from unittest.mock import MagicMock

import pika
import pytest

import consumidor
import mensajeria
from consumidor import procesar
from mensajeria import COLA, PublicadorRabbit

EVENTO = {"usuario": 5, "producto": 11, "rating": 3, "timestamp": "2026-11-21T10:00:00Z"}


def test_publicador_publica_json_en_cola_durable(monkeypatch):
    canal = MagicMock()
    conexion = MagicMock(is_closed=False, is_open=True)
    conexion.channel.return_value = canal
    monkeypatch.setattr(mensajeria.pika, "BlockingConnection", MagicMock(return_value=conexion))

    PublicadorRabbit("amqp://guest:guest@localhost:5672/").publicar(EVENTO)

    canal.queue_declare.assert_called_once_with(queue=COLA, durable=True)
    args = canal.basic_publish.call_args.kwargs
    assert args["routing_key"] == COLA
    assert json.loads(args["body"]) == EVENTO


def test_publicador_reintenta_una_vez_si_la_conexion_cae(monkeypatch):
    canal_roto = MagicMock(is_closed=False)
    canal_roto.basic_publish.side_effect = pika.exceptions.StreamLostError("cortado")
    canal_nuevo = MagicMock(is_closed=False)
    conexion = MagicMock(is_closed=False, is_open=True)
    conexion.channel.side_effect = [canal_roto, canal_nuevo]
    monkeypatch.setattr(mensajeria.pika, "BlockingConnection", MagicMock(return_value=conexion))

    PublicadorRabbit("amqp://x").publicar(EVENTO)

    canal_nuevo.basic_publish.assert_called_once()


def test_consumidor_registra_evento_en_jsonl(tmp_path):
    ruta = tmp_path / "eventos.jsonl"
    procesar(json.dumps(EVENTO).encode(), ruta)
    procesar(json.dumps({**EVENTO, "producto": 12}).encode(), ruta)

    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2
    assert json.loads(lineas[1])["producto"] == 12


def test_consumidor_rechaza_mensaje_invalido_sin_escribir(tmp_path):
    ruta = tmp_path / "eventos.jsonl"
    with pytest.raises(ValueError):
        procesar(b'{"usuario": 5}', ruta)
    with pytest.raises(ValueError):
        procesar(b"no es json", ruta)
    assert not ruta.exists()


def test_callback_hace_ack_en_evento_valido(tmp_path):
    ruta = tmp_path / "eventos.jsonl"
    canal = MagicMock()
    metodo = MagicMock(delivery_tag=7)
    consumidor._al_recibir(canal, metodo, None, json.dumps(EVENTO).encode(), ruta)
    canal.basic_ack.assert_called_once_with(delivery_tag=7)
    canal.basic_nack.assert_not_called()


def test_callback_hace_nack_sin_reencolar_en_evento_invalido(tmp_path):
    ruta = tmp_path / "eventos.jsonl"
    canal = MagicMock()
    metodo = MagicMock(delivery_tag=8)
    consumidor._al_recibir(canal, metodo, None, b"basura", ruta)
    canal.basic_nack.assert_called_once_with(delivery_tag=8, requeue=False)
    canal.basic_ack.assert_not_called()
