"use client";

import { useState } from "react";
import { SectorCard } from "./SectorCard";
import type { SectorRankItem, TriggerItem } from "./types";

interface RankingTabsProps {
  priceRankings: SectorRankItem[];
  volumeRankings: SectorRankItem[];
  triggers: TriggerItem[];
}

type TabId = "price" | "volume";

const TABS: { id: TabId; label: string }[] = [
  { id: "price", label: "Price Rankings" },
  { id: "volume", label: "Volume Rankings" },
];

const MAX_SECTORS = 3;

export function RankingTabs({
  priceRankings,
  volumeRankings,
  triggers,
}: RankingTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>("price");

  const rankings = activeTab === "price" ? priceRankings : volumeRankings;
  const topSectors = rankings.slice(0, MAX_SECTORS);
  const panelId = `tab-panel-${activeTab}`;

  return (
    <div>
      {/* Tab list */}
      <div
        role="tablist"
        aria-label="Ranking type"
        style={{
          display: "flex",
          gap: "var(--s1)",
          borderBottom: "1px solid var(--border)",
          marginBottom: "var(--s5)",
        }}
      >
        {TABS.map(({ id, label }) => {
          const isActive = activeTab === id;
          return (
            <button
              key={id}
              role="tab"
              id={`tab-${id}`}
              aria-selected={isActive}
              aria-controls={panelId}
              onClick={() => setActiveTab(id)}
              style={{
                padding: "var(--s2) var(--s4)",
                background: "none",
                border: "none",
                borderBottom: isActive
                  ? "2px solid var(--brand)"
                  : "2px solid transparent",
                cursor: "pointer",
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: "var(--text-ui)",
                fontWeight: isActive ? 600 : 400,
                color: isActive ? "var(--brand)" : "var(--ink-2)",
                marginBottom: "-1px",
                transition: "color 0.15s, border-color 0.15s",
                whiteSpace: "nowrap",
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Tab panel */}
      <div
        id={panelId}
        role="tabpanel"
        aria-labelledby={`tab-${activeTab}`}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--s3)",
        }}
      >
        {topSectors.length === 0 ? (
          <p
            style={{
              fontSize: "var(--text-ui)",
              color: "var(--ink-3)",
              textAlign: "center",
              padding: "var(--s8) 0",
            }}
          >
            No sector rankings available for this briefing.
          </p>
        ) : (
          topSectors.map((sector, index) => {
            const rank = index + 1;
            const trigger = triggers.find(
              (t) => t.ticker === sector.top_constituent.ticker
            );
            return (
              <SectorCard
                key={`${sector.sector_name}-${activeTab}`}
                rank={rank}
                sector={sector}
                scoreType={activeTab}
                trigger={trigger}
              />
            );
          })
        )}
      </div>

      {rankings.length > MAX_SECTORS && (
        <p
          style={{
            marginTop: "var(--s4)",
            fontSize: "var(--text-sm)",
            color: "var(--ink-3)",
            textAlign: "center",
          }}
        >
          Showing top {MAX_SECTORS} of {rankings.length} sectors
        </p>
      )}
    </div>
  );
}
