# Vigil on AWS EC2 (single `c7i-flex.large` instance)

All-in-one Vigil deploy: HAPI + the three Python services + Next.js frontend,
fronted by Caddy with auto Let's Encrypt TLS, on a single 4 GB Intel
EC2 instance. Target for users with the $100 AWS credit who want a
persistent HAPI store and a single domain for the Prompt Opinion listing.

- **Instance:** `c7i-flex.large` (2 vCPU, 4 GiB, Intel Sapphire Rapids)
- **OS:** Ubuntu 22.04 LTS
- **Storage:** 30 GB gp3 EBS
- **Monthly cost (always-on):** ~$55 compute + ~$2.40 EBS ≈ **$58/mo**
- **For a 17-day judging window (always-on):** ~17/30 × $58 ≈ **$33**
  — comfortably inside $100 credit, with headroom for a week of testing.

> **First-run warning.** This is the first time the full extended
> docker-compose (HAPI + mcp + a2a + api + frontend + caddy) is exercised
> end-to-end. Expect to iterate once during first boot — the runbook in
> §D below lists the commands for triage.

---

## Architecture

```
┌─── c7i-flex.large (Ubuntu 22.04, 4 GB) ───────────────────────────┐
│                                                                    │
│  Caddy :80 :443  ← the ONLY publicly exposed ports                 │
│     ├─ /.well-known/agent-card.json  → a2a:9000                    │
│     ├─ /a2a*                          → a2a:9000                    │
│     ├─ /mcp*    + /health             → mcp:7001                    │
│     ├─ /api*                          → api:8000                    │
│     └─ /*                             → frontend:3000               │
│                                                                    │
│  Internal docker network:                                          │
│     hapi-db (postgres)  ─┐                                         │
│     hapi (HAPI FHIR)    ─┘  127.0.0.1:8080 — NEVER public         │
│     mcp, a2a, api       Python services                           │
│     frontend            Next.js 16 prod build                      │
└────────────────────────────────────────────────────────────────────┘
```

HAPI stays off the public network (SEC-10). The Caddy reverse proxy has
the only public sockets; everything else is reachable only over the
docker-internal network or via ssh port forwarding from your laptop.

---

## A. Account prep

1. Log in at <https://console.aws.amazon.com/>. New account users get
   [AWS Free Tier](https://aws.amazon.com/free/) (12 months of some
   services including 750 hr/mo of t2.micro/t3.micro — **not
   c7i-flex.large**, so this deploy will draw down the $100 credit).
