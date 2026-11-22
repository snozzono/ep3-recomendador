#!/usr/bin/env bash
# Sube el dataset Industrial_and_Scientific (5core rating-only) a S3. Ejecutar en CloudShell.
set -euo pipefail

BUCKET=ep2-equipo1-128688195152
PREFIJO=datos/amazon-industrial
ARCHIVO="${ARCHIVO:-Industrial_and_Scientific.csv}"
# TODO: URL del archivo 5core rating-only (confirmar con el agente de EP3\datos\). Dejar vacía si se usa LOCAL.
URL="${URL:-}"
# Alternativa: subir el archivo a CloudShell con Actions > Upload file (queda en $HOME).
LOCAL="${LOCAL:-$HOME/$ARCHIVO}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [[ -n "$URL" ]]; then
  curl -fL --retry 3 -o "$TMP/$ARCHIVO" "$URL"
  ORIGEN="$TMP/$ARCHIVO"
elif [[ -f "$LOCAL" ]]; then
  ORIGEN="$LOCAL"
else
  echo "ERROR: define URL (TODO) o sube $ARCHIVO a CloudShell ($LOCAL)" >&2
  exit 1
fi

aws s3 cp "$ORIGEN" "s3://$BUCKET/$PREFIJO/$ARCHIVO"

# Punto de control: el archivo debe aparecer con su tamaño
aws s3 ls "s3://$BUCKET/$PREFIJO/"
