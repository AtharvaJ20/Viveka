import Link from "next/link";
import BriefingCard from "./BriefingCard";

export default function HeroSection() {
  return (
    <section
      style={{
        maxWidth: "1200px",
        margin: "0 auto",
        paddingInline: "var(--s6)",
        paddingTop: "var(--s16)",
        paddingBottom: "var(--s12)",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--s12)",
          alignItems: "center",
        }}
        className="hero-grid"
      >
        {/* Copy column */}
        <div>
          <div
            style={{
              fontSize: "var(--text-base-sm)",
              fontWeight: 600,
              color: "var(--copper)",
              letterSpacing: "0.04em",
              marginBottom: "var(--s4)",
            }}
          >
            Indian equity research
          </div>
          <h1
            style={{
              fontFamily: "'Lora', Georgia, serif",
              fontWeight: 700,
              fontSize: "clamp(2rem, 3.6vw, 3rem)",
              lineHeight: 1.1,
              color: "var(--ink-1)",
              textWrap: "balance",
              marginBottom: "var(--s5)",
            }}
          >
            Research-grade insight on every Indian equity.
          </h1>
          <p
            style={{
              fontSize: "var(--text-body)",
              color: "var(--ink-2)",
              lineHeight: 1.65,
              marginBottom: "var(--s8)",
              maxWidth: "48ch",
            }}
          >
            Viveka aggregates filings, announcements, and market data into a
            structured daily briefing — so you spend less time reading and more
            time deciding.
          </p>
          <Link
            href="/login"
            style={{
              display: "inline-flex",
              alignItems: "center",
              borderRadius: "var(--r-md)",
              padding: "var(--s3) var(--s6)",
              background: "var(--brand)",
              color: "var(--brand-on)",
              fontFamily: "'DM Sans', system-ui, sans-serif",
              fontSize: "0.9375rem",
              fontWeight: 500,
              textDecoration: "none",
            }}
          >
            Sign in
          </Link>
          <p
            style={{
              marginTop: "var(--s4)",
              fontSize: "var(--text-sm)",
              color: "var(--ink-3)",
            }}
          >
            Private · by invitation only
          </p>
        </div>

        {/* Briefing card column */}
        <div>
          <BriefingCard />
        </div>
      </div>
    </section>
  );
}
