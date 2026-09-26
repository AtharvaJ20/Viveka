import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
}

export default function Button({
  variant = "primary",
  children,
  style,
  ...props
}: ButtonProps) {
  const base: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "var(--r-md)",
    padding: "var(--s3) var(--s6)",
    fontFamily: "'DM Sans', system-ui, sans-serif",
    fontSize: "0.9375rem",
    fontWeight: 500,
    cursor: "pointer",
    border: "none",
    textDecoration: "none",
    transition: "opacity .15s",
  };

  const variants: Record<string, React.CSSProperties> = {
    primary: {
      background: "var(--brand)",
      color: "var(--brand-on)",
    },
    ghost: {
      background: "transparent",
      color: "var(--brand)",
      border: "1px solid var(--brand)",
    },
  };

  return (
    <button
      style={{ ...base, ...variants[variant], ...style }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.opacity = "0.85";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.opacity = "1";
      }}
      {...props}
    >
      {children}
    </button>
  );
}
