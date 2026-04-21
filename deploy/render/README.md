# Vigil on Render.com (free tier, fixture mode)

One-click-ish deploy of the 4-service Vigil backend on Render's **free plan**
using the FHIR fixture server instead of HAPI. Everything runs inside 512 MB
per service. The frontend goes to Vercel (free, better fit for Next.js).

- **`vigil-fhir`** — FHIR fixture (HAPI replacement, ~50 MB RAM)
- **`vigil-mcp`** — MCP server (4 tools)
- **`vigil-a2a`** — A2A agent + AgentCard
- **`vigil-api`** — FastAPI proxy (dashboard backend)

---

## Why fixture instead of HAPI?

HAPI FHIR wants ~1 GB RAM and a Postgres database. Render's free tier caps
each web service at **512 MB RAM**, and its free Postgres tier **expires
after 90 days**. The fixture server serves the same synthetic
`data/patients/PT-*.json` bundles in HAPI-compatible search shapes, stays
well under 512 MB, and has no external database dependency. The trade-off
is read-only semantics: `/approve` cannot write `Communication` resources
to the fixture (it accepts the call but does not persist). For hackathon
judging that's fine — the approve path is demonstrated against the
dashboard's in-memory queue.

If you need persistence and can spend ~$10/month, use
[`deploy/gcp/`](../gcp/README.md) or [`docs/DEPLOY.md` Option B](../../docs/DEPLOY.md)
(Fly.io) for the full HAPI stack.

---

## Free tier limits — read this first

Render's free plan has a **shared 750 instance-hour budget per workspace
per calendar month**, spent across all free web services. Math for Vigil:

| Scenario | Hours/month | Fits in 750? |
|---|---|---|
| 4 services warm 24/7 | 2880 | No — overshoots by ~4× |
| 4 services warm 24/7 for just 1 demo week | ~670 | Yes |
| Services spun down when idle (free default) | ~0 when idle + request-time | Yes |
| 4 services warm for all of judging (May 8–11, ~4 days) | ~384 | Yes |

Render **does not charge for spun-down time**. Services spin down after 15
minutes of inbound-traffic silence; a cold request then takes ~1 minute to
bring the container back up. UptimeRobot (below) keeps them warm only when
you actively want them warm — turn its monitors off when you aren't
demoing, or you will burn the 750-hour budget.

**Recommended cadence for the hackathon:**

- Deploy and let services idle until ~4 days before the submission deadline.
- Turn on UptimeRobot monitors on **May 7** (submission deadline 2026-05-11).
- After submission, pause the monitors again.

