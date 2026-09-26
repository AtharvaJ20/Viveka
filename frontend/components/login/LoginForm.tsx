"use client";

import { useState, type FormEvent } from "react";
import { apiFetch } from "@/lib/api";

export default function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await apiFetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      window.location.href = "/dashboard";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate style={{ width: "100%", maxWidth: "380px" }}>
      <div style={{ marginBottom: "var(--s4)" }}>
        <label
          htmlFor="email"
          style={{
            display: "block",
            fontSize: "var(--text-ui)",
            fontWeight: 500,
            color: "var(--ink-2)",
            marginBottom: "var(--s2)",
          }}
        >
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{
            width: "100%",
            padding: "var(--s3) var(--s4)",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            fontSize: "var(--text-body)",
            color: "var(--ink-1)",
            fontFamily: "'DM Sans', system-ui, sans-serif",
            boxSizing: "border-box",
          }}
        />
      </div>
      <div style={{ marginBottom: "var(--s6)" }}>
        <label
          htmlFor="password"
          style={{
            display: "block",
            fontSize: "var(--text-ui)",
            fontWeight: 500,
            color: "var(--ink-2)",
            marginBottom: "var(--s2)",
          }}
        >
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{
            width: "100%",
            padding: "var(--s3) var(--s4)",
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--r-md)",
            fontSize: "var(--text-body)",
            color: "var(--ink-1)",
            fontFamily: "'DM Sans', system-ui, sans-serif",
            boxSizing: "border-box",
          }}
        />
      </div>

      {error && (
        <div
          role="alert"
          aria-live="polite"
          style={{
            fontSize: "var(--text-ui)",
            color: "var(--neg)",
            marginBottom: "var(--s4)",
          }}
        >
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        style={{
          width: "100%",
          padding: "var(--s3) var(--s6)",
          background: "var(--brand)",
          color: "var(--brand-on)",
          border: "none",
          borderRadius: "var(--r-md)",
          fontFamily: "'DM Sans', system-ui, sans-serif",
          fontSize: "0.9375rem",
          fontWeight: 500,
          cursor: loading ? "not-allowed" : "pointer",
          opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
