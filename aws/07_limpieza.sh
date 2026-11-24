#!/usr/bin/env bash
# Limpieza de recursos EP3 para no consumir creditos del Learner Lab.
# Borra: EC2 ep3-rabbitmq, security group ep3-rabbitmq-sg, API ep3-recomendador-api, Lambda ep3-recomendador y su log group.
# NO borra: bucket, datos, modelos en S3, ni jobs de SageMaker (no generan costo).
# Ejecutar en CloudShell: CONFIRMAR=si bash 07_limpieza.sh
set -uo pipefail

REGION=us-east-1
FN=ep3-recomendador
API_NAME=ep3-recomendador-api
SG_NOMBRE=ep3-rabbitmq-sg

if [ "${CONFIRMAR:-}" != "si" ]; then
  echo "Abortado. Ejecutar con: CONFIRMAR=si bash 07_limpieza.sh"
  exit 1
fi

IDS=$(aws ec2 describe-instances --region $REGION \
  --filters "Name=tag:Name,Values=ep3-rabbitmq" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)
if [ -n "$IDS" ] && [ "$IDS" != "None" ]; then
  echo "Terminando EC2: $IDS"
  aws ec2 terminate-instances --region $REGION --instance-ids $IDS >/dev/null
  aws ec2 wait instance-terminated --region $REGION --instance-ids $IDS && echo "EC2 terminada"
else
  echo "No hay EC2 ep3-rabbitmq activa"
fi

SG=$(aws ec2 describe-security-groups --region $REGION \
  --filters "Name=group-name,Values=$SG_NOMBRE" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [ -n "$SG" ] && [ "$SG" != "None" ]; then
  aws ec2 delete-security-group --region $REGION --group-id $SG && echo "Security group borrado: $SG" \
    || echo "No se pudo borrar $SG (reintentar en 1 minuto)"
fi

APIID=$(aws apigatewayv2 get-apis --region $REGION --query "Items[?Name=='$API_NAME'].ApiId" --output text 2>/dev/null)
if [ -n "$APIID" ] && [ "$APIID" != "None" ]; then
  aws apigatewayv2 delete-api --region $REGION --api-id $APIID && echo "API borrada: $APIID"
fi

aws lambda delete-function --region $REGION --function-name $FN 2>/dev/null && echo "Lambda borrada: $FN" || echo "Lambda $FN no existia"
aws logs delete-log-group --region $REGION --log-group-name /aws/lambda/$FN 2>/dev/null && echo "Log group borrado" || echo "Log group no existia"

echo "Listo. Verificar con: bash 00_verificar.sh (Lambda y API deben aparecer como FALTA)"
