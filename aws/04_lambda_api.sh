#!/usr/bin/env bash
# Crea/actualiza la Lambda ep3-recomendador y su HTTP API (GET /recomendar?usuario=...). Ejecutar en CloudShell.
#
# ADVERTENCIA: si API_ID no se define, cada ejecucion CREA una API nueva (cobra y deja basura).
# Tras la primera ejecucion, exportar el API_ID impreso: export API_ID=xxxx
set -euo pipefail

BUCKET=ep2-equipo1-128688195152
REGION=us-east-1
CUENTA=128688195152
ROLE_ARN=arn:aws:iam::$CUENTA:role/LabRole
FN=ep3-recomendador
RUTA="GET /recomendar"

MODEL_KEY="${MODEL_KEY:-}"
API_ID="${API_ID:-}"

if [[ -z "$MODEL_KEY" ]]; then
  MODEL_KEY=$(aws s3api list-objects-v2 --bucket "$BUCKET" --prefix modelos/ \
    --query 'sort_by(Contents,&LastModified)[-1].Key' --output text --region "$REGION")
  if [[ -z "$MODEL_KEY" || "$MODEL_KEY" == "None" ]]; then
    echo "ERROR: no hay modelos en s3://$BUCKET/modelos/ (ejecutar 03 primero)" >&2
    exit 1
  fi
  echo "MODEL_KEY no definido: usando el mas reciente -> $MODEL_KEY"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/pkg"

# numpy no viene en el runtime de Lambda: se empaqueta con wheel manylinux para x86_64, Python 3.12
python3 -m pip install --quiet --target "$TMP/pkg" --platform manylinux2014_x86_64 \
  --implementation cp --python-version 3.12 --only-binary=:all: numpy

cat > "$TMP/pkg/lambda_function.py" <<'PYEOF'
import io
import json
import os

import boto3
import numpy as np

s3 = boto3.client("s3")
_modelo = None


def _cargar():
    global _modelo
    if _modelo is None:
        obj = s3.get_object(Bucket=os.environ["BUCKET"], Key=os.environ["MODEL_KEY"])
        d = np.load(io.BytesIO(obj["Body"].read()))
        _modelo = {
            "U": d["U"],
            "V": d["V"],
            "item_ids": d["item_ids"],
            "indptr": d["vistos_ptr"],
            "indices": d["vistos"],
            "uidx": {u: i for i, u in enumerate(d["user_ids"].tolist())},
        }
    return _modelo


def _respuesta(code, cuerpo):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(cuerpo, ensure_ascii=False),
    }


def lambda_handler(event, context):
    usuario = ((event or {}).get("queryStringParameters") or {}).get("usuario", "").strip()
    if not usuario:
        return _respuesta(400, {"error": "falta el parametro usuario"})
    m = _cargar()
    i = m["uidx"].get(usuario)
    if i is None:
        return _respuesta(404, {"error": "usuario sin historial", "usuario": usuario})
    puntajes = m["V"] @ m["U"][i]
    vistos = m["indices"][m["indptr"][i]:m["indptr"][i + 1]]
    puntajes[vistos] = -np.inf
    top = np.argsort(-puntajes)[:10]
    recs = [{"parent_asin": str(m["item_ids"][j]), "score": float(puntajes[j])} for j in top]
    return _respuesta(200, {"usuario": usuario, "recomendaciones": recs})
PYEOF

(cd "$TMP/pkg" && zip -qr "$TMP/fn.zip" .)

VARS="Variables={BUCKET=$BUCKET,MODEL_KEY=$MODEL_KEY}"

if aws lambda get-function --function-name "$FN" --region "$REGION" >/dev/null 2>&1; then
  echo "Actualizando Lambda $FN"
  aws lambda update-function-code --function-name "$FN" --zip-file "fileb://$TMP/fn.zip" --region "$REGION" >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FN" --region "$REGION"
  aws lambda update-function-configuration --function-name "$FN" --runtime python3.12 \
    --role "$ROLE_ARN" --handler lambda_function.lambda_handler \
    --timeout 30 --memory-size 512 --environment "$VARS" --region "$REGION" >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FN" --region "$REGION"
else
  echo "Creando Lambda $FN"
  aws lambda create-function --function-name "$FN" --runtime python3.12 \
    --role "$ROLE_ARN" --handler lambda_function.lambda_handler \
    --zip-file "fileb://$TMP/fn.zip" --timeout 30 --memory-size 512 \
    --environment "$VARS" --region "$REGION" >/dev/null
  aws lambda wait function-active-v2 --function-name "$FN" --region "$REGION"
fi

LAMBDA_ARN=$(aws lambda get-function --function-name "$FN" --region "$REGION" \
  --query 'Configuration.FunctionArn' --output text)

if [[ -z "$API_ID" ]]; then
  echo "ADVERTENCIA: API_ID vacio -> creando una API NUEVA. Guardar el ID impreso y exportar API_ID en las proximas ejecuciones."
  API_ID=$(aws apigatewayv2 create-api --name ep3-recomendador-api --protocol-type HTTP \
    --query 'ApiId' --output text --region "$REGION")
fi
echo "API_ID=$API_ID"

INT_ID=$(aws apigatewayv2 get-integrations --api-id "$API_ID" --region "$REGION" \
  --query "Items[?IntegrationUri=='$LAMBDA_ARN'].IntegrationId | [0]" --output text)
if [[ -z "$INT_ID" || "$INT_ID" == "None" ]]; then
  INT_ID=$(aws apigatewayv2 create-integration --api-id "$API_ID" --integration-type AWS_PROXY \
    --integration-uri "$LAMBDA_ARN" --payload-format-version 2.0 \
    --query 'IntegrationId' --output text --region "$REGION")
fi

RUTA_ID=$(aws apigatewayv2 get-routes --api-id "$API_ID" --region "$REGION" \
  --query "Items[?RouteKey=='$RUTA'].RouteId | [0]" --output text)
if [[ -z "$RUTA_ID" || "$RUTA_ID" == "None" ]]; then
  aws apigatewayv2 create-route --api-id "$API_ID" --route-key "$RUTA" \
    --target "integrations/$INT_ID" --region "$REGION" >/dev/null
fi

# Stage $default con auto-deploy (si no existe)
if ! aws apigatewayv2 get-stage --api-id "$API_ID" --stage-name '$default' --region "$REGION" >/dev/null 2>&1; then
  aws apigatewayv2 create-stage --api-id "$API_ID" --stage-name '$default' --auto-deploy --region "$REGION" >/dev/null
fi

# Permiso para que API Gateway invoque la Lambda (si ya existe, el error es esperado)
if ! aws lambda add-permission --function-name "$FN" --statement-id "apigw-$API_ID-recomendar" \
  --action lambda:InvokeFunction --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$CUENTA:$API_ID/*/GET/recomendar" \
  --region "$REGION" >/dev/null 2>&1; then
  echo "Permiso ya existente (ok)"
fi

# Punto de control: probar con un usuario real del dataset
echo "URL: https://$API_ID.execute-api.$REGION.amazonaws.com/recomendar?usuario=USUARIO_REAL"
echo "Prueba: curl \"https://$API_ID.execute-api.$REGION.amazonaws.com/recomendar?usuario=USUARIO_REAL\""
