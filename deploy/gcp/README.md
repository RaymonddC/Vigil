# Vigil on Google Cloud Platform (Cloud Run)

End-to-end deploy path for the 4-service Vigil stack on GCP. Designed to
fit inside the $300 free-trial credit and scale to **$0/month** once idle.

- **`vigil-api`** — FastAPI proxy · port 8000 → Cloud Run :8080 · **public**
- **`vigil-mcp`** — MCP server (4 tools) · port 7001 → :8080 · **public**
- **`vigil-a2a`** — A2A agent (+ `AgentCard`) · port 9000 → :8080 · **public**
- **`vigil-hapi`** — HAPI FHIR R4 (+ Cloud SQL) · port 8080 · **internal only (SEC-10)**

Option A (Cloud Run) is recommended for the hackathon. Options B (GKE) and C
(GCE VM) are documented as fallbacks at the bottom.

---

## Cost model

Cloud Run scales idle instances to zero. Billing is per-request vCPU-seconds
plus Artifact Registry storage and Cloud SQL. Realistic hackathon line items:

| Item | Est. monthly | Notes |
|---|---|---|
| Cloud Run (4 services, `minScale=1` on `vigil-api`/`a2a`) | ~$8–12 | Disable `minScale` post-demo to hit $0 |
| Cloud SQL `db-f1-micro` (HAPI) | ~$9 | Only runs if the HAPI VM is alive |
| Artifact Registry (~200 MB image) | <$0.10 | |
| Egress (hackathon traffic) | <$1 | |
| **Total** | **~$18** during demo week, **$0–$9** idle | Well under $300 free trial |

Set `minScale=0` on every service post-demo to drop Cloud Run to $0.
Shut down the Cloud SQL instance (or use `SUSPENDED`) when not demoing.

---

## Option A — Cloud Run (recommended)

### 0. Prerequisites

```bash
gcloud auth login
gcloud components install beta
export PROJECT_ID=vigil-hackathon    # your project id
export REGION=us-central1
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION
```

### 1. Create the project and enable APIs

```bash
gcloud projects create $PROJECT_ID --name="Vigil Hackathon"
gcloud billing projects link $PROJECT_ID --billing-account=$BILLING_ACCOUNT_ID

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  vpcaccess.googleapis.com \
  compute.googleapis.com \
  servicenetworking.googleapis.com
```

### 2. Artifact Registry + build the image

```bash
gcloud artifacts repositories create vigil \
  --repository-format=docker --location=$REGION \
  --description="Vigil container images"

# Kick off the Cloud Build pipeline (builds & pushes vigil:latest + vigil:$SHA)
gcloud builds submit --config=deploy/gcp/cloudbuild.yaml \
  --substitutions=_LOCATION=$REGION,_REPO=vigil,_IMAGE=vigil,SHORT_SHA=$(git rev-parse --short HEAD)
```

### 3. VPC + Serverless VPC Access connector

Needed so Cloud Run services can reach HAPI (ingress=internal) and Cloud SQL
via private IP. Uses the default VPC.

```bash
# Allocate a /28 range for the serverless connector
gcloud compute networks vpc-access connectors create vigil-connector \
  --region=$REGION \
  --network=default \
  --range=10.8.0.0/28 \
  --min-instances=2 --max-instances=3

# Allocate a private services range for Cloud SQL (one-time per project)
gcloud compute addresses create google-managed-services-default \
  --global --purposes=VPC_PEERING --prefix-length=16 --network=default
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-default --network=default
```

### 4. Cloud SQL for HAPI

```bash
# Postgres 15, tiny tier, private IP only.
gcloud sql instances create vigil-hapi-db \
  --region=$REGION --database-version=POSTGRES_15 \
  --tier=db-f1-micro --network=default --no-assign-ip

gcloud sql databases create hapi --instance=vigil-hapi-db

# Set the DB password (also saved to Secret Manager below).
HAPI_DB_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
gcloud sql users create hapi --instance=vigil-hapi-db --password="$HAPI_DB_PASSWORD"

# Grab the private IP — you'll need it for cloud-run-hapi.yaml.
CLOUD_SQL_PRIVATE_IP=$(gcloud sql instances describe vigil-hapi-db \
  --format='value(ipAddresses[0].ipAddress)')
echo "Cloud SQL private IP: $CLOUD_SQL_PRIVATE_IP"
```

### 5. Secrets in Secret Manager

