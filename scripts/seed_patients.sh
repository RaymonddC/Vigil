#!/usr/bin/env bash
# Wrapper for data/seed_hapi.py — forwards all arguments.
# Usage:
#   ./scripts/seed_patients.sh --fhir-base http://localhost:8080/fhir
#   ./scripts/seed_patients.sh --generate-only --out data/patients
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec python3 "${REPO_ROOT}/data/seed_hapi.py" "$@"
