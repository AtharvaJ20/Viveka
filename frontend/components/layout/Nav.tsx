import Link from "next/link";
import dynamic from "next/dynamic";
import VivekaLogo from "./VivekaLogo";

const ThemeToggle = dynamic(() => import("./ThemeToggle"), { ssr: false });

interface NavProps {
  showSignIn?: boolean;
}

export default function Nav({ showSignIn = true }: NavProps) {
  return (
    <nav
      style={{
        position: "sticky",
        top: "env(safe-area-inset-top, 0px)",
        zIndex: 100,
        background: "var(--canvas)",
        borderBottom: "1px solid var(--border)",
        height: "56px",
        display: "flex",
        alignItems: "center",
        paddingInline: "var(--s6)",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          width: "100%",
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Link href="/" style={{ textDecoration: "none" }}>
          <VivekaLogo />
        </Link>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)" }}>
          <ThemeToggle />
          {showSignIn && (
            <Link
              href="/login"
              style={{
                fontFamily: "'DM Sans', system-ui, sans-serif",
                fontSize: "0.9375rem",
                fontWeight: 500,
                color: "var(--brand)",
                textDecoration: "none",
              }}
            >
              Sign in
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
