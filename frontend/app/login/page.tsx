import type { Metadata } from "next";
import Nav from "@/components/layout/Nav";
import LoginForm from "@/components/login/LoginForm";

export const metadata: Metadata = {
  title: "Sign in — Viveka",
};

export default function LoginPage() {
  return (
    <>
      <Nav showSignIn={false} />
      <main
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: "var(--s16)",
          paddingInline: "var(--s6)",
        }}
      >
        <div style={{ marginBottom: "var(--s8)", textAlign: "center" }}>
          <h1
            style={{
              fontFamily: "'Lora', Georgia, serif",
              fontWeight: 700,
              fontSize: "var(--text-2xl)",
              color: "var(--ink-1)",
              textWrap: "balance",
              marginBottom: "var(--s3)",
            }}
          >
            Sign in to Viveka
          </h1>
          <p
            style={{
              fontSize: "var(--text-ui)",
              color: "var(--ink-3)",
            }}
          >
            Private · by invitation only
          </p>
        </div>
        <LoginForm />
      </main>
    </>
  );
}
