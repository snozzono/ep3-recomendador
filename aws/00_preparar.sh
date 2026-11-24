#!/bin/bash
# Paso 0: deja listo el entorno en CloudShell. Seguro de re-ejecutar.
set -e

REPO=https://github.com/snozzono/ep3-recomendador.git
DIR=$HOME/ep3

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone "$REPO" "$DIR"
fi

if [ ! -x "$HOME/venv-sm/bin/python" ]; then
  python3 -m venv "$HOME/venv-sm"
fi
"$HOME/venv-sm/bin/pip" install -q "sagemaker>=2,<3"
"$HOME/venv-sm/bin/python" -c "import sagemaker; print('sagemaker', sagemaker.__version__)"

echo "OK: repo en $DIR y venv en $HOME/venv-sm"
echo "Siguiente: cd $DIR/aws && bash 00_verificar.sh"