```bash
# Vigil-wide API key (matches VIGIL_API_KEY elsewhere)
VIGIL_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
printf "%s" "$VIGIL_API_KEY"      | gcloud secrets create vigil-api-key       --data-file=-
printf "%s" "$HAPI_DB_PASSWORD"   | gcloud secrets create hapi-db-password    --data-file=-
printf "%s" "$GROQ_API_KEY"       | gcloud secrets create groq-api-key        --data-file=-
printf "%s" "$ANTHROPIC_API_KEY"  | gcloud secrets create anthropic-api-key   --data-file=-
```

### 6. Runtime service account

```bash
gcloud iam service-accounts create vigil-run \
  --display-name="Vigil Cloud Run runtime"

SA=vigil-run@$PROJECT_ID.iam.gserviceaccount.com

# Read secrets
for s in vigil-api-key hapi-db-password groq-api-key anthropic-api-key; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
done

# Invoke other Cloud Run services (for calling internal HAPI)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/run.invoker"
```

### 7. Patch the YAMLs with your project/hashes

The four Knative YAMLs in this directory contain placeholders:

- `PROJECT_ID`  → your GCP project id (e.g. `vigil-hackathon`)
- `PROJECT_HASH` → the hash in your `*.a.run.app` URL (first deploy produces it)
- `CLOUD_SQL_PRIVATE_IP` (in `cloud-run-hapi.yaml` only) → value from step 4

Quick sed pass:

```bash
sed -i "s/PROJECT_ID/$PROJECT_ID/g" deploy/gcp/cloud-run-*.yaml
sed -i "s/CLOUD_SQL_PRIVATE_IP/$CLOUD_SQL_PRIVATE_IP/g" deploy/gcp/cloud-run-hapi.yaml
```

### 8. Deploy HAPI first (other services depend on its URL)

```bash
gcloud run services replace deploy/gcp/cloud-run-hapi.yaml --region=$REGION

# Wait for startup (HAPI boots in ~30s). Check:
HAPI_URL=$(gcloud run services describe vigil-hapi --region=$REGION --format='value(status.url)')
echo "HAPI URL (internal): $HAPI_URL"
```

Extract the project-hash from `$HAPI_URL` (e.g. `vigil-hapi-abc123de-uc.a.run.app`)
and patch it into the other three YAMLs:

```bash
PROJECT_HASH=$(echo "$HAPI_URL" | sed -E 's|https://vigil-hapi-([^.]+)\.a\.run\.app|\1|')
sed -i "s/PROJECT_HASH/$PROJECT_HASH/g" deploy/gcp/cloud-run-*.yaml
```

### 9. Deploy MCP, A2A, API

```bash
gcloud run services replace deploy/gcp/cloud-run-mcp.yaml --region=$REGION
gcloud run services replace deploy/gcp/cloud-run-a2a.yaml --region=$REGION
gcloud run services replace deploy/gcp/cloud-run-api.yaml --region=$REGION

# Allow unauthenticated access on the three public services (IAM binding is
# separate from the ingress setting; both must permit public).
for svc in vigil-mcp vigil-a2a vigil-api; do
  gcloud run services add-iam-policy-binding $svc \
    --region=$REGION \
    --member="allUsers" --role="roles/run.invoker"
done
```

### 10. Seed HAPI

HAPI is internal-only, so the seed script has to run from inside the VPC.
Easiest path: run the seeder as a one-shot Cloud Run Job, or shell into the
`vigil-api` service (which has the VPC connector) and call the seed module:

```bash
# Option 1 — one-shot from the api service (simplest during setup).
gcloud run jobs create vigil-seed \
  --image=us-central1-docker.pkg.dev/$PROJECT_ID/vigil/vigil:latest \
  --region=$REGION --vpc-connector=vigil-connector \
  --set-env-vars="FHIR_BASE_URL=$HAPI_URL/fhir" \
  --command="python" \
  --args="data/seed_hapi.py,--fhir-base,$HAPI_URL/fhir,--src,data/patients" \
  --service-account=vigil-run@$PROJECT_ID.iam.gserviceaccount.com
gcloud run jobs execute vigil-seed --region=$REGION --wait
```

### 11. Point the frontend at the new URLs

```bash
MCP_URL=$(gcloud run services describe vigil-mcp --region=$REGION --format='value(status.url)')
A2A_URL=$(gcloud run services describe vigil-a2a --region=$REGION --format='value(status.url)')
API_URL=$(gcloud run services describe vigil-api --region=$REGION --format='value(status.url)')

vercel env add NEXT_PUBLIC_BACKEND_URL   "$API_URL"
vercel env add NEXT_PUBLIC_MCP_URL       "$MCP_URL"
vercel env add NEXT_PUBLIC_A2A_URL       "$A2A_URL"
```

