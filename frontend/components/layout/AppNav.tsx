"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import VivekaLogo from "./VivekaLogo";

const ThemeToggle = dynamic(() => import("./ThemeToggle"), { ssr: false });

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/reports", label: "Reports" },
  { href: "/watchlist", label: "Watchlist" },
] as const;

export default function AppNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Application navigation"
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
        <Link href="/dashboard" style={{ textDecoration: "none", flexShrink: 0 }}>
          <VivekaLogo />
        </Link>

        <div style={{ display: "flex", alignItems: "center", gap: "var(--s6)" }}>
          <ul
            role="list"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--s4)",
              margin: 0,
              padding: 0,
              listStyle: "none",
            }}
          >
            {NAV_LINKS.map(({ href, label }) => {
              const isActive = pathname === href || pathname.startsWith(href + "/");
              return (
                <li key={href}>
                  <Link
                    href={href}
                    style={{
                      fontFamily: "'DM Sans', system-ui, sans-serif",
                      fontSize: "var(--text-ui)",
                      fontWeight: isActive ? 600 : 400,
                      color: isActive ? "var(--brand)" : "var(--ink-2)",
                      textDecoration: "none",
                      paddingBlock: "var(--s1)",
                      borderBottom: isActive
                        ? "2px solid var(--brand)"
                        : "2px solid transparent",
                      transition: "color 0.15s, border-color 0.15s",
                    }}
                    aria-current={isActive ? "page" : undefined}
                  >
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>

          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
