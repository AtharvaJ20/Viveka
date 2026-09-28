"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppNav from "@/components/layout/AppNav";
import { apiFetch, ApiError } from "@/lib/api";

type AuthState = "loading" | "authenticated";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [authState, setAuthState] = useState<AuthState>("loading");

  useEffect(() => {
    apiFetch("/api/v1/auth/me")
      .then(() => setAuthState("authenticated"))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
        } else {
          // Non-auth error (network failure, 5xx) — still redirect to login
          router.replace("/login");
        }
      });
  }, [router]);

  if (authState === "loading") {
    return (
      <div
        style={{
          minHeight: "100vh",
          background: "var(--canvas)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        aria-label="Loading"
        role="status"
      >
        <span
          style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: "var(--text-ui)",
            color: "var(--ink-3)",
          }}
        >
          Loading&hellip;
        </span>
      </div>
    );
  }

  return (
    <>
      <AppNav />
      <main
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          paddingInline: "var(--s6)",
          paddingTop: "var(--s8)",
          paddingBottom: "var(--s12)",
        }}
      >
        {children}
      </main>
    </>
  );
}
