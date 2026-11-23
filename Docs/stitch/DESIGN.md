---
name: Modern Wealth & Investment
colors:
  surface: '#f9f9ff'
  surface-dim: '#d3daef'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f1f3ff'
  surface-container: '#e9edff'
  surface-container-high: '#e1e8fd'
  surface-container-highest: '#dce2f7'
  on-surface: '#141b2b'
  on-surface-variant: '#3c4a43'
  inverse-surface: '#293040'
  inverse-on-surface: '#edf0ff'
  outline: '#6b7b72'
  outline-variant: '#bacac1'
  surface-tint: '#006c4f'
  primary: '#006c4f'
  on-primary: '#ffffff'
  primary-container: '#00d09c'
  on-primary-container: '#00533c'
  inverse-primary: '#2fe0aa'
  secondary: '#3247e2'
  on-secondary: '#ffffff'
  secondary-container: '#4f63fb'
  on-secondary-container: '#fffbff'
  tertiary: '#b91a24'
  on-tertiary: '#ffffff'
  tertiary-container: '#ff9d96'
  on-tertiary-container: '#960014'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#59fdc5'
  primary-fixed-dim: '#2fe0aa'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#dfe0ff'
  secondary-fixed-dim: '#bcc2ff'
  on-secondary-fixed: '#000b62'
  on-secondary-fixed-variant: '#102bcd'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#f9f9ff'
  on-background: '#141b2b'
  surface-variant: '#dce2f7'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.03em
  display-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
  title-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-sm: 1rem
  margin: 2rem
  margin-sm: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system delivers an optimistic, accessible, and high-clarity investment interface. Rooted in retail wealth creation, the visual tone balances institutional trust with consumer product friendliness. The interface prioritizes confidence, instantaneous comprehension of market volatility, and friction-free transaction flows.

The design movement combines **Contemporary Clean / Soft Modern Fintech** with refined utility:
- **Clarity over density:** Spacious layouts and crisp structural compartmentalization reduce financial anxiety.
- **Dynamic semantic feedback:** Clear differentiation between portfolio expansion (teal/emerald) and downturn correction (rose red), anchored by an authoritative digital indigo.
- **Lightweight tactile cues:** Flat surfaces structured by micro-borders and soft hover elevations instead of heavy skeuomorphic layers.

## Colors

The palette establishes a systematic split between transactional brand identity, market states, and high-readability content hierarchy.

- **Primary Teal/Emerald (`#00D09C`):** Represents capital growth, buy actions, SIP confirmations, and positive intraday yields. Used selectively on primary confirmation triggers, positive trendlines, and success feedback surfaces.
- **Secondary Indigo (`#5367FF`):** Serves as the primary brand catalyst and foundational interactive color. Applied across navigational highlights, tab indicators, contextual banners, explore features, and account authentication flows.
- **Negative / Danger (`#EF4444`):** Designates market downturns, sell triggers, stop-loss states, and critical transactional alerts.
- **Neutral Core:**
  - Base White (`#FFFFFF`): Main canvas and baseline layer.
  - Surface Neutral (`#F8F9FA` / `#F3F4F6`): Segmented card backgrounds, stock discovery lists, and metric grouping panels.
  - Border Hairline (`#E5E7EB`): Structural containment lines for cards, tables, and search bars.
  - Primary Text (`#111827`): Ticker symbols, stock prices, headings, and primary account metrics.
  - Secondary Text (`#4B5563`): Sub-labels, holding volume counts, and column metadata.
  - Muted Text (`#9CA3AF`): Rupee symbol affixes, disabled indicators, and timestamps.

## Typography

The type system blends the geometric approachability of Plus Jakarta Sans for titles and financial hero numbers with the strict tabular utility of Inter for market data, transaction ledgers, and body text.

- **Tabular Figures:** Always apply `font-feature-settings: "tnum" 1` to numerical figures, prices, percentages, and Indian Rupee (`₹`) values to prevent layout shift during tick updates.
- **Currency Styling:** Format the Rupee symbol (`₹`) at the same font weight but slightly de-emphasized in color or size when paired with oversized hero figures to keep visual weight on the principal quantity.
- **Hierarchy Rules:** Section titles, market indices (NIFTY, SENSEX), and card heads take Plus Jakarta Sans. Tabular order books, order execution receipts, and analytical small print stay strictly in Inter.

## Layout & Spacing

The layout is built upon an 8px grid (using a 4px sub-grid for compact market data tags, badges, and tick chips).

- **Grid Strategy:**
  - **Desktop (1024px+):** 12-column fluid grid, `margin: 2rem` (max-width bounded at 1280px or 1440px for broad dashboards), `gutter: 1.5rem`.
  - **Tablet (768px - 1023px):** 8-column layout, `margin: 1.5rem`, `gutter: 1rem`.
  - **Mobile (<768px):** 4-column layout, `margin: 1rem`, `gutter: 0.75rem`. Bottom sheets and sticky order trade pads override canvas gutters with full-bleed edges.