Also update `CORS_ORIGINS` in the three public services if your Vercel
domain is not `https://vigil-frontend.vercel.app`:

```bash
gcloud run services update vigil-api --region=$REGION \
  --set-env-vars="CORS_ORIGINS=https://<your-vercel-domain>,http://localhost:3000"
# repeat for vigil-mcp and vigil-a2a
```

### 12. Verify

```bash
# MCP tools list (requires API key)
curl -X POST "$MCP_URL/mcp" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $VIGIL_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# AgentCard (public, no key)
curl "$A2A_URL/.well-known/agent-card.json" | python -m json.tool

# API health
curl "$API_URL/api/health"

# HAPI from *inside* the VPC (should fail from laptop, succeed from vigil-api)
curl "$HAPI_URL/fhir/metadata"       # expect 403 from laptop — good
```

---

## Env var + secret checklist

| Service | Env vars (non-secret) | Secrets |
|---|---|---|
| `vigil-api` | `SERVICE=api`, `API_PORT=8080`, `FHIR_BASE_URL`, `A2A_AGENT_URL`, `LLM_PROVIDER`, `CORS_ORIGINS`, `LOG_LEVEL` | `VIGIL_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY` |
| `vigil-mcp` | `SERVICE=mcp`, `MCP_PORT=8080`, `FHIR_BASE_URL`, `LLM_PROVIDER`, `CORS_ORIGINS`, `CACHE_TTL_SEC`, `ALLOWED_FHIR_HOSTS`, `LOG_LEVEL` | `VIGIL_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY` |
| `vigil-a2a` | `SERVICE=a2a`, `A2A_PORT=8080`, `MCP_BASE_URL`, `FHIR_BASE_URL`, `A2A_PUBLIC_URL`, `POLL_INTERVAL_SEC`, `LOG_LEVEL` | `VIGIL_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY` |
| `vigil-hapi` | `spring.datasource.url`, `spring.datasource.username`, Spring/HAPI config | `hapi-db-password` |

Generate secrets in one go:

```bash
VIGIL_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

---

## Demo-day notes

- **Cold starts.** First request after idle adds 3–5s on the Python services,
  25–40s on HAPI. Keep `minScale=1` on `vigil-api`, `vigil-a2a`, and `vigil-hapi`
  during demo week (≈$5/service-month). Drop to 0 afterward.
- **Region.** `us-central1` is cheapest and latency-friendly for a US-based
  Prompt Opinion runtime. If judges are in Asia/EU, consider `asia-southeast1`
  or `europe-west4` — mirror our existing Fly.io `sin` region choice.
- **TLS.** Every Cloud Run service gets a valid cert on `*.a.run.app`.
- **Logs.** `gcloud run services logs tail vigil-api --region=$REGION`.

---

## Option B — GKE Autopilot (overkill for hackathon)

If you need multi-replica or long-lived WebSocket streaming beyond Cloud Run's
60-minute request cap, use GKE Autopilot. The shape would be 4 `Deployments`
+ 4 `Services`, a single `Ingress` with a managed cert on the public three,
and a private LoadBalancer for HAPI. Cloud SQL stays the same. Not recommended
here — Cloud Run covers every hackathon requirement and Autopilot adds
cluster-level cost (~$75/month per cluster) that eats free-trial credit.

## Option C — Compute Engine VM (fallback if Cloud Run hits a limit)

Single `e2-small` VM running `docker compose up` from the project's existing
`docker-compose.yml`, fronted by nginx for TLS (Let's Encrypt) and a static
public IP. Simplest to reason about; no auto-scale. Pick this only if HAPI
on Cloud Run turns out to be flakey under load — we already know HAPI is
stateful-unfriendly on serverless. VM cost is ~$14/month but runs always-on.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `vigil-mcp` 502 on `/mcp` | Check `gcloud run services logs read vigil-mcp` — most often `FHIR_BASE_URL` points at a wrong HAPI host |
| HAPI 403 from laptop | Expected — ingress=internal (SEC-10). Test from inside the VPC via `vigil-api` logs |
| `AgentCard` missing URL | Set `A2A_PUBLIC_URL` to the `$A2A_URL` from step 11 and redeploy |
| Cloud Build image push denied | Grant `roles/artifactregistry.writer` to `$PROJECT_ID@cloudbuild.gserviceaccount.com` |
| HAPI cold-starts kill the demo | Bump `cloud-run-hapi.yaml` `minScale` to `1` (already default in our config) |
| Cost alarm | `gcloud run services update <svc> --min-instances=0 --region=$REGION` on every service |
