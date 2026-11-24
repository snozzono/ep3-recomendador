#!/bin/bash
# Solo lectura: revisa el estado del laboratorio antes de correr el resto.
BUCKET=ep2-equipo1-128688195152
FN=ep3-recomendador
API_NAME=ep3-recomendador-api
REGION=us-east-1
OK=0; FALLA=0
ok()    { echo "OK      $1"; OK=$((OK+1)); }
falla() { echo "FALTA   $1"; FALLA=$((FALLA+1)); }

CUENTA=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
[ "$CUENTA" = "128688195152" ] && ok "cuenta $CUENTA" || falla "cuenta (salida: $CUENTA)"

aws s3 ls "s3://$BUCKET/datos/amazon-industrial/Industrial_and_Scientific.csv" >/dev/null 2>&1 \
  && ok "dataset en S3" || falla "dataset en S3 (correr 01_datos.sh)"

JOB=$(aws sagemaker list-training-jobs --name-contains ep3-svd --sort-by CreationTime --sort-order Descending \
  --max-results 1 --query 'TrainingJobSummaries[0].[TrainingJobName,TrainingJobStatus]' --output text 2>/dev/null)
case "$JOB" in
  *Completed*) ok "ultimo job ep3-svd: $JOB" ;;
  "None"|"") falla "no hay jobs ep3-svd (correr 02_run.py)" ;;
  *) falla "ultimo job ep3-svd no esta Completed: $JOB" ;;
esac

MODELOS=$(aws s3 ls "s3://$BUCKET/modelos/" 2>/dev/null | grep -c "\.npz$")
[ "$MODELOS" -gt 0 ] && ok "modelos publicados en S3: $MODELOS" || falla "sin modelos en s3://$BUCKET/modelos/ (correr 03_publicar_modelo.sh)"

aws lambda get-function --function-name "$FN" --region $REGION >/dev/null 2>&1 \
  && ok "Lambda $FN existe" || falla "Lambda $FN (correr 04_lambda_api.sh)"

APIID=$(aws apigatewayv2 get-apis --region $REGION --query "Items[?Name=='$API_NAME'].ApiId" --output text 2>/dev/null)
[ -n "$APIID" ] && [ "$APIID" != "None" ] && ok "API $API_NAME id=$APIID" || falla "API $API_NAME (correr 04_lambda_api.sh)"

echo "---"
echo "OK=$OK  FALTA=$FALLA"
