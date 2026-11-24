# EP3 · Despliegue en AWS Academy Learner Lab

Todo se ejecuta en **AWS CloudShell** (us-east-1). Cada paso termina con un **punto de control**: no sigas si no se cumple.

Cuenta `128688195152` · bucket `ep2-equipo1-128688195152` · rol `LabRole` · instance profile `LabInstanceProfile`.

## Paso 0 · Preparar el entorno

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/snozzono/ep3-recomendador/main/aws/00_preparar.sh)
```

Si falla, clona a mano: `git clone https://github.com/snozzono/ep3-recomendador.git ~/ep3 && bash ~/ep3/aws/00_preparar.sh`

**Punto de control:** la última línea dice `OK: repo en ~/ep3 y venv en ~/venv-sm`.

## Paso 1 · Verificar estado

```bash
cd ~/ep3/aws && bash 00_verificar.sh
```

**Punto de control:** qué se ve en `FALTA` indica qué paso correr (ver tabla). Con el lab recién reseteado, esperar `FALTA` en el job y en modelos.

| FALTA | Paso que lo resuelve |
|---|---|
| dataset en S3 | 01_datos.sh (sólo si el bucket se vació) |
| no hay jobs ep3-svd | paso 2 |
| sin modelos | paso 3 |
| Lambda / API | paso 4 |

## Paso 2 · Entrenar en SageMaker (ALS implícito)

```bash
cd ~/ep3/aws
source ~/venv-sm/bin/activate
python 02_run.py
```

Tarda varios minutos (dataset completo). Ve el log en pantalla.

**Punto de control:** la última línea dice `Job ... Completed`. Si dice `Failed`, revisar CloudWatch: log group `/aws/sagemaker/TrainingJobs`, stream del job.

## Paso 3 · Publicar el modelo

```bash
bash 03_publicar_modelo.sh
```

**Punto de control:** imprime `MODEL_KEY=modelos/modelo_svd-<fecha>.npz`. Verificar: `aws s3 ls s3://ep2-equipo1-128688195152/modelos/`.

## Paso 4 · Lambda y API Gateway

La API exige la misma clave que el servicio local (cabecera `X-API-Key`). Definirla antes de correr el script (si falta, el script se detiene):

```bash
export API_KEY=<misma clave que en .env local>
bash 04_lambda_api.sh
```

La primera vez crea la API `ep3-recomendador-api` y avisa el `API_ID`. Exporta el id y vuelve a correr para actualizar sin crear otra API (la Lambda recibe de nuevo el código y la variable `API_KEY`):

```bash
export API_ID=<id impreso>
export API_KEY=<misma clave que en .env local>
bash 04_lambda_api.sh
```

**Punto de control:**

```bash
URL="https://$API_ID.execute-api.us-east-1.amazonaws.com/recomendar"
curl -s -o /dev/null -w "%{http_code}\n" "$URL?usuario=<ID_EXISTENTE>"                        # esperado 401 (sin clave)
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $API_KEY" "$URL?usuario=<ID_EXISTENTE>" # esperado 200
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $API_KEY" "$URL?usuario=999999999"      # esperado 404
```

Si la clave es incorrecta o no se envía, responde 401 `{"error":"no autorizado"}`. Sin `usuario` con clave válida, responde 400.

Logs: CloudWatch `/aws/lambda/ep3-recomendador`.

## Paso 5 · RabbitMQ en EC2 (opcional)

```bash
export MI_IP=<tu IP pública>
export RABBIT_PASS=<clave>
bash 05_rabbitmq_ec2.sh
```

**Punto de control:** imprime `INSTANCE_ID` e `IP_PUBLICA`. Consola `http://<IP>:15672`, usuario `ep3`.

## Paso 6 · Probar el broker (requiere paso 5)

```bash
export MI_IP=<tu IP pública>   # ya usada en paso 5, no cambia
export RABBIT_PASS=<clave>
bash 06_probar_rabbitmq.sh
```

**Punto de control:** `HTTP 15672 ... 200` y `AMQP publicar+leer: OK` con el mensaje de prueba. Si el HTTP da `000`, esperar 3-5 min a que Docker arranque.

## Paso 7 · Limpieza (al terminar cada sesión)

```bash
CONFIRMAR=si bash 07_limpieza.sh
```

Borra: EC2 `ep3-rabbitmq`, security group `ep3-rabbitmq-sg`, API `ep3-recomendador-api`, Lambda `ep3-recomendador` y su log group. **No borra** el bucket, los datos ni los modelos en S3, ni los jobs de SageMaker (no generan costo).
Verificación posterior: `bash 00_verificar.sh` debe marcar FALTA en Lambda y API.

## Notas

- La API devuelve `parent_asin`, no nombres de producto. Los nombres requieren `meta_Industrial_and_Scientific`, no descargado.
- Paso 2 verificado: el job `ep3-svd-2026-11-24-15-45-45-251` está `Completed` (fix `-k/--k` aplicado). API ID actual: `5uli1pw7qf`.
