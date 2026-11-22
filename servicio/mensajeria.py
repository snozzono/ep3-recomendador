import json
import logging
import threading

import pika

log = logging.getLogger("mensajeria")

COLA = "interacciones"


class PublicadorRabbit:
    """Publica en la cola COLA con una conexión persistente que se reabre si se cae."""

    def __init__(self, url: str):
        self._url = url
        self._conexion = None
        self._canal = None
        self._lock = threading.Lock()

    def _asegurar_canal(self):
        if self._conexion is None or self._conexion.is_closed or self._canal is None or self._canal.is_closed:
            self._conexion = pika.BlockingConnection(pika.URLParameters(self._url))
            self._canal = self._conexion.channel()
            self._canal.queue_declare(queue=COLA, durable=True)
        return self._canal

    def _cerrar(self):
        try:
            if self._conexion is not None and self._conexion.is_open:
                self._conexion.close()
        except pika.exceptions.AMQPError:
            pass
        self._conexion = None
        self._canal = None

    def publicar(self, mensaje: dict) -> None:
        cuerpo = json.dumps(mensaje, ensure_ascii=False).encode("utf-8")
        with self._lock:
            for intento in (1, 2):
                try:
                    self._asegurar_canal().basic_publish(
                        exchange="",
                        routing_key=COLA,
                        body=cuerpo,
                        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
                    )
                    return
                except (pika.exceptions.AMQPError, OSError) as error:
                    log.warning("Fallo publicando (intento %d): %s", intento, error)
                    self._cerrar()
                    if intento == 2:
                        raise
