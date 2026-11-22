#!/usr/bin/env bash
# Extrae modelo_svd.npz del ultimo job completado y lo publica en S3 con timestamp. Ejecutar en CloudShell.
# Uso: ./03_publicar_modelo.sh [nombre-del-training-job]
set -euo pipefail

BUCKET=ep2-equipo1-128688195152
REGION=us-east-1

JOB="${1:-}"
if [[ -z "$JOB" ]]; then
  JOB=$(aws sagemaker list-training-jobs --name-contains ep3-svd --status-equals Completed \
    --sort-by CreationTime --sort-order Descending --max-results 1 \
    --query 'TrainingJobSummaries[0].TrainingJobName' --output text --region "$REGION")
fi
if [[ -z "$JOB" || "$JOB" == "None" ]]; then
  echo "ERROR: no hay training jobs ep3-svd completados" >&2
  exit 1
fi
echo "Job: $JOB"

ARTEFACTO=$(aws sagemaker describe-training-job --training-job-name "$JOB" \
  --query 'ModelArtifacts.S3ModelArtifacts' --output text --region "$REGION")

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

aws s3 cp "$ARTEFACTO" "$TMP/model.tar.gz" --region "$REGION"
tar -xzf "$TMP/model.tar.gz" -C "$TMP" modelo_svd.npz

STAMP=$(date -u +%Y%m%d-%H%M%S)
MODEL_KEY="modelos/modelo_svd-$STAMP.npz"

aws s3 cp "$TMP/modelo_svd.npz" "s3://$BUCKET/$MODEL_KEY" --region "$REGION"

# Punto de control: el archivo debe aparecer en modelos/
aws s3 ls "s3://$BUCKET/modelos/" --region "$REGION"

echo "MODEL_KEY=$MODEL_KEY"
echo "Usar: export MODEL_KEY=$MODEL_KEY"
