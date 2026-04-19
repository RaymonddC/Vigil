# Vigil — Final Submission Checklist (P6)

Owner: integration-lead | Created: 2026-04-19 | Deadline: 2026-05-11

**Run this checklist at T-24h and again at T-2h. Two people sign off. No exceptions.**

Ref: `RISK_REGISTER.md §4`, `BUILD_PLAN.md §6`, `JUDGE_HOOKS.md §6`

**Source of truth for rules:** https://agents-assemble.devpost.com/rules

---

## Repository

| # | Item | Check | Signed off by | Notes |
|---|------|:-----:|:-------------:|-------|
| 1 | GitHub repo is **public** (not private, not internal) | [ ] | | Verify at `github.com/<owner>/vigil` — should show "Public" badge |
| 2 | GitHub repo topics set: `mcp`, `a2a`, `healthcare`, `fhir`, `hackathon` | [ ] | | Settings → General → Topics |
| 3 | `LICENSE` file present in repo root (MIT) | [ ] | | `cat LICENSE \| head -1` → "MIT License" |
| 4 | No PHI anywhere in repo history | [ ] | | Run: `git log --all -p \| grep -iE '(ssn\|mrn-[0-9]{4,})' \| head` — must be clean. Synthetic MRN-100001 format is OK. |
| 5 | No secrets committed (`.env`, API keys, credentials) | [ ] | | Run: `git ls-files \| grep -iE '\.env$'` — must return nothing. Verify `.gitignore` covers `.env`, `.env.local` |
| 6 | `.secrets.baseline` does not contain real secrets | [ ] | | Inspect — should only contain hash patterns, no plaintext keys |
| 7 | `README.md` is complete | [ ] | | Sections present: What / Why / Stack / Quickstart / FHIR resources / Architecture / Clinical standards / Evaluation / Demo script |

## Tests & Quality

| # | Item | Check | Signed off by | Notes |
|---|------|:-----:|:-------------:|-------|
| 8 | `uv run pytest -v` all green on main | [ ] | | Target: 312+ tests, 0 failures |
| 9 | `uv run ruff check backend/ tests/` clean (or only style warnings) | [ ] | | Run `--fix` for auto-fixable issues before submission |
| 10 | `make demo` works from a **fresh clone** | [ ] | | Clone to `/tmp/vigil-test`, run `make demo`, verify all 6 services start. Must complete in <5 min. |
| 11 | All 4 MCP tools callable via smoke test | [ ] | | With services running: `curl http://localhost:7001/health` → 200; MCP inspector shows 4 tools |
| 12 | A2A agent responds to health check | [ ] | | `curl http://localhost:9000/.well-known/agent-card.json` → valid AgentCard JSON |

## Demo & Video

| # | Item | Check | Signed off by | Notes |
|---|------|:-----:|:-------------:|-------|
| 13 | Demo video recorded, runtime **< 3:00** | [ ] | | Verify with stopwatch on playback, not trust. Hard ceiling — judges not required to watch beyond 3:00. |
| 14 | Video uploaded to YouTube as **Public** (not Unlisted) | [ ] | | Devpost requires "publicly visible" — go Public to avoid rejection. YouTube/Vimeo/Youku only. |
| 15 | Video has captions (SRT uploaded or burned-in) | [ ] | | YouTube auto-caption → download SRT → hand-edit clinical terms → re-upload. Burn in for social clips. |
| 16 | Video resolution ≥ 1080p, MP4 H.264 | [ ] | | No copyright music / no third-party trademarks in video |
| 17 | All 5 judge hooks present in video or README | [ ] | | Cross-reference `docs/JUDGE_HOOK_CHECK.md` — each judge has ≥3 hooks |

## Devpost Submission

| # | Item | Check | Signed off by | Notes |
|---|------|:-----:|:-------------:|-------|
| 18 | Devpost submission status: **Submitted** (not Draft) | [ ] | | Click "Submit" — drafts are NOT judged. Verify confirmation email. |
| 19 | Devpost fields complete | [ ] | | Required: title, text description, **Prompt Opinion Marketplace URL**, demo video link. See `docs/DEVPOST_SUBMISSION.md` for copy. |
| 20 | Devpost category: **Option B** | [ ] | | Agents Assemble hackathon, correct track selected |
| 21 | Devpost team roster correct — every member has accepted the invite | [ ] | | Check "Team" tab — all members show "Accepted", not "Pending" |
| 22 | All data in demo is synthetic / de-identified | [ ] | | Devpost rules require this explicitly — no real PHI in video or screenshots |

