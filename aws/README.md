# EP3 - Recomendador en AWS (Learner Lab, us-east-1)

Todo se ejecuta en **CloudShell** (Bash). Cuenta: `128688195152`, rol `LabRole`, bucket `ep2-equipo1-128688195152`.

## Archivos

| Script | Qué hace |
|---|---|
| `01_datos.sh` | Sube el dataset Industrial_and_Scientific a `s3://…/datos/amazon-industrial/`. |
| `02_entrenar_sagemaker.py` | Script de entrenamiento (corre dentro de SageMaker): lee el canal `datos`, construye la matriz usuario×producto, entrena ALS implícito (numpy puro, 32 factores, regularización 0,01, 15 iteraciones, confianza = rating) y guarda `modelo_svd.npz` (U, V, user_ids, item_ids, vistos_ptr y vistos). El nombre de archivo y el job `ep3-svd` se mantienen por compatibilidad con `03`. |
| `02_run.py` | Lanza el training job `ep3-svd` (SKLearn 1.2-1, `ml.t3.large`, LabRole). |
| `03_publicar_modelo.sh` | Toma el último job completado, extrae `modelo_svd.npz` y lo sube a `modelos/modelo_svd-<timestamp>.npz`. Imprime `MODEL_KEY`. |
| `04_lambda_api.sh` | Crea/actualiza la Lambda `ep3-recomendador` (python3.12, 30 s, 512 MB, numpy empaquetado) y la HTTP API con `GET /recomendar?usuario=…` (AWS_PROXY, payload 2.0). |
| `05_rabbitmq_ec2.sh` | (Opcional) EC2 t3.large con Docker + RabbitMQ 3 management; SG abierto a 22/5672/15672 solo para tu IP. |

## Orden de ejecución

### 0. Preparación (CloudShell)
```bash
python3 -m pip install --user "sagemaker<3"   # el SDK v2 es requerido
```
Subir los scripts: en CloudShell, **Actions > Upload file** (carpeta `aws/`), o copiarlos a mano.

### 1. Dataset
Antes: definir la URL del 5core rating-only (`TODO` en el script) **o** subir `Industrial_and_Scientific.csv` a `$HOME` de CloudShell.
```bash
cd ~/aws && bash 01_datos.sh
```
**Punto de control:** `aws s3 ls` muestra `Industrial_and_Scientific.csv` con tamaño > 0.

> El archivo local `EP3\datos\Industrial_and_Scientific.csv` tiene cabecera `user_id,parent_asin,rating,timestamp` (CSV). `02_entrenar_sagemaker.py` acepta CSV o JSON Lines.

### 2. Entrenamiento
```bash
python3 02_run.py
```
**Punto de control:** la salida termina en `TRAINING_JOB = ep3-svd-…` y el log muestra `ratings=… usuarios=… productos=…` y `modelo guardado`. En consola: SageMaker > Training jobs > estado `Completed`. Tiempo de referencia: ~2–3 min en ML-100K; el dataset completo tarda más.

### 3. Publicar modelo
```bash
bash 03_publicar_modelo.sh            # o: bash 03_publicar_modelo.sh <nombre-del-job>
export MODEL_KEY=modelos/modelo_svd-YYYYMMDD-HHMMSS.npz   # copiar la línea MODEL_KEY impresa
```
**Punto de control:** `aws s3 ls s3://ep2-equipo1-128688195152/modelos/` muestra el `.npz`. La clave **siempre** lleva el prefijo `modelos/`.

### 4. Lambda + API
```bash
bash 04_lambda_api.sh                 # primera vez: crea API nueva
export API_ID=xxxxxxxxxx              # el ID impreso
bash 04_lambda_api.sh                 # siguientes: reutiliza API_ID, no crea otra
```
> **Advertencia:** sin `API_ID` cada ejecución crea una API nueva. Exportar `API_ID` después de la primera vez.

**Punto de control:**
```bash
curl "https://<API_ID>.execute-api.us-east-1.amazonaws.com/recomendar?usuario=<USER_ID_REAL>"
```
Debe devolver `200` con `recomendaciones` (10 `parent_asin` con score). Un usuario inexistente da `404`; sin parámetro, `400`. Revisar logs en CloudWatch `/aws/lambda/ep3-recomendador` si falla.

### 5. (Opcional) RabbitMQ en EC2
```bash
export MI_IP=<tu IP pública IPv4>     # ej. desde https://checkip.amazonaws.com en tu PC
export RABBIT_PASS=<password>
export KEY_NAME=<key-pair>            # opcional, para SSH
bash 05_rabbitmq_ec2.sh
```
**Punto de control:** imprime `INSTANCE_ID` e `IP_PUBLICA`. Tras 3–5 min, `http://<IP>:15672` pide login (usuario `ep3` por defecto).

## Limpieza (al terminar; evita consumo de créditos)

```bash
# EC2 (y luego su security group)
aws ec2 terminate-instances --instance-ids <INSTANCE_ID> --region us-east-1
aws ec2 wait instance-terminated --instance-ids <INSTANCE_ID> --region us-east-1
aws ec2 delete-security-group --group-name ep3-rabbitmq-sg --region us-east-1

# API Gateway y Lambda
aws apigatewayv2 delete-api --api-id <API_ID> --region us-east-1
aws lambda delete-function --function-name ep3-recomendador --region us-east-1
aws logs delete-log-group --log-group-name /aws/lambda/ep3-recomendador --region us-east-1

# Jobs de SageMaker: no se borran (quedan como historial). Si hay alguno en curso:
aws sagemaker stop-training-job --training-job-name <JOB>

# S3 (opcional): artefactos de entrenamiento y modelos viejos
aws s3 rm s3://ep2-equipo1-128688195152/sagemaker-output/ --recursive
aws s3 rm s3://ep2-equipo1-128688195152/modelos/ --recursive   # solo si ya no se necesitan
```
No borrar `datos/amazon-industrial/` mientras se trabaje con el modelo.

## Notas
- Los IDs de producto que devuelve la API son `parent_asin` (no títulos). Para mostrar nombres habría que cargar metadatos aparte.
- `numpy` se empaqueta en el zip porque el runtime de Lambda no lo incluye. El zip debería quedar bajo el límite de 50 MB de subida directa (no verificado aún: revisar `ls -lh $TMP/fn.zip` si `create-function` falla por tamaño).
