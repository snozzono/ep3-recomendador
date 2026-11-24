#!/usr/bin/env bash
# Rehace todo el pipeline EP3 en CloudShell, en orden, para tomar las capturas de nuevo.
# Uso: export API_KEY=<clave> && bash 10_todo.sh
# Pasos: 00 preparar -> 00 verificar -> entrenar SageMaker -> publicar modelo -> Lambda+API -> evidencia.
# Idempotente: si la API ya existe por nombre, la reutiliza (no crea otra).
set -euo pipefail

: "${API_KEY:?Falta API_KEY (export API_KEY=...)}"
REGION=us-east-1
API_NAME=ep3-recomendador-api
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "=== PASO 0: repo y entorno"
if [ -d "$HOME/ep3/.git" ]; then
  git -C "$HOME/ep3" pull -q
else
  git clone -q https://github.com/snozzono/ep3-recomendador.git "$HOME/ep3"
fi
if [ ! -x "$HOME/venv-sm/bin/python" ]; then
  python3 -m venv "$HOME/venv-sm"
  "$HOME/venv-sm/bin/pip" install -q "sagemaker>=2,<3"
fi
source "$HOME/venv-sm/bin/activate"
cd "$HOME/ep3/aws"

echo "=== PASO 1: verificar cuenta y datos"
bash 00_verificar.sh || true

echo "=== PASO 2: entrenar en SageMaker (tarda ~4 min)"
python3 02_run.py

echo "=== PASO 3: publicar modelo"
bash 03_publicar_modelo.sh
MODEL_KEY=$(aws s3api list-objects-v2 --bucket ep2-equipo1-128688195152 --prefix modelos/ \
  --query 'sort_by(Contents,&LastModified)[-1].Key' --output text --region $REGION)
export MODEL_KEY
echo "MODEL_KEY=$MODEL_KEY"

echo "=== PASO 4: Lambda y API"
if [ -z "${API_ID:-}" ]; then
  API_ID=$(aws apigatewayv2 get-apis --region $REGION \
    --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)
  [ "$API_ID" = "None" ] && API_ID=""
fi
export API_ID
bash 04_lambda_api.sh
API_ID=$(aws apigatewayv2 get-apis --region $REGION \
  --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)
export API_ID
echo "API_ID=$API_ID"

echo "=== PASO 5: evidencia (capturas)"
bash 09_evidencia.sh

echo "=== LISTO. Si algo falló, revisar el paso anterior antes de seguir."
