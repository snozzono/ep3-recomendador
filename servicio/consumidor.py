import json
import logging
import os
import time
from pathlib import Path

import pika
from pydantic import ValidationError

from mensajeria import COLA
from schemas import InteraccionIn

log = logging.getLogger("consumidor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

EVENTOS_DEFAULT = Path(__file__).resolve().parent / "eventos.jsonl"
ESPERA_MAX = 30


def procesar(cuerpo: bytes, ruta: Path) -> dict:
    """Valida el evento y lo agrega a eventos.jsonl. Es el punto donde luego se actualizará el modelo."""
    evento = InteraccionIn.model_validate_json(cuerpo).model_dump(mode="json")
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
    return evento


def _al_recibir(canal, metodo, _propiedades, cuerpo, ruta: Path) -> None:
    try:
        evento = procesar(cuerpo, ruta)
    except (ValidationError, ValueError) as error:
        log.error("Mensaje descartado (no válido): %s", error)
        canal.basic_nack(delivery_tag=metodo.delivery_tag, requeue=False)
        return
    log.info("Evento registrado: usuario=%s producto=%s rating=%s", evento["usuario"], evento["producto"], evento["rating"])
    canal.basic_ack(delivery_tag=metodo.delivery_tag)


def consumir(url: str, ruta: Path) -> None:
    espera = 1
    while True:
        conexion = None
        try:
            conexion = pika.BlockingConnection(pika.URLParameters(url))
            canal = conexion.channel()
            canal.queue_declare(queue=COLA, durable=True)
            canal.basic_qos(prefetch_count=10)
            canal.basic_consume(
                queue=COLA,
                on_message_callback=lambda c, m, p, b: _al_recibir(c, m, p, b, ruta),
            )
            espera = 1
            log.info("Escuchando la cola '%s' en %s", COLA, url)
            canal.start_consuming()
        except KeyboardInterrupt:
            log.info("Detenido por el usuario")
            break
        except (pika.exceptions.AMQPError, OSError) as error:
            log.warning("Conexión con RabbitMQ perdida o no disponible (%s). Reintento en %ss", error, espera)
        finally:
            if conexion is not None and conexion.is_open:
                conexion.close()
        time.sleep(espera)
        espera = min(espera * 2, ESPERA_MAX)


def main() -> None:
    url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    ruta = Path(os.getenv("EVENTOS_PATH", EVENTOS_DEFAULT))
    consumir(url, ruta)


if __name__ == "__main__":
    main()
