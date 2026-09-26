const features = [
  {
    title: "Evening Briefing",
    description:
      "Every day at 21:00, a structured summary of market-moving filings, announcements, and sector movements across NSE and BSE.",
  },
  {
    title: "Company Research",
    description:
      "Deep dives on any listed company — annual reports, shareholding patterns, management changes, and financial trend analysis.",
  },
  {
    title: "SME & Mainboard Coverage",
    description:
      "Full coverage of BSE SME and NSE Emerge, the segment where most retail investors have the least information advantage.",
  },
];

export default function FeaturesSection() {
  return (
    <section
      style={{
        background: "var(--surface-warm)",
        borderTop: "1px solid var(--border)",
        paddingBlock: "var(--s16) var(--s12)",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          paddingInline: "var(--s6)",
        }}
      >
        <div
          style={{
            fontSize: "var(--text-base-sm)",
            color: "var(--ink-3)",
            marginBottom: "var(--s8)",
          }}
        >
          What the platform covers
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "var(--s6)",
          }}
          className="features-grid"
        >
          {features.map((f) => (
            <div
              key={f.title}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "var(--r-lg)",
                padding: "var(--s5) var(--s6)",
                boxShadow: "var(--shadow-md)",
              }}
            >
              <h3
                style={{
                  fontFamily: "'Lora', Georgia, serif",
                  fontWeight: 600,
                  fontSize: "0.9375rem",
                  color: "var(--ink-1)",
                  textWrap: "balance",
                  marginBottom: "var(--s3)",
                }}
              >
                {f.title}
              </h3>
              <p
                style={{
                  fontSize: "var(--text-ui)",
                  color: "var(--ink-2)",
                  lineHeight: 1.6,
                }}
              >
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