2. Confirm your credit balance at
   [Billing → Credits](https://console.aws.amazon.com/billing/home#/credits).
3. Set a **Zero-Spend** budget alert at
   [Budgets](https://console.aws.amazon.com/billingconservation/home#/budgets/create?type=cost)
   — optional safety net if your credit runs out.
4. Pick a region close to you (this guide assumes `us-east-1`). Keep
   everything in one region to avoid inter-region egress charges.

---

## B. Launch the instance

Console walkthrough (replace with Terraform if you prefer — the
user-data script is the only non-trivial bit):

1. **EC2 → Launch instance**
2. **Name:** `vigil-prod`
3. **AMI:** *Ubuntu Server 22.04 LTS (HVM), SSD Volume Type* — the
   "Free tier eligible" 22.04 image (ARM or x86 — **pick x86** to match
   c7i-flex.large).
4. **Instance type:** `c7i-flex.large` (2 vCPU, 4 GiB).
5. **Key pair:** create or reuse an RSA/ED25519 key. You'll need
   `chmod 400 vigil-prod.pem` locally to SSH.
6. **Network settings → Edit**:
   - VPC: default is fine.
   - Auto-assign public IP: **Enable**.
   - **Security group (create new)** — `vigil-prod-sg`:

     | Type  | Protocol | Port | Source     | Note |
     |-------|----------|------|------------|------|
     | SSH   | TCP      | 22   | My IP      | replace with your current IPv4/32 |
     | HTTP  | TCP      | 80   | 0.0.0.0/0  | Let's Encrypt HTTP-01 + HTTP→HTTPS redirect |
     | HTTPS | TCP      | 443  | 0.0.0.0/0  | public traffic |

     Do **NOT** open 8080 (HAPI), 7001 (MCP), 9000 (A2A), 8000 (API),
     or 3000 (frontend). Caddy handles all public traffic on 80/443.

7. **Configure storage:** 1 × 30 GiB gp3 root volume (keep defaults
   otherwise).
8. **Advanced details → User data**: paste the contents of
   [`deploy/aws/user-data.sh`](./user-data.sh).
   - Before you paste, edit these vars at the top of the script:
     - `SITE_DOMAIN` (see §C) — or leave blank for sslip.io auto-derivation.
     - `LLM_PROVIDER` + `GROQ_API_KEY` or `ANTHROPIC_API_KEY`.
9. **Launch instance.** Provisioning takes ~30 s; cloud-init runs for
   ~3–5 min after that.

---

## C. Domain / TLS options

Caddy obtains a Let's Encrypt cert automatically, but it needs a
hostname that resolves to the EC2 public IP. Three paths:

### Option (a) — You own a domain *(production posture)*

1. Grab the instance's **public IPv4** from the EC2 console.
2. At your DNS registrar, add an **A record**:
   ```
   vigil.example.com.   A   <EC2-public-IP>   TTL 300
   ```
3. Set `SITE_DOMAIN="vigil.example.com"` in `user-data.sh` (or in
   `/opt/vigil/.env` if you're editing after launch).
4. Wait 1–5 min for DNS to propagate, then restart Caddy:
   `docker compose restart caddy`.

### Option (b) — sslip.io wildcard *(recommended for the hackathon)*

[`sslip.io`](https://sslip.io/) is a free DNS service that resolves
`1-2-3-4.sslip.io` to `1.2.3.4` — no account, no cost. Let's Encrypt
issues certs against sslip.io subdomains via HTTP-01.

Leave `SITE_DOMAIN=""` in `user-data.sh` — the script auto-derives
`<public-ip-with-dashes>.sslip.io` from EC2 instance metadata on first
boot. The resulting URL looks like:

```
https://3-221-45-127.sslip.io
```

> **Caveat.** sslip.io is a community service. If it's ever down,
> Let's Encrypt renewal will fail. Swap to option (a) for the final
> submission if you have a domain handy.

### Option (c) — Plain HTTP *(testing only)*

Set `SITE_DOMAIN=":80"`. Caddy listens on 80 only, no TLS, URL is
`http://<EC2-IP>`. **Prompt Opinion Marketplace requires HTTPS**, so
this won't work for the real submission — use for local smoke tests only.

---

## D. Verify the deploy

1. Watch cloud-init progress:
   ```bash
   ssh -i vigil-prod.pem ubuntu@<EC2-IP>
   tail -f /var/log/cloud-init-output.log
   ```
   You're looking for the `==============================================================`
   banner printed at the end of `user-data.sh`. The VIGIL_API_KEY and
   public URL are in that banner.

2. Confirm containers are healthy:
   ```bash
   cd /opt/vigil
   docker compose ps
   # All 7 rows should show "Up (healthy)" or "Up".
   # HAPI takes ~60 s; the Next.js build can push first-boot time to
   # ~3-5 min on 2 vCPU.
   ```

3. Smoke-test from your laptop:
   ```bash
   SITE=https://<your-site-domain>

   # 1. Frontend renders
   curl -I $SITE/

   # 2. FastAPI health
   curl $SITE/api/health | jq

   # 3. AgentCard — should advertise the A2A_PUBLIC_URL you set
   curl $SITE/.well-known/agent-card.json | jq

   # 4. MCP tool list (needs the API key from the cloud-init log)
   curl -X POST $SITE/mcp \
     -H "Content-Type: application/json" \
     -H "X-API-Key: <paste-from-cloud-init-log>" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq
   ```

4. If Caddy is still provisioning the cert, you'll see a self-signed
   warning. Wait ~60 s and retry; Caddy serves a fresh cert once the
   HTTP-01 challenge completes. Logs:
   ```bash
   docker compose logs -f caddy
   ```

### Common first-boot issues

| Symptom | Fix |
|---|---|
| `docker compose ps` shows nothing | cloud-init still running — `tail /var/log/cloud-init-output.log` |
| Caddy loops retrying HTTP-01 | DNS not propagated yet, or security group doesn't allow :80 from `0.0.0.0/0` |
| `frontend` restarts repeatedly | Next.js build OOMed on first boot. `docker compose build frontend` manually and retry |
| MCP returns `SSRF blocked` | `ALLOWED_FHIR_HOSTS` doesn't include `http://hapi:8080/fhir`. Check `.env` override. |
| AgentCard shows `http://localhost:9000` | `A2A_PUBLIC_URL` unset or wrong in `.env` — fix and `docker compose restart a2a` |

---

## E. Register with Prompt Opinion

Follow [`docs/PO_PUBLISHING_RESEARCH.md`](../../docs/PO_PUBLISHING_RESEARCH.md)
§ "Confirmed Publishing Flow". URLs to paste:

| Field | Value |
|---|---|
| Agent Card URL | `https://<SITE_DOMAIN>/.well-known/agent-card.json` |
| MCP endpoint   | `https://<SITE_DOMAIN>/mcp` |
| API key header | `X-API-Key: <from cloud-init log>` |

After submission the Prompt Opinion runtime will call the MCP endpoint
with the SHARP headers set — Vigil's MCP server reads `FHIR_BASE_URL`,
`Authorization`, and patient IDs per-call, overriding the baked-in
`http://hapi:8080/fhir`.

---

## F. Stop / start / teardown runbook

Compute charges only accrue while the instance is **running**. Stopping
drops you to ~$2.40/mo for the EBS volume.

### Stop (preserve data)

```bash
# Find the instance id
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=vigil-prod" \
  --query 'Reservations[].Instances[].InstanceId' --output text

aws ec2 stop-instances --instance-ids i-xxxxxxxxxxxxxxxxx
```

Or console: **EC2 → Instances → vigil-prod → Instance state → Stop instance**.

### Start again

```bash
aws ec2 start-instances --instance-ids i-xxxxxxxxxxxxxxxxx
```

**The public IP changes on each stop/start** unless you attach an
Elastic IP. With sslip.io, just re-derive the domain:
```bash
ssh ubuntu@<new-ip>
NEW_IP=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/public-ipv4)
NEW_DOMAIN="${NEW_IP//./-}.sslip.io"
sed -i "s|^SITE_DOMAIN=.*|SITE_DOMAIN=$NEW_DOMAIN|" /opt/vigil/.env
sed -i "s|^A2A_PUBLIC_URL=.*|A2A_PUBLIC_URL=https://$NEW_DOMAIN|" /opt/vigil/.env
cd /opt/vigil && docker compose up -d
```

If you're using your own domain, either attach an Elastic IP (~$3.60/mo
when attached to a stopped instance) or update the A record on each restart.

### Teardown

```bash
# 1. Terminate the instance (also deletes the root EBS by default)
aws ec2 terminate-instances --instance-ids i-xxxxxxxxxxxxxxxxx

# 2. Confirm no lingering volumes
aws ec2 describe-volumes \
  --filters "Name=tag:Name,Values=vigil-prod" \
  --query 'Volumes[].VolumeId'

# 3. Delete the security group
aws ec2 delete-security-group --group-name vigil-prod-sg

# 4. Delete the key pair (if not reusing)
aws ec2 delete-key-pair --key-name vigil-prod
```

---

## G. Credit / cost monitoring

Set a **CloudWatch billing alarm at $90** so you get a warning before
the credit runs out.

1. **CloudWatch → Alarms → Create alarm** (in `us-east-1` —
   billing metrics only publish there).
2. **Select metric → Billing → Total Estimated Charge → Currency=USD**.
3. Threshold type: static, >= 90, period 6 hours.
4. Action: SNS topic to your email (confirm subscription).
5. Name: `vigil-credit-burn-warning`.

Alternatively, [AWS Budgets](https://console.aws.amazon.com/billing/home#/budgets)
can email you when **actual or forecast** spend crosses thresholds.

Day-to-day cost check:
- [Billing → Bills](https://console.aws.amazon.com/billing/home#/bills)
  — the current month's accrued spend, updated ~daily.
- [Billing → Free Tier](https://console.aws.amazon.com/billing/home#/freetier)
  — tracks Free Tier consumption specifically.

---

## Back to top-level deploy options

See [`docs/DEPLOY.md`](../../docs/DEPLOY.md) for Render.com, Fly.io, GCP
Cloud Run alternatives.
