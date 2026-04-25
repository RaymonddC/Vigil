import * as React from "react";

export interface VitalTileProps {
  label: string;
  value: string | number;
  unit: string;
  alert?: boolean;
  trend?: string;
}

export function VitalTile({ label, value, unit, alert, trend }: VitalTileProps) {
  return (
    <div className={`vital${alert ? " alert" : ""}`}>
      <div className="lbl">{label}</div>
      <div className="num">
        {value}
        <span className="unit"> {unit}</span>
      </div>
      <div className="trend">{trend ?? (alert ? "↑ out of range" : "within range")}</div>
    </div>
  );
}
