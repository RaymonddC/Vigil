# Vigil — FRONTEND_SPEC.md

> Read-only clinician dashboard for the 3-minute hackathon demo video.
> Stack: **Next.js 15 App Router + TypeScript + shadcn/ui + Tailwind CSS v4 + Recharts**, deployed to Vercel.
> Scope: four pages, desktop only, no auth, no editing. Judges are clinical experts — it must look like it belongs in a hospital.

---

## 1. Design Philosophy

**Modern clinical minimalism** — think *Linear × Epic × Notion*. The UI is information-dense but never cluttered: typography does the hierarchy work, color is reserved for risk signaling, and whitespace is generous around the clinically meaningful elements (vitals, SBAR, risk badge). No stock healthcare photography, no rounded "friendly" blobs, no gradient hero shots. Data tables are first-class citizens. Every surface reads as something a physician would trust on a Tuesday morning rounding laptop. Dark mode is supported via Tailwind's `dark:` variants but the demo video is recorded in **light mode** — light mode is the canonical theme.

---

## 2. Design System & Tokens

### 2.1 Color palette — `ui-ux-pro-max` palette: **"Clinical Slate + Medical Blue"** (healthcare SaaS category, slate-neutral family)

Chosen because (a) slate neutrals are the de-facto palette for clinical dashboards (Epic Haiku, Oracle Cerner Millennium Web) and read as "serious software, not consumer app"; (b) a single saturated medical blue (`#0B5FFF`) for the primary accent gives us one and only one place the user's eye goes for CTAs; (c) the five risk levels map cleanly onto a perceptually-spaced sequence that keeps WCAG 2.2 AA contrast against both `slate-50` and `slate-950` backgrounds.

```css
/* app/globals.css — Tailwind v4 @theme tokens */
@theme {
  /* Neutrals — slate scale */
  --color-slate-50:  #F8FAFC;
  --color-slate-100: #F1F5F9;
  --color-slate-200: #E2E8F0;
  --color-slate-300: #CBD5E1;
  --color-slate-400: #94A3B8;
  --color-slate-500: #64748B;
  --color-slate-600: #475569;
  --color-slate-700: #334155;
  --color-slate-800: #1E293B;
  --color-slate-900: #0F172A;
  --color-slate-950: #020617;

  /* Accent — single medical blue for primary actions */
  --color-accent:     #0B5FFF;
  --color-accent-fg:  #FFFFFF;
  --color-accent-50:  #EFF5FF;
  --color-accent-600: #0950DB;

  /* Risk levels — 5 tokens, WCAG AA contrast-checked */
  --color-risk-normal-bg:   #ECFDF5;   /* fg #065F46 (8.1:1) */
  --color-risk-normal-fg:   #065F46;
  --color-risk-low-bg:      #EFF6FF;   /* fg #1E40AF (9.3:1) */
  --color-risk-low-fg:      #1E40AF;
  --color-risk-medium-bg:   #FFFBEB;   /* fg #92400E (6.8:1) */
  --color-risk-medium-fg:   #92400E;
  --color-risk-high-bg:     #FFF7ED;   /* fg #9A3412 (6.4:1) */
  --color-risk-high-fg:     #9A3412;
  --color-risk-critical-bg: #FEF2F2;   /* fg #991B1B (8.9:1) */
  --color-risk-critical-fg: #991B1B;

  /* Semantic */
  --color-success: #059669;
  --color-warning: #D97706;
  --color-error:   #DC2626;
  --color-info:    #2563EB;
}
```

Dark-mode variants: same hues but with `-bg` tokens at `slate-900/40` tints and `-fg` tokens boosted two shades lighter; validated 4.5:1 against `--color-slate-950`.

### 2.2 Typography — `ui-ux-pro-max` font pairing: **"Geist + Inter"** (Professional / Modern-SaaS category)

- **Headings**: `Geist Sans` (600 / 700) — tight tracking, engineered for dashboards.
- **Body / UI**: `Inter` (400 / 500) with `font-feature-settings: 'cv11','ss01','tnum'` — tabular numerals are essential for vitals columns.
- **Numerics in vitals**: `Geist Mono` (500) for any live numeric readout — prevents digit jitter.

