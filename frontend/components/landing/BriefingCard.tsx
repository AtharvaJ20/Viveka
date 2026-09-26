const sectors = [
  { rank: 1, name: "Capital Goods", change: "+2.4%", pos: true },
  { rank: 2, name: "Financials", change: "+1.8%", pos: true },
  { rank: 3, name: "Energy", change: "−0.6%", pos: false },
];

export default function BriefingCard() {
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-lg)",
        padding: "var(--s5) var(--s6)",
        boxShadow: "var(--shadow-lg)",
      }}
    >
      <div
        style={{
          fontFamily: "'Lora', Georgia, serif",
          fontWeight: 600,
          fontSize: "0.9375rem",
          color: "var(--ink-1)",
          marginBottom: "var(--s4)",
        }}
      >
        Evening Briefing
      </div>
      <div
        style={{
          fontSize: "var(--text-sm)",
          color: "var(--ink-3)",
          marginBottom: "var(--s4)",
        }}
      >
        Top sectors · 26 Sep 2026
      </div>
      {sectors.map((s, i) => (
        <div
          key={s.rank}
          className="fadeup-item"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            paddingBlock: "var(--s2)",
            borderBottom: i < sectors.length - 1 ? "1px solid var(--border)" : "none",
            fontVariantNumeric: "tabular-nums",
            animation: `fadeUp 400ms ease both`,
            animationDelay: i === 0 ? "150ms" : i === 1 ? "300ms" : "420ms",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: "var(--s3)" }}>
            <span
              style={{
                color: "var(--ink-3)",
                fontSize: "var(--text-sm)",
                width: "12px",
                textAlign: "right",
              }}
            >
              {s.rank}
            </span>
            <span style={{ fontSize: "var(--text-ui)", color: "var(--ink-1)" }}>
              {s.name}
            </span>
          </div>
          <span
            style={{
              fontSize: "var(--text-ui)",
              fontWeight: 600,
              color: s.pos ? "var(--pos)" : "var(--neg)",
            }}
          >
            {s.change}
          </span>
        </div>
      ))}
      <div
        style={{
          marginTop: "var(--s4)",
          fontSize: "var(--text-xs)",
          color: "var(--ink-3)",
        }}
      >
        NSE / BSE · End of day
      </div>
    </div>
  );
}
