━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Phase 0 Design System
ID:          DS-20260925-001
Author:      frontend-design
Owner:       Atharva
Date:        2026-09-25
Version:     v1.0
Status:      Accepted — ready for Arjun implementation
References:  IMP-20260923-001, ARCH-20260923-001, PRD WEB-013 (mode override below)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Phase 0 Design System

> **WEB-013 mode override:** PRD WEB-013 specified "dark mode is the default." The user
> has explicitly overridden this: light and warm is now the default visual theme. Dark
> mode is still fully defined at token level and supported via `prefers-color-scheme`
> and `data-theme="dark"`. Only the *default* has changed.

---

## 1. Design direction

**Audience:** One primary user (Atharva) plus up to four invited contacts. Serious
individual investors doing deep research on Indian equities, particularly BSE/SME names.
Not a casual consumer dashboard — a research terminal.

**Page job (landing):** Explain what the tool is; provide a login path. No data
exposed. Carry the disclaimer. Convey research-grade seriousness.

**Page job (app screens):** Deliver dense, legible research output. Typography hierarchy
over visual decoration. Data is the product.

**Design posture:** Editorial, precise, warm. Not a startup. Not a trading terminal.
Closer to a well-edited financial publication than a dashboard product.

---

## 2. Color palette

### 2.1 Named values

| Token name | Light mode | Dark mode | Role |
|---|---|---|---|
| `--canvas` | `#FAFAF9` | `#17140F` | Page background |
| `--surface` | `#FFFFFF` | `#1E1B16` | Card, panel, input |
| `--surface-warm` | `#F5F1EC` | `#252118` | Hover state, tinted surface |
| `--ink-1` | `#1A1714` | `#EDE9E4` | Primary text |
| `--ink-2` | `#635D56` | `#A09690` | Secondary text, labels |
| `--ink-3` | `#9C9288` | `#6B6560` | Captions, metadata, muted |
| `--border` | `#E4DFD8` | `#2E2A24` | Default border |
| `--border-strong` | `#CEC8C0` | `#3D3930` | Dividers, focused elements |
| `--brand` | `#1B4E82` | `#4A90D9` | Brand blue, primary CTAs |
| `--brand-subtle` | `#EAF1F8` | `#152035` | Brand tinted background |
| `--brand-on` | `#FFFFFF` | `#FFFFFF` | Text on brand backgrounds |
| `--copper` | `#B87829` | `#D4923A` | Accent — burnished copper |
| `--copper-subtle` | `#F5EDE1` | `#2A1C08` | Copper tinted background |
| `--pos` | `#1A6B3C` | `#22C55E` | Positive price movement, gain |
| `--pos-subtle` | `#E8F5EE` | `#0A2014` | Positive tinted background |
| `--neg` | `#B91C1C` | `#EF4444` | Negative price movement, loss |
| `--neg-subtle` | `#FEF2F2` | `#200A0A` | Negative tinted background |

### 2.2 Palette rationale

