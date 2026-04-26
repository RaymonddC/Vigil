"use client";

import * as React from "react";
import { Panel } from "@/components/panel";
import {
  FHIR_SOURCES,
  getSelectedFhirSourceId,
  setSelectedFhirSourceId,
  onFhirSourceChange,
  getPoFhirUrl,
  setPoFhirUrl,
  onPoFhirUrlChange,
  getPoFhirToken,
  setPoFhirToken,
  onPoFhirTokenChange,
  type FhirSourceId,
} from "@/lib/fhir-sources";

// useSyncExternalStore adapters — the switcher is driven by localStorage,
// which React treats as an external store. getServerSnapshot pins SSR /
// first hydration to the defaults so markup matches.

function subscribeSource(cb: () => void) {
  return onFhirSourceChange(() => cb());
}
function getSourceSnapshot(): FhirSourceId {
  return getSelectedFhirSourceId();
}
function getSourceServerSnapshot(): FhirSourceId {
  return "hapi";
}

function subscribeUrl(cb: () => void) {
  return onPoFhirUrlChange(() => cb());
}
function getUrlSnapshot(): string {
  return getPoFhirUrl();
}
function getUrlServerSnapshot(): string {
  return "";
}

/**
 * For the token we only ever surface presence / absence to the UI — we
 * don't render the value. Storing a boolean in the store snapshot keeps
 * the strict-equality comparison in `useSyncExternalStore` cheap.
 */
function subscribeTokenPresence(cb: () => void) {
  return onPoFhirTokenChange(() => cb());
}
function getTokenPresenceSnapshot(): boolean {
  return getPoFhirToken().length > 0;
}
function getTokenPresenceServerSnapshot(): boolean {
  return false;
}

/**
 * Settings-page panel: pick where the dashboard reads FHIR data from.
 * Persisted via localStorage with cookie mirror so server components see
 * the same selection.
 */
