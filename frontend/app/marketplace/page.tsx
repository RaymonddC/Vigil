import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Marketplace — Vigil",
  description: "Vigil clinical AI tools on the Prompt Opinion Marketplace",
};

type Listing = {
  id: string;
  name: string;
  type: string;
  author: string;
  desc: string;
  installs: string;
  rating: string;
};

const LISTINGS: Listing[] = [
  {
    id: "mcp-tools",
    name: "vigil-clinical-tools",
    type: "MCP Tool Library",
    author: "Vigil Health",
    desc:
      "FHIR read, NEWS2 / qSOFA scoring, SBAR drafter, audit log writer. 4 tools, versioned. SHARP-compliant.",
    installs: "2.4k",
    rating: "4.8",
  },
  {
    id: "a2a-agent",
    name: "vigil-ward-agent",
    type: "A2A Agent",
    author: "Vigil Health",
    desc:
      "Autonomous post-op / postpartum monitor. Deterministic 7-state machine. Human-in-the-loop by default.",
    installs: "810",
    rating: "4.9",
  },
];

export default function MarketplacePage() {
  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Prompt Opinion Marketplace</h1>
        <span className="page__sub">
          {LISTINGS.length} listings · published · verified
        </span>
      </div>

      <div className="alerts-list">
        {LISTINGS.map((l) => (
          <article key={l.id} className="alert-card" aria-label={l.name}>
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 6,
                background: "var(--ink-700)",
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: "var(--font-mono)",
                fontWeight: 600,
                fontSize: 14,
              }}
              aria-hidden="true"
            >
              {l.type[0]}
            </div>
            <div>
              <div className="who">
                {l.name}
                <span className="bed">
                  · {l.type} · {l.author}
                </span>
              </div>
              <div className="msg">{l.desc}</div>
            </div>
            <div className="meta">
              {l.installs} installs
              <br />
              <span style={{ color: "var(--warning)" }}>★ {l.rating}</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
