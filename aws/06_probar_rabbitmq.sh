#!/usr/bin/env bash
# Prueba el broker RabbitMQ de 05_rabbitmq_ec2.sh: consola HTTP (15672) y AMQP (5672) publicando y leyendo la cola "interacciones".
# Ejecutar en CloudShell con venv-sm activo. Requiere RABBIT_PASS.
set -euo pipefail

REGION=us-east-1
NOMBRE=ep3-rabbitmq
RABBIT_USER=${RABBIT_USER:-ep3}
RABBIT_PASS=${RABBIT_PASS:?definir RABBIT_PASS=<password de RabbitMQ>}

IP=$(aws ec2 describe-instances --region $REGION \
  --filters "Name=tag:Name,Values=$NOMBRE" "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text)
if [ -z "$IP" ] || [ "$IP" = "None" ]; then
  echo "FALLA: no hay instancia $NOMBRE en estado running (correr 05_rabbitmq_ec2.sh)"
  exit 1
fi
echo "IP_PUBLICA=$IP"

CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -u "$RABBIT_USER:$RABBIT_PASS" "http://$IP:15672/api/overview" || true)
echo "HTTP 15672 (API de gestion): $CODE (esperado 200; si 000, esperar 3-5 min a que Docker arranque)"

python3 -c "import pika" 2>/dev/null || python3 -m pip install -q pika

python3 - "$IP" "$RABBIT_USER" "$RABBIT_PASS" <<'PY'
import sys, json, pika

ip, user, pw = sys.argv[1:4]
cred = pika.PlainCredentials(user, pw)
conn = pika.BlockingConnection(pika.ConnectionParameters(host=ip, port=5672, credentials=cred, socket_timeout=10))
ch = conn.channel()
ch.queue_declare(queue="interacciones", durable=True)
msg = json.dumps({"usuario": "TEST", "producto": "TEST", "rating": 5, "timestamp": 0})
ch.basic_publish(exchange="", routing_key="interacciones", body=msg)
metodo, _, body = ch.basic_get(queue="interacciones", auto_ack=True)
print("AMQP publicar+leer: OK" if body else "AMQP publicar+leer: FALLA (cola vacia)")
if body:
    print("mensaje leido:", body.decode())
conn.close()
PY