export function FhirSourceSwitcher() {
  const persistedSource = React.useSyncExternalStore(
    subscribeSource,
    getSourceSnapshot,
    getSourceServerSnapshot
  );
  const persistedUrl = React.useSyncExternalStore(
    subscribeUrl,
    getUrlSnapshot,
    getUrlServerSnapshot
  );
  const tokenIsPresent = React.useSyncExternalStore(
    subscribeTokenPresence,
    getTokenPresenceSnapshot,
    getTokenPresenceServerSnapshot
  );

  // Local "in-flight edit" buffers. Initially `null`, which means "no
  // pending edit — render the persisted value". Setting any of these to a
  // non-null value tracks a user edit until Save / Reset clears them. This
  // avoids the React 19 setState-in-effect cascading-render warning that a
  // useState+useEffect sync pattern would trip.
  const [editSource, setEditSource] = React.useState<FhirSourceId | null>(null);
  const [editUrl, setEditUrl] = React.useState<string | null>(null);
  const [draftToken, setDraftToken] = React.useState<string>("");
  const [showToken, setShowToken] = React.useState(false);

  const draftSource: FhirSourceId = editSource ?? persistedSource;
  const draftUrl: string = editUrl ?? persistedUrl;

  const sourceChanged = editSource !== null && editSource !== persistedSource;
  const urlChanged = editUrl !== null && editUrl !== persistedUrl;
  const tokenChanged = draftToken !== "";
  const dirty = sourceChanged || urlChanged || tokenChanged;

  const showPoWarning =
    draftSource === "po" &&
    (draftUrl.trim() === "" || (!tokenIsPresent && draftToken.trim() === ""));

  const handleSave = () => {
    if (sourceChanged) setSelectedFhirSourceId(draftSource);
    if (urlChanged) setPoFhirUrl(draftUrl);
    if (tokenChanged) setPoFhirToken(draftToken);
    // Clear edit buffers — the persisted snapshot is now the source of truth.
    setEditSource(null);
    setEditUrl(null);
    setDraftToken("");
  };

  const handleClear = () => {
    setSelectedFhirSourceId("hapi");
    setPoFhirUrl("");
    setPoFhirToken("");
    setEditSource(null);
    setEditUrl(null);
    setDraftToken("");
  };

  const activeSource =
    FHIR_SOURCES.find((s) => s.id === persistedSource) ?? FHIR_SOURCES[0];

  return (
    <Panel
      title="FHIR data source"
      meta={`active: ${activeSource.label}`}
      bodyClassName="panel__body"
    >
      <div className="flex flex-col gap-3 text-[12px]">
        <p className="text-[var(--fg-2)] leading-relaxed">
          Choose which FHIR server the dashboard reads from. Switching to
          Prompt Opinion makes the dashboard a read-only client of an
          external workspace; Approve actions are disabled until you switch
          back to local HAPI.
        </p>

        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">FHIR source</legend>
          {FHIR_SOURCES.map((s) => (
            <label
              key={s.id}
              className="flex items-start gap-2.5 cursor-pointer rounded-md border border-[var(--border)] px-3 py-2 hover:bg-[var(--surface-2)]"
              style={{
                background:
                  draftSource === s.id ? "var(--surface-2)" : "transparent",
              }}
            >
              <input
                type="radio"
                name="vigil-fhir-source"
                value={s.id}
                checked={draftSource === s.id}
                onChange={() => setEditSource(s.id)}
                className="mt-0.5"
              />
              <span className="flex flex-col gap-0.5 flex-1 min-w-0">
                <span className="font-medium text-[var(--fg-1)]">
                  {s.label}
                  {!s.writesAllowed && (
                    <span
                      className="ml-2 text-[10px] uppercase tracking-wider text-[var(--fg-3)]"
                      style={{ fontFamily: "var(--font-mono)" }}
                    >
                      READ-ONLY
                    </span>
                  )}
                </span>
                <span className="text-[var(--fg-2)]">{s.description}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="vigil-po-url"
            className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            Prompt Opinion FHIR URL
          </label>
          <input
            id="vigil-po-url"
            type="url"
            spellCheck={false}
            autoComplete="off"
            placeholder="https://app.promptopinion.ai/api/workspaces/<id>/fhir"
            value={draftUrl}
            onChange={(e) => setEditUrl(e.target.value)}
            className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[12px] font-mono outline-none focus:border-[var(--ink-700)]"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="vigil-po-token"
            className="text-[11px] uppercase tracking-wider text-[var(--fg-3)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            Prompt Opinion bearer token{" "}
            {tokenIsPresent && (
              <span className="ml-1 text-[var(--fg-2)] normal-case tracking-normal">
                (saved — leave blank to keep)
              </span>
            )}
          </label>
          <div className="flex items-center gap-2">
            <input
              id="vigil-po-token"
              type={showToken ? "text" : "password"}
              spellCheck={false}
              autoComplete="off"
              placeholder={tokenIsPresent ? "••••••••" : "paste SMART-on-FHIR token"}
              value={draftToken}
              onChange={(e) => setDraftToken(e.target.value)}
              className="flex-1 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[12px] font-mono outline-none focus:border-[var(--ink-700)]"
            />
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => setShowToken((v) => !v)}
              aria-label={showToken ? "Hide token" : "Show token"}
            >
              {showToken ? "Hide" : "Show"}
            </button>
          </div>
        </div>

        {showPoWarning && (
          <div
            className="rounded-md border border-[var(--warn-border,#d4a017)] bg-[var(--warn-bg,#fff8e1)] px-3 py-2 text-[12px] text-[var(--warn-fg,#8a6d3b)]"
            role="status"
          >
            Prompt Opinion mode needs both a workspace URL and a bearer token
            before reads will succeed. The backend will silently fall back to
            local HAPI until both are set.
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={handleSave}
            disabled={!dirty}
          >
            Save
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={handleClear}
          >
            Reset to HAPI
          </button>
          <span className="grow" />
          <span
            className="text-[10px] uppercase tracking-wider text-[var(--fg-3)]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            stored: {persistedSource}
          </span>
        </div>
      </div>
    </Panel>
  );
}
