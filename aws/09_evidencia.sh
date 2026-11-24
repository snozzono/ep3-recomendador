#!/usr/bin/env bash
# Evidencia EP3 para capturas desde CloudShell. Solo lectura + 4 llamadas HTTP.
# Cada bloque imprime un titulo "=== [N] ..." para tomar una captura por bloque.
# Ejecutar en CloudShell: API_KEY=<clave> bash 09_evidencia.sh
set -uo pipefail

REGION=us-east-1
BUCKET=ep2-equipo1-128688195152
FN=ep3-recomendador
API_NAME=ep3-recomendador-api
USUARIO=${USUARIO:-AFNT6ZJCYQN3WDIKUSWHJDXNND2Q}
API_KEY=${API_KEY:?Falta API_KEY (export API_KEY=...)}
JOB=$(aws sagemaker list-training-jobs --region $REGION --name-contains ep3-svd \
  --sort-by CreationTime --sort-order Descending --max-results 1 \
  --query 'TrainingJobSummaries[0].TrainingJobName' --output text)

echo "=== [1] Cuenta y region"
aws sts get-caller-identity --query 'Account' --output text
echo "Region: $REGION"

echo "=== [2] SageMaker: job de entrenamiento (${JOB})"
aws sagemaker describe-training-job --region $REGION --training-job-name "$JOB" \
  --query '{Job:TrainingJobName,Estado:TrainingJobStatus,Instancia:ResourceConfig.InstanceType,Segundos:TrainingTimeInSeconds,Facturados:BillableTimeInSeconds,Modelo:ModelArtifacts.S3ModelArtifacts}' \
  --output table

echo "=== [3] S3: datos y modelos publicados"
aws s3 ls s3://$BUCKET/datos/amazon-industrial/ --human-readable
aws s3 ls s3://$BUCKET/modelos/ --human-readable

echo "=== [4] Lambda: configuracion"
aws lambda get-function-configuration --region $REGION --function-name $FN \
  --query '{Nombre:FunctionName,Runtime:Runtime,Memoria:MemorySize,Timeout:Timeout,Rol:Role,Variables:Environment.Variables}' \
  --output table

echo "=== [5] API Gateway: APIs y rutas"
API_ID=$(aws apigatewayv2 get-apis --region $REGION \
  --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)
echo "API_ID=$API_ID"
API_URL=${API_URL:-https://$API_ID.execute-api.$REGION.amazonaws.com/recomendar}
echo "API_URL=$API_URL"
aws apigatewayv2 get-routes --region $REGION --api-id "$API_ID" \
  --query 'Items[].{Ruta:RouteKey,Auth:AuthorizationType}' --output table

echo "=== [6] Pruebas HTTP: sin clave (esperado 401)"
curl -s -o /dev/null -w "HTTP %{http_code}\n" "$API_URL?usuario=$USUARIO"

echo "=== [7] Pruebas HTTP: con clave, usuario valido (esperado 200)"
curl -s -w "\nHTTP %{http_code}\n" -H "X-API-Key: $API_KEY" "$API_URL?usuario=$USUARIO"

echo "=== [8] Pruebas HTTP: usuario inexistente (esperado 404)"
curl -s -w "\nHTTP %{http_code}\n" -H "X-API-Key: $API_KEY" "$API_URL?usuario=999999999"

echo "=== [9] Pruebas HTTP: sin parametro (esperado 400)"
curl -s -w "\nHTTP %{http_code}\n" -H "X-API-Key: $API_KEY" "$API_URL"

echo "=== [10] CloudWatch: ultimas invocaciones de la Lambda"
aws logs describe-log-streams --region $REGION --log-group-name /aws/lambda/$FN \
  --order-by LastEventTime --descending --max-items 1 \
  --query 'logStreams[0].logStreamName' --output text > /tmp/stream.txt
aws logs get-log-events --region $REGION --log-group-name /aws/lambda/$FN \
  --log-stream-name "$(cat /tmp/stream.txt)" --limit 15 \
  --query 'events[].message' --output text | tail -n 15

echo "=== [11] CloudWatch: Count y 4XX de API Gateway (ultima hora)"
aws cloudwatch get-metric-statistics --region $REGION --namespace AWS/ApiGateway \
  --metric-name Count --dimensions Name=ApiId,Value=$API_ID \
  --start-time "$(date -u -d '-1 hour' +%FT%TZ)" --end-time "$(date -u +%FT%TZ)" \
  --period 300 --statistics Sum --query 'Datapoints[].[Timestamp,Sum]' --output table

echo "=== [12] Costo del mes (Learner Lab)"
aws ce get-cost-and-usage --region us-east-1 \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u -d tomorrow +%F) \
  --granularity MONTHLY --metrics UnblendedCost \
  --query 'ResultsByTime[0].Total.UnblendedCost' --output table 2>&1 || echo "ce no disponible: usar captura de Billing"
