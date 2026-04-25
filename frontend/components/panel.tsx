import * as React from "react";

export interface PanelProps {
  title?: React.ReactNode;
  meta?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children?: React.ReactNode;
}

/**
 * Panel — the workhorse card. 1px border, 6px radius, header strip with
 * title + monospace meta + optional right slot. Children render inside a
 * default `.panel__body` unless `bodyClassName` is overridden to bare
 * (e.g. for SBAR's 4-row grid that sets its own padding).
 */
export function Panel({
  title,
  meta,
  right,
  className,
  bodyClassName,
  children,
}: PanelProps) {
  const hasHeader = !!(title || right || meta);
  return (
    <div className={["panel", className].filter(Boolean).join(" ")}>
      {hasHeader && (
        <div className="panel__hd">
          {title && <span className="t">{title}</span>}
          {meta && <span className="s">{meta}</span>}
          {right && <span style={{ marginLeft: "auto" }}>{right}</span>}
        </div>
      )}
      {bodyClassName === "" ? children : (
        <div className={bodyClassName ?? "panel__body"}>{children}</div>
      )}
    </div>
  );
}
