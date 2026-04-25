import * as React from "react";

export interface SBARSections {
  situation: string;
  background: string;
  assessment: string;
  recommendation: string;
}

export interface SBARCardProps {
  sbar: SBARSections;
  /** "B-12 · Sarah Chen" — the right-of-tag header text. */
  patientLabel: string;
  /** Display time like "14:02". */
  time?: string;
  approved?: boolean;
}

/**
 * SBARCard — the agent's drafted handoff. The header tag flips between
 * `SBAR · DRAFT` and `SBAR · APPROVED` to make the human-in-the-loop
 * status visible at a glance.
 */
export function SBARCard({ sbar, patientLabel, time, approved }: SBARCardProps) {
  return (
    <div className="sbar">
      <div className="sbar__hd">
        <span className="sbar__tag">{approved ? "SBAR · APPROVED" : "SBAR · DRAFT"}</span>
        <span className="sbar__title">{patientLabel}</span>
        {time && <span className="sbar__time">{time}</span>}
      </div>
      <Section k="Situation"   v={sbar.situation} />
      <Section k="Background"  v={sbar.background} />
      <Section k="Assessment"  v={sbar.assessment} />
      <Section k="Recommend"   v={sbar.recommendation} />
    </div>
  );
}

function Section({ k, v }: { k: string; v: string }) {
  return (
    <div className="sbar__sec">
      <span className="sbar__k">{k}</span>
      <span className="sbar__v">{v || "—"}</span>
    </div>
  );
}