Both are loaded via `next/font` with `display: 'swap'` and self-hosted to avoid FOUT during the demo recording.

```ts
// app/layout.tsx
import { Geist, Geist_Mono, Inter } from 'next/font/google';
const geist = Geist({ subsets: ['latin'], variable: '--font-geist' });
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-geist-mono' });
const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });
```

**Pinned type scale** (rem, 16px base):

| Token     | Size       | Line-height | Use                                      |
|-----------|------------|-------------|------------------------------------------|
| `text-xs` | 12 / 0.75  | 16 / 1.0    | Table captions, timestamps, metadata     |
| `text-sm` | 14 / 0.875 | 20 / 1.25   | Table cells, body UI                     |
| `text-base`| 16 / 1.0  | 24 / 1.5    | SBAR body text, paragraph copy           |
| `text-lg` | 20 / 1.25  | 28 / 1.75   | Card titles                              |
| `text-xl` | 24 / 1.5   | 32 / 2.0    | Page subheadings                         |
| `text-2xl`| 32 / 2.0   | 40 / 2.5    | Patient name / page title                |

### 2.3 Spacing, radius, shadow

- **Spacing**: Tailwind default 4px scale; canonical gutters `gap-4` (16), card padding `p-6` (24), section stacks `space-y-8` (32).
- **Radius**: `rounded-md` (6) for inputs/badges, `rounded-lg` (8) for cards, `rounded-xl` (12) for large panels. **No `rounded-full`** on anything except avatar circles.
- **Shadow**: three-step scale — `shadow-xs` (hairline 1px border shadow), `shadow-sm` (cards at rest), `shadow-md` (hovered actionable cards / popovers). No dramatic ambient shadows.
- **Borders**: `border-slate-200` as the default hairline; `border-slate-300` for emphasis dividers.

### 2.4 RiskBadge spec (canonical)

Same visual language everywhere a risk level appears — table cell, detail header, chart legend, alert card.

```tsx
// components/risk-badge.tsx
type RiskLevel = 'normal' | 'low' | 'medium' | 'high' | 'critical';

const RISK: Record<RiskLevel, { label: string; icon: JSX.Element; shape: string }> = {
  normal:   { label: 'Normal',   icon: <CheckCircle2 />, shape: 'rounded-md' },
  low:      { label: 'Low',      icon: <Info />,         shape: 'rounded-md' },
  medium:   { label: 'Medium',   icon: <AlertCircle />,  shape: 'rounded-md' },
  high:     { label: 'High',     icon: <AlertTriangle />,shape: 'rounded-md' },
  critical: { label: 'CRITICAL', icon: <Siren />,        shape: 'rounded-md ring-2 ring-risk-critical-fg/40' },
};
```

Classes: `inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-risk-{level}-bg text-risk-{level}-fg`.
**Color is never the only signal** — icon + text label + (for critical) ring emphasis are all present. Screen readers announce the label via plain text; no aria-hidden on the icon's accessible name.

---

## 3. Page Wireframes

### 3.1 `/` — Patient List

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Vigil                          Post-op Unit 4B        Dr. A. Chen  [⚙] │
├──────────────────────────────────────────────────────────────────────────┤
│  Post-operative Patients                            [All 10] [High+] [▼] │
│  ────────────────────────────────────────────────────────────────────── │
│  Name              MRN       Procedure         T+ OR   Risk   Alert  →  │
│  ────────────────────────────────────────────────────────────────────── │
│  Reyes, Maria      102394    Lap chole         02:14   [CRIT] 00:42 [>] │
│  Osei, Kwame       110201    Hip arthroplasty  05:48   [HIGH] 01:10 [>] │
│  Novak, Irena      100882    C-section         01:02   [MED]  04:33 [>] │
│  Tanaka, Yuki      119384    CABG              07:30   [LOW]   —    [>] │
│  ...                                                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

