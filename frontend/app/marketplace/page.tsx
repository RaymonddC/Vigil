import type { Metadata } from 'next';
import { Badge } from '@/components/ui/badge';

export const metadata: Metadata = {
  title: 'Marketplace — Vigil',
  description: 'Vigil clinical AI tools on the Prompt Opinion Marketplace',
};

const TILES = [
  {
    id: 'mcp-server',
    title: 'Vigil MCP Server',
    subtitle: '4 Clinical Early-Warning Tools',
    description:
      'Real-time FHIR R4 vitals analysis, sepsis risk scoring (qSOFA + MEWT), deterioration detection, and LLM escalation-note generation. Exposes SHARP-compliant context headers for Prompt Opinion agent handoffs.',
    badges: [
      { label: 'MCP',     variant: 'outline' as const },
      { label: 'FHIR R4', variant: 'outline' as const },
      { label: 'SHARP',   variant: 'outline' as const },
    ],
    cta: 'Install →',
    ctaNote: 'Coming to Prompt Opinion Marketplace',
    agentCardHref: null,
  },
  {
    id: 'a2a-agent',
    title: 'Vigil Postop Sentinel',
    subtitle: '7-state A2A Agent, clinician-approved',
    description:
      'Autonomous post-operative monitoring agent. Polls HAPI FHIR, triggers MCP tools, generates SBAR escalation notes, and routes to clinician review queues. Implements the full A2A JSON-RPC protocol.',
    badges: [
      { label: 'A2A',     variant: 'outline' as const },
      { label: 'FHIR R4', variant: 'outline' as const },
      { label: 'SHARP',   variant: 'outline' as const },
    ],
    cta: 'Subscribe →',
    ctaNote: 'Clinician approval required',
    agentCardHref: '/.well-known/agent-card.json',
  },
];

export default function MarketplacePage() {
  return (
    <div className="p-6 space-y-8">

      {/* Page header */}
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
          Vigil on the Prompt Opinion Marketplace
        </h1>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
          Clinical AI tools built for the{' '}
          <span className="font-medium text-slate-700 dark:text-slate-300">Prompt Opinion</span>{' '}
          agent ecosystem. Each listing is SHARP-compliant and communicates via FHIR R4 — interoperable
          with any hospital EHR that supports HL7 FHIR R4.
        </p>
      </div>

      {/* Two-tile grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-4xl">
        {TILES.map((tile) => (
          <article
            key={tile.id}
            className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col"
            aria-label={tile.title}
          >
            {/* Card header */}
            <div className="p-6 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50">
                    {tile.title}
                  </h2>
                  <p className="mt-0.5 text-sm font-medium text-[#0B5FFF] dark:text-blue-400">
                    {tile.subtitle}
                  </p>
                </div>

                {/* Badge cluster */}
                <div className="flex flex-wrap gap-1.5 shrink-0">
                  {tile.badges.map((b) => (
                    <Badge
                      key={b.label}
                      variant={b.variant}
                      className="text-xs font-medium text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600"
                    >
                      {b.label}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>

            {/* Description */}
            <div className="px-6 py-4 flex-1">
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                {tile.description}
              </p>
            </div>

            {/* Footer */}
            <div className="px-6 py-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-3">
              <p className="text-xs text-slate-400 dark:text-slate-500 italic">
                {tile.ctaNote}
              </p>
              <div className="flex items-center gap-2">
                {tile.agentCardHref && (
                  <a
                    href={tile.agentCardHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-[#0B5FFF] hover:text-[#0950DB] dark:text-blue-400 dark:hover:text-blue-300 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] rounded"
                  >
                    Agent card ↗
                  </a>
                )}
                <button
                  type="button"
                  disabled
                  aria-disabled="true"
                  className="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium bg-[#0B5FFF] text-white opacity-40 cursor-not-allowed min-h-[44px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF]"
                >
                  {tile.cta}
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* Footer note */}
      <p className="text-xs text-slate-400 dark:text-slate-600 max-w-2xl">
        Vigil is a research prototype submitted to the Agents Assemble hackathon. Listed tools are
        not approved medical devices. Clinical decisions require physician oversight.
      </p>

    </div>
  );
}
