export default function DashboardPage() {
  return (
    <div>
      <h1
        style={{
          fontFamily: "'Lora', Georgia, serif",
          fontWeight: 700,
          fontSize: "var(--text-2xl)",
          color: "var(--ink-1)",
          textWrap: "balance",
          marginBottom: "var(--s4)",
        }}
      >
        Dashboard
      </h1>
      <p style={{ fontSize: "var(--text-ui)", color: "var(--ink-3)" }}>
        Application data screens are implemented in Phase 2+.
      </p>
    </div>
  );
}