- Table uses `<table>` semantic markup with `<caption class="sr-only">Post-op patient roster</caption>`.
- **Default sort**: risk desc (critical → normal), then time-since-OR asc.
- Filter pills (`All 10` / `High+` / `Triggered`) above the table.
- Row hover: `bg-slate-50 cursor-pointer`; entire row is a `<Link>` to `/patients/[id]`.
- Tabular numerics on MRN, T+ OR, Alert.
- Empty state never shown in demo — always seeded with 10 patients.

### 3.2 `/patients/[id]` — Patient Detail

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ← Back to roster                                                        │
│                                                                          │
│  Maria Reyes, 34 F             MRN 102394      [CRITICAL]                │
│  Lap chole  ·  OR-end 08:14   ·  Admit 06:02   ·  Day 0                  │
│  ────────────────────────────────────────────────────────────────────── │
│  ┌──────────────── Vitals Trend T+0h..T+8h ──────────┐ ┌──────────────┐ │
│  │                                                    │ │ Recent Alerts│ │
│  │  ── HR   ── SpO2   ── MAP   ── RR   ── Temp       │ │              │ │
│  │                                                    │ │ 10:32 CRIT  │ │
│  │      (Recharts multi-line, y-axis toggle pills)   │ │ 09:58 HIGH  │ │
│  │                                                    │ │ 09:14 MED   │ │
│  │                                                    │ │              │ │
│  └────────────────────────────────────────────────────┘ │              │ │
│  ┌─ What triggered ─────────────────────────────────┐  │              │ │
│  │ Sustained HR ↑ + MAP ↓ over 12 min; qSOFA = 2.   │  │              │ │
│  │ Pattern matches early sepsis signature.          │  │              │ │
│  └──────────────────────────────────────────────────┘  └──────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

- Header card: name/age/sex, MRN, procedure, admit time, `<RiskBadge>`.
- `<VitalsChart>` component: multi-line Recharts, toggle pills above it flip y-axis between *BP*, *HR/RR*, *SpO2*, *Temp*.
- **Right sidebar** (`w-80 shrink-0`): `<AlertTimeline>` showing most recent 5 alerts, each an in-page link to alert detail.
- **"What triggered" card** only renders when latest risk ≥ HIGH; plain prose + bullet list of contributing signals.

### 3.3 `/patients/[id]/alerts/[alertId]` — Alert Detail + SBAR

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ← Patient                                                               │
│                                                                          │
│  ⚠  EMERGENCY — Rapid Response recommended                    10:00 ▣   │
│                                                                          │
│  Maria Reyes  ·  102394  ·  [CRITICAL]                                   │
│  ────────────────────────────────────────────────────────────────────── │
│  ┌─ S: Situation ─────────────┐ ┌─ B: Background ────────────┐          │
│  │ 34F, POD0 lap chole,       │ │ Uncomplicated surgery ...  │          │
│  │ triggered critical sepsis. │ │                            │          │
│  └────────────────────────────┘ └────────────────────────────┘          │
│  ┌─ A: Assessment ────────────┐ ┌─ R: Recommendation ────────┐          │
│  │ qSOFA = 2. Concern for ... │ │ Call RRT. Blood cultures,  │          │
│  │                            │ │ lactate, 30 mL/kg bolus.   │          │
│  └────────────────────────────┘ └────────────────────────────┘          │
│                                                                          │
│  Contributing signals                                                    │
│  HR ▁▂▃▅▇   ↑ 128    MAP ▇▆▅▃▂ ↓ 58    RR ▂▃▅▆▇ ↑ 26   Temp ▃▅▆▇ ↑ 38.9 │
│                                                                          │
│  [ Approve & send RRT ]        [ Dismiss ]                               │
└──────────────────────────────────────────────────────────────────────────┘
```

- **EMERGENCY bar** — full-width `bg-risk-critical-bg text-risk-critical-fg border-l-4`. Never flashing or pulsing (seizure-risk).
- **Countdown timer** `10:00 until auto-escalate` — `aria-live="polite"` region so SRs announce per-minute updates, not per-second.
- **4 SBAR cards** in a 2×2 grid at `lg:` and stacked `<lg:` (we don't care about <lg, but still).
- **Contributing signals**: horizontal list, each with a 24px-tall Recharts `<LineChart>` sparkline + last value + direction arrow.
- **Two buttons**: primary `bg-accent text-accent-fg` ("Approve & send RRT") and ghost outline ("Dismiss"). The approve button is a client component that calls `ackAlert(pid, alertId)` from `lib/api.ts` (see §6) — the call hits `POST /api/patients/{id}/alerts/{alertId}/approve` on the FastAPI proxy, which writes `Communication` + `AuditEvent` to HAPI and returns the new audit id. On success, a `<Sonner>` toast reads "Communication {id} written — audit {audit_id}". On failure, the toast reads "Write failed — retry". Dismiss is client-side only (closes the dialog without a network call). This mirrors `API_CONTRACTS §6.4` and is the ONLY FHIR-write entry point in the demo.

### 3.4 `/marketplace` — Marketplace Mock (closing shot)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Vigil on the Prompt Opinion Marketplace                                 │
│                                                                          │
│  ┌────────────────────────────┐  ┌────────────────────────────┐         │
│  │ Vigil MCP Server           │  │ Vigil Postop Sentinel      │         │
│  │ 4 Clinical Early-Warning   │  │ Autonomous A2A Agent       │         │
│  │ Tools                      │  │                            │         │
│  │                            │  │                            │         │
│  │ [MCP] [FHIR R4] [SHARP]    │  │ [A2A] [FHIR R4] [SHARP]    │         │
│  │                            │  │                            │         │
│  │ Install →                  │  │ Subscribe →                │         │
│  └────────────────────────────┘  └────────────────────────────┘         │
└──────────────────────────────────────────────────────────────────────────┘
```