Other free-tier limits (per Render's public docs, April 2026):
- 512 MB RAM per service — Vigil's Python services use ~150 MB each, fixture ~50 MB.
- Outbound bandwidth and build-pipeline minutes count against monthly allowances; exact numbers vary, but Vigil's traffic is negligible.
- Free plan only — no free `pserv` (private-only) type, which is why we use `web` services gated by `VIGIL_API_KEY`.

---

## 0. Prerequisites

1. A GitHub account with this repo forked or push access.
2. A Render account — sign up at <https://render.com/> with GitHub OAuth. **No credit card required** for free tier.
3. (Optional) An UptimeRobot account — <https://uptimerobot.com/> — also free, no CC.
4. A Vercel account for the frontend — <https://vercel.com/>, free hobby tier is plenty.

## 1. Generate a Vigil API key

This shared key protects MCP, A2A, and API requests (SEC-05).

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save the value — you will paste it into Render three times (once per service that reads it).

---

## Option A — Deploy via Blueprint (recommended)

1. In the Render dashboard, click **New → Blueprint**.
2. Connect your GitHub account if you haven't already, then pick the `Vigil` repo.
3. Render scans the repo, finds [`render.yaml`](../../render.yaml), and shows 4 services: `vigil-fhir`, `vigil-mcp`, `vigil-a2a`, `vigil-api`.
4. Render prompts for the `sync: false` environment variables. Fill in:
   - `VIGIL_API_KEY` — the value from step 1, same for all three callers (mcp / a2a / api).
   - `GROQ_API_KEY` — from <https://console.groq.com/keys>. Recommended for demo speed.
   - `ANTHROPIC_API_KEY` — from <https://console.anthropic.com/>. Leave blank if you only plan to demo on Groq.
   - `A2A_PUBLIC_URL` — **leave empty for now**, you fill it in after first deploy (step 3 below).
5. Click **Apply**. Render builds and deploys all four services. Expect ~8–12 minutes for the first build (the single Docker image is cached after that).

After the Blueprint apply completes, Render assigns each service a public URL like `https://vigil-<name>-<suffix>.onrender.com`. Collect them:

```
vigil-fhir → https://vigil-fhir-XXXX.onrender.com  (you won't normally hit this publicly)
vigil-mcp  → https://vigil-mcp-XXXX.onrender.com
vigil-a2a  → https://vigil-a2a-XXXX.onrender.com
vigil-api  → https://vigil-api-XXXX.onrender.com
```

### 2. Finish the A2A service

`A2A_PUBLIC_URL` is the URL the AgentCard advertises to external callers
(Prompt Opinion's runtime). Set it now that you know the actual A2A URL:

1. Open the `vigil-a2a` service in the Render dashboard → **Environment**.
2. Set `A2A_PUBLIC_URL` to the full public URL (e.g. `https://vigil-a2a-abcd.onrender.com`).
3. Click **Save, rebuild, and deploy**.

### 3. Smoke-test

```bash
# AgentCard should include the A2A_PUBLIC_URL you just set
curl https://vigil-a2a-XXXX.onrender.com/.well-known/agent-card.json | python -m json.tool

# API health
curl https://vigil-api-XXXX.onrender.com/api/health

# MCP tools list (requires API key)
curl -X POST https://vigil-mcp-XXXX.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $VIGIL_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Fixture patient bundle (should return PT-001)
curl https://vigil-fhir-XXXX.onrender.com/fhir/Patient/PT-001
```

If the first request returns `502 Bad Gateway` or takes ~60 seconds, the service is cold-starting — this is expected on free tier. Retry.

---

## Option B — Deploy each service via the dashboard (fallback)

Use this if the Blueprint step fails or Render changes the schema.

For each service (`vigil-fhir`, `vigil-mcp`, `vigil-a2a`, `vigil-api`):

1. **New → Web Service → Build and deploy from a Git repository.**
2. Pick the `Vigil` repo.
3. Fill in the form:
   - **Name**: one of `vigil-fhir` / `vigil-mcp` / `vigil-a2a` / `vigil-api`.
   - **Region**: Oregon (or match all four to the same region — the private network requires it).
   - **Branch**: `main`.
   - **Root Directory**: leave blank (use repo root).
   - **Runtime**: Docker.
   - **Dockerfile Path**: `./Dockerfile`.
   - **Instance Type**: Free.
4. **Environment**: paste the vars from `render.yaml` for that service. Copy-paste from there — it's the source of truth.
5. **Health Check Path**:
   - `vigil-fhir`: `/fhir/metadata`
   - `vigil-mcp`: `/health`
   - `vigil-a2a`: `/.well-known/agent-card.json`
   - `vigil-api`: `/api/health`
6. **Create Web Service**.

After all 4 are up, set `A2A_PUBLIC_URL` on `vigil-a2a` (same as Option A step 2).

---

## 4. Keep-alive with UptimeRobot

Free tier services sleep after 15 minutes of idle. UptimeRobot's free plan
allows up to 50 monitors with 5-minute intervals — more than enough.

1. Sign up at <https://uptimerobot.com/>.
2. **Add New Monitor** for each service:

   | Monitor name | Type | URL | Interval |
   |---|---|---|---|
   | vigil-mcp | HTTP(s) | `https://vigil-mcp-XXXX.onrender.com/health` | 5 min |
   | vigil-a2a | HTTP(s) | `https://vigil-a2a-XXXX.onrender.com/.well-known/agent-card.json` | 5 min |
   | vigil-api | HTTP(s) | `https://vigil-api-XXXX.onrender.com/api/health` | 5 min |

   (We intentionally do not poll `vigil-fhir` — it is reached over the
   private network from `vigil-mcp`, so keeping MCP warm keeps the fixture
   warm too, and skipping the fixture monitor saves ~192 instance-hours/month.)

3. **Cost control:** pause all three monitors when not in a demo window. Re-enable them ~4 days before the submission deadline (2026-05-11).

---

## 5. Deploy the Next.js frontend to Vercel

The frontend is not on Render — Vercel is a better fit for Next.js and is
free for hobby projects.

```bash
cd frontend
npm install -g vercel
vercel login
vercel link        # or `vercel` to create a new project

# Point the frontend at the Render backend
vercel env add NEXT_PUBLIC_BACKEND_URL   production
# paste: https://vigil-api-XXXX.onrender.com

vercel env add NEXT_PUBLIC_MCP_URL       production
# paste: https://vigil-mcp-XXXX.onrender.com

vercel env add NEXT_PUBLIC_A2A_URL       production
# paste: https://vigil-a2a-XXXX.onrender.com

vercel --prod
```

Then update the `CORS_ORIGINS` env var on each Render service to include
your Vercel production domain (default assumed: `https://vigil-frontend.vercel.app`):

```
CORS_ORIGINS=https://<your-vercel-domain>,http://localhost:3000
```

Render auto-redeploys after each env var change; wait ~2 minutes for it to settle.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| First request returns 502 / hangs for 60s | Cold start — expected on free tier. Retry. Enable UptimeRobot to keep services warm. |
| MCP returns `SSRF blocked: FHIR server URL 'http://vigil-fhir:8080'` | Add that origin to `ALLOWED_FHIR_HOSTS` (already in `render.yaml`; check for typos in your override). |
| AgentCard shows `"url": "http://localhost:9000"` | `A2A_PUBLIC_URL` is unset — see Option A step 2. |
| All services restart constantly | Likely OOM. Check the service logs for `Killed` / exit code 137. The fixture stays small, but MCP+A2A+API each nudge 150 MB. If your image grows, trim dev deps in `pyproject.toml`. |
| "You've exceeded your free monthly limit" | Workspace used >750 instance-hours. Pause UptimeRobot monitors and wait for the monthly reset, or upgrade one service to Starter ($7/mo). |
| Fixture does not return PT-009 bundle | Confirm `data/patients/PT-009.json` is committed to the repo (the Dockerfile `COPY data/ data/` bakes it in). |
| `vigil-mcp` cannot reach `vigil-fhir` | Both must be in the same Render region (Oregon in the Blueprint). Verify in each service's **Settings**. |

---

## Cost & limits summary

| Item | Free tier? | Notes |
|---|---|---|
| 4 web services (Docker) | Yes | Subject to shared 750 instance-hours / month per workspace |
| 512 MB RAM each | Yes | Fixture ~50 MB, Python services ~150 MB each — fits comfortably |
| Outbound bandwidth | Yes, metered | Negligible for hackathon-scale traffic |
| Private inter-service network | Yes | `http://vigil-fhir:8080` resolves from peers in same region |
| HTTPS + managed TLS on `*.onrender.com` | Yes | Certificates auto-issued |
| Custom domain | Yes | Available on free tier; not required for the hackathon |
| Persistent storage / Postgres | **No** (90-day free Postgres expires) | Fixture avoids this entirely |
| UptimeRobot keep-alive | Yes (free 50 monitors @ 5-min) | Pause outside demo windows to stay under 750h |

For the submission deadline 2026-05-11, the recommended posture is:
deploy now, leave monitors off, turn them on 2026-05-07, turn off again
after submission.
