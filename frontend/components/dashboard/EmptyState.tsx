"use client";

interface EmptyStateProps {
  lastUpdated?: string | null;
}

export function EmptyState({ lastUpdated }: EmptyStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        border: "1px dashed var(--border-strong)",
        borderRadius: "var(--r-lg)",
        padding: "var(--s12) var(--s8)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--s3)",
        textAlign: "center",
        background: "var(--surface)",
      }}
    >
      <svg
        aria-hidden="true"
        width="40"
        height="40"
        viewBox="0 0 40 40"
        fill="none"
        style={{ color: "var(--border-strong)", flexShrink: 0 }}
      >
        <rect
          x="6" y="8" width="28" height="26" rx="3"
          stroke="currentColor" strokeWidth="1.5"
        />
        <path
          d="M6 14h28M14 8v6M26 8v6"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
        />
        <path
          d="M12 22h8M12 27h5"
          stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
        />
      </svg>

      <p
        style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: "var(--text-lg)",
          fontWeight: 600,
          color: "var(--ink-2)",
          marginTop: "var(--s2)",
        }}
      >
        No briefing available yet
      </p>
      <p
        style={{
          fontSize: "var(--text-ui)",
          color: "var(--ink-3)",
          maxWidth: "340px",
          lineHeight: "var(--lh-relaxed)",
        }}
      >
        The daily briefing runs at 21:00 IST on NSE trading days. Check back
        after the scheduler completes its first run.
      </p>
      {lastUpdated && (
        <p
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--ink-3)",
            marginTop: "var(--s2)",
          }}
        >
          Last report:{" "}
          <time dateTime={lastUpdated}>
            {new Date(lastUpdated).toLocaleDateString("en-IN", {
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
          </time>
        </p>
      )}
    </div>
  );
}
