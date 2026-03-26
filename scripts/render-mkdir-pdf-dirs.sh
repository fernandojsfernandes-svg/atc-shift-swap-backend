#!/usr/bin/env sh
# Executar uma vez no Render Shell (ou noutro Linux) depois do disco estar montado.
# Cria as subpastas esperadas pelo import (PDF_FOLDER_ATUAL / PDF_FOLDER_SEGUINTE).
set -e
BASE="${PDF_ESCALAS_BASE:-/var/data/pdf_escalas}"
mkdir -p "$BASE/atual" "$BASE/seguinte"
echo "Pastas criadas:"
ls -la "$BASE/atual"
ls -la "$BASE/seguinte"