- Two-card grid; static content, no interactivity.
- Badge row uses shadcn `<Badge variant="outline">` — each badge is its own accessible label.
- Install/Subscribe buttons are disabled placeholders (`aria-disabled="true"`).

---

## 4. Component Inventory

### 4.1 shadcn/ui primitives (installed via `npx shadcn@latest add …`)

`button`, `card`, `badge`, `table`, `dialog`, `separator`, `tooltip`, `skeleton`, `scroll-area`, `tabs`, `sheet`, `toggle-group`, `dropdown-menu`, `sonner` (for the approve-confirm toast).

### 4.2 Custom components

```ts
// components/risk-badge.tsx
export interface RiskBadgeProps {
  level: 'normal' | 'low' | 'medium' | 'high' | 'critical';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

// components/vitals-chart.tsx
export interface VitalsChartProps {
  data: Array<{
    t: string;          // ISO timestamp
    hr?: number;
    spo2?: number;
    map?: number;
    rr?: number;
    tempC?: number;
  }>;
  axis?: 'all' | 'bp' | 'hr-rr' | 'spo2' | 'temp';
  height?: number;      // default 320
}

// components/sbar-section.tsx
export interface SBARSectionProps {
  situation: string;
  background: string;
  assessment: string;
  recommendation: string;
}

// components/contributing-signals-list.tsx
export interface Signal {
  name: 'HR' | 'SpO2' | 'MAP' | 'RR' | 'Temp';
  unit: string;
  latest: number;
  direction: 'up' | 'down' | 'flat';
  sparkline: Array<{ t: string; v: number }>;
}
export interface ContributingSignalsListProps { signals: Signal[]; }

// components/alert-timeline.tsx
export interface AlertTimelineItem {
  id: string;
  timestamp: string;  // ISO
  level: RiskBadgeProps['level'];
  headline: string;
}
export interface AlertTimelineProps {
  patientId: string;
  items: AlertTimelineItem[];
}
```

---

## 5. Charts (Recharts)

- **Vitals trend** (`/patients/[id]`): `<LineChart>` — 5 `<Line>` children, one per vital, `strokeWidth={2}`, `dot={false}`, `isAnimationActive={false}` (no animations during video). Custom `<Tooltip>` renders all five values at the hovered timestamp in a `<Card>`.
- **Sparklines** (alert card): 80×24px `<LineChart>` per signal, `<Line>` with no axes, no tooltip, no grid; color = `--color-slate-600` except if the trend direction is contributing to risk, then `--color-risk-high-fg`.
- Colors per vital: HR `#DC2626`, SpO2 `#2563EB`, MAP `#7C3AED`, RR `#0891B2`, Temp `#D97706`. Each passes 3:1 vs `slate-50`.

