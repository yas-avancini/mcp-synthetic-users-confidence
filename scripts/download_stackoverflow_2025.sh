#!/usr/bin/env bash
# Baixa os microdados da Stack Overflow Developer Survey 2025 (ODbL 1.0).
# Fonte: https://github.com/StackExchange/Survey/tree/main/packages/archive/2025
# Os arquivos ficam no Git LFS, por isso usamos o endpoint de mídia.
# Os dados NÃO são versionados neste repositório: atribuição a Stack Overflow.
set -euo pipefail
OUT="${1:-data/stackoverflow-2025}"
BASE="https://media.githubusercontent.com/media/StackExchange/Survey/main/packages/archive/2025"
mkdir -p "$OUT"
curl -fL -o "$OUT/results.csv" "$BASE/results.csv"
curl -fL -o "$OUT/schema.csv" "$BASE/schema.csv"
echo "Pronto em $OUT (results.csv ~141 MB)."
