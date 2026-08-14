#!/usr/bin/env bash
# Regenerates the TypeScript API types from the FastAPI OpenAPI spec.
#
# The backend is the single source of truth for the API contract.
# Run this after changing backend schemas:
#
#   1. Start the API (docker compose up -d api)
#   2. make types        (or run this script directly)
#
# Requires: curl, npx (Node 18+).
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
TARGET="packages/shared-types/src/generated/api.ts"

if ! curl -fsS --max-time 5 "$API_URL/openapi.json" -o /tmp/openapi.json; then
  echo "error: cannot reach $API_URL/openapi.json — is the API running?" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
npx --yes openapi-typescript /tmp/openapi.json -o "$TARGET"

echo "generated $TARGET"