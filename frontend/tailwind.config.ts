import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)",
        surface: "var(--surface)",
        "surface-warm": "var(--surface-warm)",
        "ink-1": "var(--ink-1)",
        "ink-2": "var(--ink-2)",
        "ink-3": "var(--ink-3)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        brand: "var(--brand)",
        "brand-subtle": "var(--brand-subtle)",
        copper: "var(--copper)",
        "copper-subtle": "var(--copper-subtle)",
        pos: "var(--pos)",
        "pos-subtle": "var(--pos-subtle)",
        neg: "var(--neg)",
        "neg-subtle": "var(--neg-subtle)",
      },
      fontFamily: {
        display: ["Lora", "Georgia", "serif"],
        ui: ["DM Sans", "system-ui", "-apple-system", "sans-serif"],
      },
      borderRadius: {
        sm: "var(--r-sm)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
      },
    },
  },
  plugins: [],
};

export default config;