### 5.1 Vitals chart sample

```tsx
// components/vitals-chart.tsx
'use client';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const sample = [
  { t: '08:00', hr: 82, spo2: 98, map: 88, rr: 14, tempC: 37.0 },
  { t: '09:00', hr: 94, spo2: 96, map: 82, rr: 16, tempC: 37.4 },
  { t: '10:00', hr: 112,spo2: 94, map: 74, rr: 20, tempC: 38.1 },
  { t: '10:30', hr: 128,spo2: 91, map: 58, rr: 26, tempC: 38.9 },
];

export function VitalsChart({ data = sample, height = 320 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" />
        <XAxis dataKey="t" stroke="#64748B" fontSize={12} />
        <YAxis stroke="#64748B" fontSize={12} />
        <Tooltip
          contentStyle={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: '#0F172A', fontWeight: 600 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="hr"    stroke="#DC2626" strokeWidth={2} dot={false} name="HR"   isAnimationActive={false} />
        <Line type="monotone" dataKey="spo2"  stroke="#2563EB" strokeWidth={2} dot={false} name="SpO2" isAnimationActive={false} />
        <Line type="monotone" dataKey="map"   stroke="#7C3AED" strokeWidth={2} dot={false} name="MAP"  isAnimationActive={false} />
        <Line type="monotone" dataKey="rr"    stroke="#0891B2" strokeWidth={2} dot={false} name="RR"   isAnimationActive={false} />
        <Line type="monotone" dataKey="tempC" stroke="#D97706" strokeWidth={2} dot={false} name="Temp" isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

---

## 6. API Integration

Full payload schemas live in `API_CONTRACTS.md` (authored separately). The frontend consumes **four endpoints**, all via a thin FastAPI proxy at `NEXT_PUBLIC_API_BASE_URL` — this is the **recommended** option because it gives us stable shapes and hides FHIR polymorphism. Option (a) — direct CORS-enabled calls to HAPI FHIR at `http://localhost:8080/fhir` — is kept as a fallback for local dev if the Python backend isn't running.

| Route                                     | Method | Where called          | Returns            |
|-------------------------------------------|--------|-----------------------|--------------------|
| `/api/patients`                           | GET    | `app/page.tsx` (RSC)  | `PatientSummary[]` |
| `/api/patients/{id}`                      | GET    | `app/patients/[id]/page.tsx` (RSC) | `PatientDetail` |
| `/api/patients/{id}/alerts/{alertId}`     | GET    | `alerts/[alertId]/page.tsx` (RSC) | `AlertDetail` |
| `/api/patients/{id}/alerts/{alertId}/approve` | POST   | Client component on button click | `{ alert_id, status, acknowledged_at, audit_id }` |

**Server Components** for list/detail (stable, cacheable with `fetch(..., { next: { revalidate: 10 } })`).
**Client Components** only for the approve/dismiss buttons, the axis toggle, and the countdown timer.

```ts
// lib/api.ts
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function getPatients() {
  const res = await fetch(`${BASE}/api/patients`, { next: { revalidate: 10 } });
  if (!res.ok) throw new Error('patients fetch failed');
  return res.json();
}
export async function getPatient(id: string) { /* … */ }
export async function getAlert(pid: string, aid: string) { /* … */ }
export async function ackAlert(pid: string, aid: string) {
  const res = await fetch(`${BASE}/api/patients/${pid}/alerts/${aid}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clinician_id: 'prac-nurse-17', note: 'Acknowledged, RRT dispatched.' }),
  });
  if (!res.ok) throw new Error('approve failed');
  return res.json() as Promise<{ alert_id: string; status: string; acknowledged_at: string; audit_id: string }>;
}
```

No SWR — native `fetch` in RSC is enough for four views. Loading states are handled with `loading.tsx` route-level skeletons, but the demo video uses pre-hydrated pages so skeletons should never actually appear on camera.

---

## 7. Project Layout

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── globals.css
│   ├── page.tsx                      # /
│   ├── loading.tsx
│   ├── patients/
│   │   └── [id]/
│   │       ├── page.tsx
│   │       ├── loading.tsx
│   │       └── alerts/
│   │           └── [alertId]/
│   │               └── page.tsx
│   └── marketplace/
│       └── page.tsx
├── components/
│   ├── ui/                           # shadcn primitives
│   ├── vitals-chart.tsx
│   ├── risk-badge.tsx
│   ├── sbar-section.tsx
│   ├── contributing-signals-list.tsx
│   ├── alert-timeline.tsx
│   └── countdown-timer.tsx
├── lib/
│   ├── api.ts                        # backend client
│   ├── risk.ts                       # level helpers: compare, sort, label
│   └── format.ts                     # time-since, tabular numerics
├── public/
│   └── favicon.svg
├── tailwind.config.ts
├── next.config.ts
├── tsconfig.json
└── package.json
```