## Marketplace (REQUIRED by Devpost rules)

> **Devpost requires a Prompt Opinion Marketplace URL.** This is not optional — the submission form mandates that your project is "discoverable and invokable within the platform." If listing is blocked, execute KS-1 (see `RISK_REGISTER.md §3`).
>
> **Registration surface is unconfirmed.** PO homepage shows "Talk to Us" — no self-service publish button found. Join Discord (https://discord.gg/cCBxKpdS7j) and ask the 5 questions in `PROMPT_OPINION_INTEGRATION.md §8` ASAP.

| # | Item | Check | Signed off by | Notes |
|---|------|:-----:|:-------------:|-------|
| 23 | Prompt Opinion MCP listing (Path A) live and **URL in Devpost form** | [ ] | | Must be discoverable + invokable. Requires: public URL, `stateless_http=True`, `ai.promptopinion/fhir-context` capability advertised, `X-API-Key` middleware. |
| 24 | Prompt Opinion A2A listing (Path B) live and **URL in Devpost form** | [ ] | | AgentCard at `/.well-known/agent-card.json`, FHIR extension in `capabilities.extensions`, `X-API-Key` middleware. |
| 25 | Marketplace listings link back to GitHub repo | [ ] | | Verify bidirectional links: listing → repo AND README → listing |
| 26 | If KS-1 fired: "Marketplace listing pending" note in Devpost description with draft link | [ ] | | Fallback only — submit as GitHub repo + video if listing blocked at T-48h |

## Final verification

| # | Item | Check | Signed off by | Notes |
|---|------|:-----:|:-------------:|-------|
| 27 | Demo URL (if deployed) still reachable from fresh browser | [ ] | | Open incognito window, navigate to Vercel URL. If local-only, mark N/A. |
| 28 | Devpost description mentions: HAPI FHIR, MCP, A2A, and links repo + video + demo | [ ] | | All four protocols/tools named in description text |
| 29 | English language throughout (or translations provided) | [ ] | | Devpost rules require English |

---

## Sign-off log

| Run | Date | Time | Person 1 | Person 2 | Items failed | Resolution |
|-----|------|------|----------|----------|-------------|------------|
| T-24h | ___ | ___ | ___ | ___ | ___ | ___ |
| T-2h | ___ | ___ | ___ | ___ | ___ | ___ |

---

## Quick-fix playbook

If a checklist item fails at T-2h, use these pre-planned fixes:

| Item | Failure | Fix | Time |
|------|---------|-----|------|
| 1 | Repo still private | Settings → Danger Zone → Change visibility → Public | 1 min |
| 4 | PHI found | `git filter-repo` or BFG to scrub, force push | 30 min |
| 5 | .env committed | `git rm --cached .env && git commit` | 5 min |
| 8 | Tests failing | Fix or skip with `@pytest.mark.skip(reason="...")`, commit | 15 min |
| 10 | Fresh clone fails | Check `.env.example` has all required vars, `docker-compose.yml` pulls correct images | 30 min |
| 13 | Video > 3:00 | Re-export with tighter cuts; trim silence at start/end | 20 min |
| 14 | Video unlisted not public | YouTube Studio → Visibility → Public. Devpost requires "publicly visible". | 2 min |
| 15 | No captions | YouTube auto-generate → download SRT → upload alongside video | 15 min |
| 18 | Devpost still Draft | Click Submit. No excuses. KS-6: ship last clean take if video incomplete. | 2 min |
| 23-24 | Marketplace blocked | Execute KS-1: add "Marketplace listing pending" note to Devpost description with link to draft listing | 5 min |

---

## Post-submission verification (T+5 min)

After clicking Submit on Devpost:

- [ ] Refresh Devpost project page — shows "Submitted" status
- [ ] Video plays in embed (not just link)
- [ ] GitHub link opens to public repo
- [ ] README renders correctly on GitHub (no broken images/links)
- [ ] Marketplace listings (if live) are accessible without auth

---

*End of checklist. Two signatures required before submit.*
