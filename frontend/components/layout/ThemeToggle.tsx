"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "viveka-theme";

export default function ThemeToggle() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
      setIsDark(true);
    }
  }, []);

  function toggle() {
    const next = !isDark;
    setIsDark(next);
    if (next) {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem(STORAGE_KEY, "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem(STORAGE_KEY, "light");
    }
  }

  return (
    <button
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      style={{
        width: "32px",
        height: "32px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "transparent",
        border: "none",
        borderRadius: "var(--r-full)",
        color: "var(--ink-2)",
        cursor: "pointer",
        transition: "background 150ms ease, opacity 150ms ease",
        flexShrink: 0,
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.background =
          "var(--surface-warm)")
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.background = "transparent")
      }
      onMouseDown={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.opacity = "0.7")
      }
      onMouseUp={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.opacity = "1")
      }
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function MoonIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M15.5 11.5A7 7 0 0 1 6.5 2.5a7.001 7.001 0 1 0 9 9z"
        fill="currentColor"
      />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="9" cy="9" r="3.5" />
      <line x1="9" y1="1" x2="9" y2="3" />
      <line x1="9" y1="15" x2="9" y2="17" />
      <line x1="1" y1="9" x2="3" y2="9" />
      <line x1="15" y1="9" x2="17" y2="9" />
      <line x1="3.22" y1="3.22" x2="4.64" y2="4.64" />
      <line x1="13.36" y1="13.36" x2="14.78" y2="14.78" />
      <line x1="14.78" y1="3.22" x2="13.36" y2="4.64" />
      <line x1="4.64" y1="13.36" x2="3.22" y2="14.78" />
    </svg>
  );
}
