"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { RankingTabs } from "@/components/dashboard/RankingTabs";
import { apiFetch, ApiError } from "@/lib/api";
import type { DailyBriefingReport } from "@/components/dashboard/types";

type FetchState =
  | { status: "loading" }
  | { status: "empty" }
  | { status: "error"; message: string }
  | { status: "loaded"; report: DailyBriefingReport };

export default function DashboardPage() {
  const [fetchState, setFetchState] = useState<FetchState>({ status: "loading" });

  const loadReport = () => {
    setFetchState({ status: "loading" });
    const controller = new AbortController();

    apiFetch("/api/v1/reports/latest?type=daily_briefing", {
      signal: controller.signal,
    })
      .then((res) => res.json() as Promise<DailyBriefingReport>)
      .then((report) => setFetchState({ status: "loaded", report }))
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err instanceof ApiError && err.status === 404) {
          setFetchState({ status: "empty" });
          return;
        }
        const message =
          err instanceof Error ? err.message : "An unexpected error occurred.";
        setFetchState({ status: "error", message });
      });

    return () => controller.abort();
  };

  useEffect(loadReport, []);

  return (
    <div>
      <h1
        style={{
          fontFamily: "'Lora', Georgia, serif",
          fontWeight: 700,
          fontSize: "var(--text-2xl)",
          color: "var(--ink-1)",
          marginBottom: "var(--s2)",
        }}
      >
        Daily Briefing
      </h1>

      {fetchState.status === "loading" && <LoadingSkeleton />}

      {fetchState.status === "error" && (
        <ErrorState message={fetchState.message} onRetry={loadReport} />
      )}

      {fetchState.status === "empty" && <EmptyState />}

      {fetchState.status === "loaded" && (
        <LoadedReport report={fetchState.report} />
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Loaded report
   ────────────────────────────────────────────────────────────────────────── */

function LoadedReport({ report }: { report: DailyBriefingReport }) {
  const content = report.content;

  if (!content) {
    return <EmptyState />;
  }

  const briefingDate = report.trading_date
    ? new Date(report.trading_date + "T00:00:00").toLocaleDateString("en-IN", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : null;

  const generatedAt = report.generated_at
    ? new Date(report.generated_at).toLocaleString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZoneName: "short",
      })
    : null;

  return (
    <>
      {/* Briefing date + metadata row */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "baseline",
          gap: "var(--s2)",
          marginBottom: "var(--s6)",
        }}
      >
        {briefingDate && (
          <p
            style={{
              fontSize: "var(--text-ui)",
              color: "var(--ink-3)",
            }}
          >
            {briefingDate}
          </p>
        )}
        {generatedAt && briefingDate && (
          <span style={{ color: "var(--border-strong)", fontSize: "var(--text-sm)" }}>
            ·
          </span>
        )}
        {generatedAt && (
          <p
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--ink-3)",
            }}
          >
            Generated {generatedAt}
          </p>
        )}
      </div>

      <RankingTabs
        priceRankings={content.rankings_price ?? []}
        volumeRankings={content.rankings_volume ?? []}
        triggers={content.triggers ?? []}
      />
    </>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Loading skeleton
   ────────────────────────────────────────────────────────────────────────── */

function LoadingSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading briefing"
      aria-live="polite"
      style={{ display: "flex", flexDirection: "column", gap: "var(--s3)" }}
    >
      <SkeletonBar width="180px" height="var(--text-ui)" />
      <div
        style={{
          display: "flex",
          gap: "var(--s3)",
          borderBottom: "1px solid var(--border)",
          paddingBottom: "var(--s1)",
          marginBottom: "var(--s5)",
        }}
      >
        <SkeletonBar width="120px" height="var(--text-ui)" />
        <SkeletonBar width="130px" height="var(--text-ui)" />
      </div>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-lg)",
            padding: "var(--s4) var(--s5)",
            display: "flex",
            alignItems: "center",
            gap: "var(--s3)",
          }}
        >
          <SkeletonCircle size="28px" />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "var(--s2)" }}>
            <SkeletonBar width="60%" height="var(--text-ui)" />
            <SkeletonBar width="40%" height="var(--text-sm)" />
          </div>
          <SkeletonBar width="52px" height="var(--text-ui)" />
        </div>
      ))}
      <span className="sr-only">Loading daily briefing…</span>
    </div>
  );
}

function SkeletonBar({
  width,
  height,
}: {
  width: string;
  height: string;
}) {
  return (
    <div
      aria-hidden="true"
      style={{
        width,
        height,
        borderRadius: "var(--r-sm)",
        background: "var(--border)",
        animation: "pulse 1.6s ease-in-out infinite",
      }}
    />
  );
}

function SkeletonCircle({ size }: { size: string }) {
  return (
    <div
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: "var(--r-full)",
        background: "var(--border)",
        animation: "pulse 1.6s ease-in-out infinite",
      }}
    />
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Error state
   ────────────────────────────────────────────────────────────────────────── */

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--r-lg)",
        padding: "var(--s8)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "var(--s3)",
        textAlign: "center",
        background: "var(--surface)",
      }}
    >
      <p
        style={{
          fontSize: "var(--text-ui)",
          fontWeight: 600,
          color: "var(--neg)",
        }}
      >
        Failed to load briefing
      </p>
      <p
        style={{
          fontSize: "var(--text-ui)",
          color: "var(--ink-3)",
          maxWidth: "320px",
        }}
      >
        {message}
      </p>
      <button
        onClick={onRetry}
        style={{
          marginTop: "var(--s2)",
          padding: "var(--s2) var(--s5)",
          borderRadius: "var(--r-md)",
          background: "var(--brand)",
          color: "var(--brand-on)",
          border: "none",
          cursor: "pointer",
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: "var(--text-ui)",
          fontWeight: 600,
        }}
      >
        Try again
      </button>
    </div>
  );
}