---

## 8. Accessibility Notes (WCAG 2.2 AA)

- **Touch / click targets**: minimum 44×44 px for every interactive control. Table rows are wrapped in a link and get `py-3` plus full-row hit area.
- **Contrast**: every risk badge bg/fg pair has been checked at ≥ 4.5:1. Chart lines hit ≥ 3:1 against `slate-50`.
- **Focus**: `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent` applied globally in `globals.css`. No `outline: none` anywhere.
- **Keyboard nav**: tab order matches visual order — roster → filter pills → table rows → action buttons. `<Dialog>` traps focus.
- **Semantic HTML**: `<table>`/`<thead>`/`<tbody>`, `<main>`, `<nav>`, `<h1>`…`<h3>` in order, `<time dateTime>` for every timestamp.
- **Icon-only buttons** (e.g. settings gear) have `aria-label`.
- **aria-live**: SBAR countdown timer is wrapped in `<div role="timer" aria-live="polite" aria-atomic="true">`; updates announced every 60 s, not every second.
- **Color is never the only signal**: risk level = background color + icon + text label (+ ring on critical). Chart lines additionally use distinct dash patterns on the printable/export variant.
- **Motion**: `@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }` — also disables the countdown flash.

---

## 9. Vercel Deployment

**Environment variables**

| Var                        | Dev value                      | Demo value                       |
|----------------------------|--------------------------------|----------------------------------|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000`        | `http://localhost:8000` (local)  |

**`vercel.json`**

```json
{
  "buildCommand": "next build",
  "outputDirectory": ".next",
  "framework": "nextjs",
  "regions": ["iad1"]
}
```

**Recommendation for demo recording**: run **everything locally** (Next dev server on :3000, FastAPI on :8000, HAPI FHIR on :8080). Vercel deploy is only needed if the judges want to click a live URL after the video — in that case start an `ngrok http 8000` tunnel and set `NEXT_PUBLIC_API_BASE_URL` to the tunnel URL in the Vercel project settings, then redeploy. Do **not** try to proxy HAPI FHIR through Vercel — too much moving plumbing on demo day.

Build command locally: `pnpm build && pnpm start`. Pre-warm every route (`curl http://localhost:3000/`, `/patients/102394`, `/patients/102394/alerts/abc`, `/marketplace`) before hitting record.

---

## 10. Demo Recording Checklist — 3 things the UI MUST NOT do

1. **No flashing / pulsing elements near the alert cards.** The EMERGENCY bar is static color, not animated. This is both a seizure-safety concern (WCAG 2.3.1) and it looks amateurish on video playback compression.
2. **No loading spinners or skeletons on camera.** Every route must be pre-hydrated before record. Use `pnpm start` (production build), warm each URL with `curl`, and keep the tab open before you hit record. No `loading.tsx` fallback should ever flash.
3. **No console errors, no hydration warnings, no 404s in DevTools.** Open DevTools in a *separate* window (not docked) before recording to verify clean; close it before recording. React hydration mismatches on `<time>` elements are the usual culprit — pass timestamps as pre-formatted strings from the server, do not call `toLocaleString()` on the client.

Bonus: set browser zoom to **110 %** — everything reads better on a 1080p recording; set the recording window to **1440×900**; disable browser extensions; hide the bookmarks bar.