- **Rhythm Guidelines:**
  - Use `space-xs` (4px) and `space-sm` (8px) for inline financial tags, badge padding, and tick delta shifts.
  - Use `space-md` (16px) for interior card padding, input fields, and standard list element gaps.
  - Use `space-lg` (24px) for between-card stack gaps and module groupings.
  - Use `space-xl` (32px) for page section separators and key transitions.

## Elevation & Depth

Visual architecture relies on flat container surfaces accented with low-contrast hairpins and diffused ambient layering instead of multi-tiered drop shadows.

- **Baseline Canvas:** Pure `#FFFFFF` backdrops.
- **Container Tiers:** Inner grouped metrics and market card backings sit on `#F8F9FA` or `#F3F4F6` with a uniform `1px solid #E5E7EB` border.
- **Ambient Floating Elevation:** Reserved exclusively for sticky execution docks (e.g., bottom trade pads on mobile), contextual search dropdowns, and modal dialogs:
  - `box-shadow: 0 10px 25px -5px rgba(17, 24, 39, 0.05), 0 8px 10px -6px rgba(17, 24, 39, 0.03)`
- **Hover Micro-Lift:** Asset cards and watchlists raise on hover by -1px translateY accompanied by `box-shadow: 0 4px 12px 0 rgba(17, 24, 39, 0.04)`.

## Shapes

The interface embraces a balanced curvature model where cards and modules convey modern discipline (`rounded-lg` / 16px), while navigational filters, order type switches, and quick-filter tags adopt full-radius pills (`9999px`).

- **Base Cards & Dialogs:** `border-radius: 12px` to `16px`.
- **Form Controls & Inputs:** `border-radius: 8px` to maintain alignment with form labels.
- **Chips, Category Filters, and Status Badges:** `border-radius: 9999px` (Pill geometry) for dynamic readability and tactile appeal.
- **Interactive Action Buttons:** `border-radius: 8px` for tabular/data contexts; `border-radius: 9999px` for sticky bottom-sheet conversion CTAs.

## Components

### Buttons
- **Primary Brand / Action:** Solid Indigo (`#5367FF`) with `#FFFFFF` text. Used for main account navigations, explorations, and multi-step onboarding.
- **Buy / Growth Action:** Solid Teal (`#00D09C`) with `#FFFFFF` text, bold weight (`600`). Triggers instantaneous investment commitments, order completions, and SIP activations.
- **Sell / Exit Action:** Solid Rose (`#EF4444`) with `#FFFFFF` text or neutral ghost style with border. Triggers exits and short orders.
- **Secondary / Ghost:** `#FFFFFF` surface with `1px solid #E5E7EB` border, text `#111827`, shifting to `#F9FAFB` on hover.

### Chips & Pill Tags
- **Market Gainers:** `#E6FAF5` (10% tint of Primary Teal) background with `#00A37A` text, leading with a `+` symbol or upward arrow icon.
- **Market Losers:** `#FEE2E2` background with `#DC2626` text, leading with a `-` symbol or downward arrow icon.
- **Filter Tags:** Pill shape (`9999px` radius), border `1px solid #E5E7EB`, text `#4B5563`. When active: solid `#111827` background with `#FFFFFF` text, or tinted `#5367FF` background.

### Cards & Asset Tiles
- **Structure:** Crisp white background `#FFFFFF`, bordered by `1px solid #E5E7EB`, internal padding `space-md` (16px), corner radius `12px`.
- **Market Item Content Flow:** Left: Company / Fund logo (circular, 40px) followed by ticker symbol (`title-md`) and company name (`body-sm`, `#4B5563`). Right: Live Price (`title-md`, tabular figures) above intraday % change tag.

### Lists & Watchlists
- Clean divider-less or micro-divider rows (`border-bottom: 1px solid #F3F4F6`).
- Hover state transitions row background to `#F9FAFB` seamlessly.
- Numeric columns right-align; text data left-aligns.

### Inputs & Financial Steppers
- **Order Amount Input:** Prominent centered or left-aligned `display-lg` numbers preceded by a fixed `#9CA3AF` Rupee symbol (`₹`). Zero border in focal view or clean `1px solid #E5E7EB` bottom-border/surround.
- **Focused State:** Border transitions to `#5367FF` with `0 0 0 3px rgba(83, 103, 255, 0.15)`.

### Checkboxes, Radios, & Switches
- **Accent Color:** `#5367FF` for preference settings, `#00D09C` for auto-pay mandates and investment disclaimers.
- **Switches:** Smooth rounded pills with white knob and subtle depth shadow.