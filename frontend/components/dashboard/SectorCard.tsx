"use client";

import { useState } from "react";
import { TriggerSummary } from "./TriggerSummary";
import type { SectorRankItem, TriggerItem } from "./types";

interface SectorCardProps {
  rank: number;
  sector: SectorRankItem;
  scoreType: "price" | "volume";
  trigger: TriggerItem | undefined;
}

export function SectorCard({ rank, sector, scoreType, trigger }: SectorCardProps) {
  const [expanded, setExpanded] = useState(false);
  const panelId = `sector-panel-${rank}-${scoreType}`;
  const headerId = `sector-header-${rank}-${scoreType}`;

  const formattedScore = _formatScore(sector.sector_score, scoreType);
  const scoreColor = _scoreColor(sector.sector_score, scoreType);
  const constituentScore = _formatScore(sector.top_constituent.score, scoreType);

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-lg)",
        overflow: "hidden",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      {/* Card header / toggle button */}
      <button
        id={headerId}
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((v) => !v)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: "var(--s3)",
          padding: "var(--s4) var(--s5)",
          background: "none",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
          color: "inherit",
        }}
      >
        {/* Rank badge */}
        <span
          aria-label={`Rank ${rank}`}
          style={{
            flexShrink: 0,
            width: "28px",
            height: "28px",
            borderRadius: "var(--r-full)",
            background: "var(--brand-subtle)",
            color: "var(--brand)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "var(--text-sm)",
            fontWeight: 700,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {rank}
        </span>

        {/* Sector name + constituent count */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: "var(--text-body)",
              fontWeight: 600,
              color: "var(--ink-1)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {sector.sector_name}
          </p>
          <p
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--ink-3)",
              marginTop: "1px",
            }}
          >
            {sector.constituent_count}{" "}
            {sector.constituent_count === 1 ? "stock" : "stocks"}
          </p>
        </div>

        {/* Score pill */}
        <span
          className="tabular"
          style={{
            flexShrink: 0,
            padding: "2px var(--s2)",
            borderRadius: "var(--r-full)",
            background: _scoreBg(sector.sector_score, scoreType),
            color: scoreColor,
            fontSize: "var(--text-ui)",
            fontWeight: 600,
          }}
        >
          {formattedScore}
        </span>

        {/* Chevron */}
        <ChevronIcon expanded={expanded} />
      </button>

      {/* Expanded detail panel */}
      {expanded && (
        <div
          id={panelId}
          role="region"
          aria-labelledby={headerId}
          style={{
            padding: "0 var(--s5) var(--s5)",
            borderTop: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--s3)",
          }}
        >
          {/* Top mover */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "var(--s3)",
              paddingTop: "var(--s4)",
              flexWrap: "wrap",
            }}
          >
            <div>
              <span
                style={{
                  fontSize: "var(--text-sm)",
                  fontWeight: 600,
                  color: "var(--ink-3)",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  display: "block",
                  marginBottom: "2px",
                }}
              >
                Top Mover
              </span>
              <span
                style={{
                  fontFamily: "'DM Sans', system-ui, sans-serif",
                  fontSize: "var(--text-body)",
                  fontWeight: 700,
                  color: "var(--ink-1)",
                  letterSpacing: "0.02em",
                }}
              >
                {sector.top_constituent.ticker}
              </span>
            </div>
            <span
              className="tabular"
              style={{
                padding: "2px var(--s2)",
                borderRadius: "var(--r-full)",
                background: _scoreBg(sector.top_constituent.score, scoreType),
                color: _scoreColor(sector.top_constituent.score, scoreType),
                fontSize: "var(--text-ui)",
                fontWeight: 600,
              }}
            >
              {constituentScore}
            </span>
          </div>

          {/* Provenance */}
          <p
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--ink-3)",
            }}
          >
            Sector map{" "}
            <span
              style={{
                fontFamily: "monospace",
                background: "var(--surface-warm)",
                padding: "1px 4px",
                borderRadius: "var(--r-sm)",
                fontSize: "var(--text-xs)",
              }}
            >
              {sector.map_version}
            </span>
          </p>

          {/* Trigger summary */}
          {trigger && <TriggerSummary trigger={trigger} />}
        </div>
      )}
    </div>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      style={{
        flexShrink: 0,
        color: "var(--ink-3)",
        transition: "transform 0.2s ease",
        transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
      }}
    >
      <path
        d="M4 6l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function _formatScore(score: number, type: "price" | "volume"): string {
  if (type === "price") {
    const sign = score >= 0 ? "+" : "";
    return `${sign}${score.toFixed(2)}%`;
  }
  // volume score = ratio × 100; display as multiplier e.g. 1.50×
  return `${(score / 100).toFixed(2)}×`;
}

function _scoreColor(score: number, type: "price" | "volume"): string {
  if (type === "volume") return "var(--brand)";
  if (score > 0) return "var(--pos)";
  if (score < 0) return "var(--neg)";
  return "var(--ink-2)";
}

function _scoreBg(score: number, type: "price" | "volume"): string {
  if (type === "volume") return "var(--brand-subtle)";
  if (score > 0) return "var(--pos-subtle)";
  if (score < 0) return "var(--neg-subtle)";
  return "var(--surface-warm)";
}
