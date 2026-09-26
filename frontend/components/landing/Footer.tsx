export default function Footer() {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--border)",
        paddingBlock: "var(--s8)",
        paddingInline: "var(--s6)",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
        }}
      >
        <p
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--ink-3)",
            lineHeight: 1.6,
            maxWidth: "72ch",
            marginBottom: "var(--s3)",
          }}
        >
          The information provided by Viveka is for research and informational
          purposes only. It does not constitute investment advice, a solicitation,
          or a recommendation to buy or sell any security. Past performance is
          not indicative of future results. You are solely responsible for your
          investment decisions.
        </p>
        <p
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--ink-3)",
          }}
        >
          Private · by invitation only
        </p>
      </div>
    </footer>
  );
}
