#!/usr/bin/env bash
# Send a Prompt-Opinion-flavor JSON-RPC SendMessage to the A2A agent and
# pretty-print the response. Used to verify dispatch + skill routing +
# SHARP context propagation end-to-end without going through PO's launchpad.
#
# All knobs are env vars with sensible defaults. Invoke via `make smoke`
# (which forwards Make's ALL_ARGS / variable assignments).
#
# Examples:
#   make smoke                                              # local agent → local HAPI → vigil.screen_vitals
#   make smoke SKILL=draft_sbar                             # different skill (keyword routing in the prompt)
#   make smoke AGENT=https://abc.ngrok-free.app             # hit ngrok instead
#   make smoke FHIR_URL=https://app.promptopinion.ai/...    # PO workspace FHIR (will 403 without a fhirToken)
#   make smoke PATIENT=abb130a6-... FHIR_URL=https://app.promptopinion.ai/...   # full PO simulation

set -euo pipefail

AGENT="${AGENT:-http://localhost:9000}"
SKILL="${SKILL:-screen_vitals}"
KEY="${VIGIL_API_KEY:-local-dev-key-anything}"
PATIENT="${PATIENT:-PT-001}"
FHIR_URL="${FHIR_URL:-http://localhost:8080/fhir}"

# One-line prompts per skill (the keywords drive vigil's text-based
# routing fallback when no skill_id metadata is present)
case "$SKILL" in
  screen_vitals)  PROMPT="Please screen this patient's vitals against early-warning thresholds." ;;
  score_risk)     PROMPT="Score this patient's deterioration risk and qSOFA." ;;
  check_sepsis)   PROMPT="Check this patient for sepsis onset." ;;
  draft_sbar)     PROMPT="Draft an SBAR escalation note for this patient." ;;
  start_watching) PROMPT="Start autonomously watching this patient." ;;
  *)              PROMPT="$SKILL" ;;  # custom prompt — falls through unrouted
esac

REQ_ID="smoke-$(date +%s)"
MSG_ID="msg-$(date +%s)"

cat <<INFO >&2
→ POST $AGENT/a2a
  skill keyword : $SKILL
  patient_id    : $PATIENT
  fhir_url      : $FHIR_URL
  prompt        : $PROMPT
INFO

cat > /tmp/vigil-smoke-body.json <<EOF
{
  "jsonrpc": "2.0",
  "id": "$REQ_ID",
  "method": "SendMessage",
  "params": {
    "message": {
      "role": "ROLE_USER",
      "messageId": "$MSG_ID",
      "parts": [{"text": "$PROMPT"}],
      "metadata": {
        "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context": {
          "fhirUrl": "$FHIR_URL",
          "patientId": "$PATIENT"
        }
      }
    }
  }
}
EOF

curl -sS -X POST "$AGENT/a2a" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  --data-binary @/tmp/vigil-smoke-body.json \
  | python3 -m json.tool
