#!/usr/bin/env bash
# G-8: OpenAPI → TypeScript 端点表生成器（薄壳）
# 用法: bash scripts/gen-api.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$ROOT/.venv/bin/activate" ]; then
    source "$ROOT/.venv/bin/activate"
fi

python "$ROOT/scripts/gen_api.py" --out "$ROOT/src/cscode/web/src/lib/api/generated/endpoints.ts"