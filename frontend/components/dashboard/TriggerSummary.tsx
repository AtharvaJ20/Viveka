"use client";

import type { TriggerItem } from "./types";

const NO_TRIGGER_TEXT = "No identifiable trigger found for this move.";

interface TriggerSummaryProps {
  trigger: TriggerItem;
}

export function TriggerSummary({ trigger }: TriggerSummaryProps) {
  const isNoTrigger = trigger.trigger_summary === NO_TRIGGER_TEXT;

  return (
    <div
      style={{
        borderTop: "1px solid var(--border)",
        paddingTop: "var(--s3)",
        marginTop: "var(--s3)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--s2)",
      }}
    >
      <p
        style={{
          fontSize: "var(--text-ui)",
          lineHeight: "var(--lh-relaxed)",
          color: isNoTrigger ? "var(--ink-3)" : "var(--ink-1)",
          fontStyle: isNoTrigger ? "italic" : "normal",
        }}
      >
        {trigger.trigger_summary}
      </p>

      {!isNoTrigger && trigger.news_urls_used.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--s1)",
          }}
        >
          <span
            style={{
              fontSize: "var(--text-sm)",
              fontWeight: 600,
              color: "var(--ink-3)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            Sources
          </span>
          <ul
            role="list"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--s1)",
              padding: 0,
              listStyle: "none",
            }}
          >
            {trigger.news_urls_used.map((url) => (
              <li key={url}>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: "var(--text-sm)",
                    color: "var(--brand)",
                    wordBreak: "break-all",
                    textDecoration: "underline",
                    textDecorationColor: "color-mix(in srgb, var(--brand) 40%, transparent)",
                    textUnderlineOffset: "2px",
                  }}
                >
                  {_friendlyDomain(url)}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function _friendlyDomain(url: string): string {
  try {
    const { hostname, pathname } = new URL(url);
    const domain = hostname.replace(/^www\./, "");
    // For synthetic exchange URLs (nse://, bse://) return the full url
    if (!url.startsWith("http")) return url;
    // Truncate long paths
    const path = pathname.length > 40 ? pathname.slice(0, 40) + "…" : pathname;
    return `${domain}${path === "/" ? "" : path}`;
  } catch {
    return url.length > 60 ? url.slice(0, 60) + "…" : url;
  }
}