**Canvas `#FAFAF9`:** Near-white with a single-step warmth bias. Deliberately not the
AI-default warm cream (#F4F1EA) and not clinical white. Warmth is earned through type
colors and the copper accent, not background saturation.

**Ink `#1A1714`:** Warm near-black with a slight red-brown cast. Never pure `#000000`.
Text reads as warm and organic against the canvas.

**Brand `#1B4E82`:** India ink blue. Deep, trustworthy, financial authority. Not the
generic navy (#003366) or SaaS blue (#3B82F6). Chosen for connotation: the color of
a fountain-pen ink used to sign share certificates.

**Copper `#B87829`:** The distinctive accent. Burnished copper — evokes precision
instruments, old market machinery, the color of a BSE trading floor badge. Not
terracotta, not orange, not gold. This is the one place the palette takes a risk.

**Positive/Negative:** Deep forest green and dark red — legible at small sizes without
being garish. Not the neon green/red of a trading terminal.

---

## 3. Typography

### 3.1 Typefaces

| Face | Source | Role |
|---|---|---|
| **Lora** | Google Fonts | Display, hero headlines, report titles, company names in headings, the briefing card header. Editorial gravitas appropriate for published research. |
| **DM Sans** | Google Fonts | All UI chrome: navigation, labels, body copy, data tables, form elements, buttons, captions. Slightly warmer than Inter. |

**Google Fonts URL:**
```
https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;0,700;1,400&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap
```

**Fallback stacks:**
```css
font-family: 'Lora', Georgia, 'Times New Roman', serif;
font-family: 'DM Sans', system-ui, -apple-system, sans-serif;
```

### 3.2 Type scale

All sizes in `rem` (base 16px). Line heights are unitless multipliers.

| Token | rem | px | Line height | Use |
|---|---|---|---|---|
| `--text-xs` | 0.6875rem | 11px | 1.45 | Fine print, timestamps |
| `--text-sm` | 0.75rem | 12px | 1.5 | Captions, metadata |
| `--text-base-sm` | 0.8125rem | 13px | 1.55 | Data labels, badge text, small UI |
| `--text-ui` | 0.875rem | 14px | 1.6 | Body small, feature descriptions |
| `--text-body` | 1rem | 16px | 1.65 | Primary body copy |
| `--text-lg` | 1.125rem | 18px | 1.45 | Subheadings, card titles (DM Sans) |
| `--text-xl` | 1.25rem | 20px | 1.35 | Section headings |
| `--text-2xl` | 1.5rem | 24px | 1.25 | Page-level headings |
| `--text-3xl` | 1.875rem | 30px | 1.2 | Lora display, report titles |
| `--text-4xl` | 2.25rem | 36px | 1.15 | Lora section hero |
| `--text-5xl` | 3rem | 48px | 1.1 | Lora hero headline |

**Responsive headline:** The hero H1 uses `clamp(2rem, 3.6vw, 3rem)` — this is the
right approach for the landing page's two-column layout. Application screen headings
use fixed scale tokens.

### 3.3 Font weight naming

| Weight | DM Sans | Lora | Use |
|---|---|---|---|
| 300 | Light | — | Large display numbers only |
| 400 | Regular | Regular | Body, secondary text |
| 500 | Medium | — | Labels, UI elements |
| 600 | SemiBold | SemiBold | Headings, key data |
| 700 | — | Bold | Hero headlines (Lora only) |

### 3.4 Numeric formatting

All tabular data (prices, percentages, P&L, volume) uses:
```css
font-variant-numeric: tabular-nums;
```
This must be set on any element containing financial figures that appear in columns.
DM Sans includes proper tabular number support.

---

## 4. Spacing

4px base unit. All tokens are multiples of 4px.

| Token | rem | px | Use |
|---|---|---|---|
| `--s1` | 0.25rem | 4px | Icon gap, badge padding-inline |
| `--s2` | 0.5rem | 8px | Badge padding, tight gap |
| `--s3` | 0.75rem | 12px | Button padding-block, row padding |
| `--s4` | 1rem | 16px | Card padding, section gap |
| `--s5` | 1.25rem | 20px | Button padding-inline, form gap |
| `--s6` | 1.5rem | 24px | Card padding comfortable, section side gutter |
| `--s8` | 2rem | 32px | Between card and section |
| `--s10` | 2.5rem | 40px | Column gap in hero grid |
| `--s12` | 3rem | 48px | Section padding-block end |
| `--s16` | 4rem | 64px | Section padding-block start |
| `--s20` | 5rem | 80px | Large section gaps |

**Side gutter rule:** Minimum 16px (`--s4`) at every viewport width. Set once on
`.wrap` as `padding-inline: --s6` and never override to zero on inner elements.

---

## 5. Border radius

| Token | Value | Use |
|---|---|---|
| `--r-sm` | 4px | Badges, chips, small decorative elements |
| `--r-md` | 8px | Buttons, inputs, small cards |
| `--r-lg` | 12px | Primary cards, panels, modals |
| `--r-full` | 9999px | Pills, avatar circles |

**Rule:** Not every element gets a border-radius. Apply by role to mark objects that
need to read as separate containers. Applying the same radius uniformly is a design tell.

---

## 6. Elevation / shadow

| Token | Value | Use |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(26,23,20,.06)` | Subtle lift (hover states) |
| `--shadow-md` | `0 2px 8px rgba(26,23,20,.08), 0 1px 2px rgba(26,23,20,.04)` | Cards on surface |
| `--shadow-lg` | `0 4px 24px rgba(26,23,20,.10), 0 2px 6px rgba(26,23,20,.06)` | Hero card, modal, elevated panel |

Dark mode: base rgba shifted to `rgba(0,0,0, ...)` with higher opacity (see tokens.css).

---

## 7. Component baseline

### 7.1 Button

Primary (brand):
```css
background: var(--brand);
color: var(--brand-on);
border-radius: var(--r-md);
padding: var(--s3) var(--s6);
font-family: DM Sans;
font-size: 0.9375rem;   /* 15px */
font-weight: 500;
```
Hover: `opacity: 0.85` — never `filter: brightness()` which changes hue.
Focus-visible: `outline: 2px solid var(--brand); outline-offset: 3px;`

No arrows appended to button text. No all-caps. Sentence case throughout.

### 7.2 Card

```css
background: var(--surface);
border: 1px solid var(--border);
border-radius: var(--r-lg);
padding: var(--s5) var(--s6);
box-shadow: var(--shadow-md);
```

Lead/highlighted card (e.g. top sector in briefing):
```css
background: var(--copper-subtle);
border-color: var(--copper-subtle);
```

### 7.3 Badge / chip

```css
display: inline-flex;
align-items: center;
gap: var(--s1);
padding: 2px var(--s2);
border-radius: 20px;
font-size: 0.6875rem;   /* 11px */
font-weight: 600;
```

Brand badge: `background: var(--brand-subtle); color: var(--brand)`
Copper badge: `background: var(--copper-subtle); color: var(--copper)`
Positive: `background: var(--pos-subtle); color: var(--pos)`
Negative: `background: var(--neg-subtle); color: var(--neg)`

### 7.4 Data table row

```css
display: flex;
justify-content: space-between;
align-items: baseline;
padding-block: var(--s2);
border-bottom: 1px solid var(--border);
font-variant-numeric: tabular-nums;
```

Sector rank number: `--ink-3`, `font-size: --text-sm`, fixed `width: 12px`, `text-align: right`

### 7.5 Nav

```css
position: sticky;
top: env(safe-area-inset-top, 0px);
z-index: 100;
background: var(--canvas);
border-bottom: 1px solid var(--border);
height: 56px;
```

---

## 8. Landing page structure

```
┌──────────────────────────────────────────────────────┐
│  NAV: Logo mark + "Research" [wordmark]   [Sign in]  │
│  sticky, 56px, canvas background                     │
├──────────────────────────────────────────────────────┤
│  HERO (2-col grid, gap --s12)                        │
│  ┌──────────────────────┐  ┌────────────────────┐   │
│  │ Copper eyebrow       │  │  Briefing card     │   │
│  │ Lora H1 (3rem/clamp) │  │  (surface, shadow- │   │
│  │ Sub text (ink-2)     │  │   lg, radius-lg)   │   │
│  │ [Sign in CTA]        │  │  Live-data preview │   │
│  │ Private note (ink-3) │  │  of 21:00 output   │   │
│  └──────────────────────┘  └────────────────────┘   │
│  Padding: --s16 top, --s12 bottom                    │
├──────────────────────────────────────────────────────┤
│  FEATURES (3-col grid)                               │
│  Cards: surface, border, radius-lg                   │
│  Heading: Lora 15px semibold                         │
│  Label above grid: "What the platform covers"        │
│  ink-3, NOT all-caps                                 │
├──────────────────────────────────────────────────────┤
│  FOOTER                                              │
│  Disclaimer (ink-3, 12px, max 72ch)                  │
│  "Private · by invitation only"                      │
└──────────────────────────────────────────────────────┘
```

Mobile (≤820px): single column. Briefing card stacks below the hero copy.
Features: single column stack.

---

## 9. Motion principles

**Rule:** One orchestrated moment per page load, not scattered entry effects.

Landing page: The three briefing card sectors fade and slide up sequentially
(`fadeUp` keyframe, 400ms ease, delays of 150ms / 300ms / 420ms). Nothing else animates
on load. Hover transitions are `opacity .15s` on buttons only.

Application screens: Use motion only for state transitions that benefit from it
(panel open/close, filter changes). Never scatter fade-in-on-scroll across every card.

All motion must respect:
```css
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
```

---

## 10. Logo mark

An ascending three-bar mark (representing sector ranking) in `--brand` with a copper
vertical line at the trailing edge. SVG, 24×24 viewBox. Product name: **Viveka**
(Sanskrit: discernment, wisdom). Wordmark in DM Sans SemiBold, `--ink-1`, `letter-spacing: -0.015em`.

---

## 11. Tailwind configuration (WEB-013)

The PRD requires Tailwind CSS (WEB-013). These tokens must be configured in
`tailwind.config.js` under `theme.extend.colors` and `theme.extend.fontFamily`:

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        canvas:   'var(--canvas)',
        surface:  'var(--surface)',
        'surface-warm': 'var(--surface-warm)',
        'ink-1':  'var(--ink-1)',
        'ink-2':  'var(--ink-2)',
        'ink-3':  'var(--ink-3)',
        border:   'var(--border)',
        'border-strong': 'var(--border-strong)',
        brand:    'var(--brand)',
        'brand-subtle': 'var(--brand-subtle)',
        copper:   'var(--copper)',
        'copper-subtle': 'var(--copper-subtle)',
        pos:      'var(--pos)',
        'pos-subtle': 'var(--pos-subtle)',
        neg:      'var(--neg)',
        'neg-subtle': 'var(--neg-subtle)',
      },
      fontFamily: {
        display: ['Lora', 'Georgia', 'serif'],
        ui: ['DM Sans', 'system-ui', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        sm: 'var(--r-sm)',
        md: 'var(--r-md)',
        lg: 'var(--r-lg)',
      },
    },
  },
}
```

Arjun sets up this config in Phase 1 alongside the Next.js project scaffold.

---

## 12. Handoff to Arjun

**Deliverables included in this handoff:**

| File | Status | Description |
|---|---|---|
| `docs/design-system.md` | ✓ This document | Full token spec and component baseline |
| `frontend/styles/tokens.css` | ✓ Done | CSS custom properties, both themes |
| Landing page artifact | ✓ Published | Visual reference at artifact URL |

**Arjun's Phase 1 implementation tasks:**

1. Scaffold Next.js project under `frontend/`
2. Install Tailwind CSS; configure `tailwind.config.js` per §11
3. Copy `frontend/styles/tokens.css` into the project
4. Import tokens.css in the root layout (`_app.tsx` or `layout.tsx`)
5. Implement the landing page at `pages/index.tsx` (or `app/page.tsx`) matching the
   artifact exactly — the artifact is the source of truth for layout, typography, and spacing
6. Implement the login page at `pages/login.tsx` (static form; auth logic is Bhima's)
7. Set up the navigation shell (sticky nav, 56px height) for all authenticated pages
8. Implement `font-variant-numeric: tabular-nums` utility class for financial figures

**Do not implement any application data screens in Phase 1.** Those belong to Phase 2+
per the implementation plan (IMP-20260923-001).

**Constraints Arjun must enforce:**
- Never use literal color values in components — always `var(--token-name)` or Tailwind token classes
- `font-variant-numeric: tabular-nums` on every financial figure
- `text-wrap: balance` on all headings
- All CTA text in sentence case — no all-caps, no appended arrows
- Minimum 16px side gutter at every viewport width
- `@media (prefers-reduced-motion: reduce)` respected

---

*DS-20260925-001 · v1.0 · frontend-design · 2026-09-25*
*Handoff to Arjun for Phase 1 implementation*
