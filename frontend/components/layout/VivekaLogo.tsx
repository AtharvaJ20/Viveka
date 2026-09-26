export default function VivekaLogo() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--s2)" }}>
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        {/* Ascending three-bar mark */}
        <rect x="2" y="16" width="5" height="6" fill="var(--brand)" rx="1" />
        <rect x="9.5" y="11" width="5" height="11" fill="var(--brand)" rx="1" />
        <rect x="17" y="5" width="5" height="17" fill="var(--brand)" rx="1" />
        {/* Copper trailing line */}
        <rect x="22.5" y="3" width="1.5" height="19" fill="var(--copper)" rx="0.75" />
      </svg>
      <span
        style={{
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontWeight: 600,
          fontSize: "1rem",
          color: "var(--ink-1)",
          letterSpacing: "-0.015em",
        }}
      >
        Viveka
      </span>
    </span>
  );
}
