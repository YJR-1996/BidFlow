---
name: Precision Enterprise
colors:
  surface: '#f3faff'
  surface-dim: '#c7dde9'
  surface-bright: '#f3faff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#e6f6ff'
  surface-container: '#dbf1fe'
  surface-container-high: '#d5ecf8'
  surface-container-highest: '#cfe6f2'
  on-surface: '#071e27'
  on-surface-variant: '#414754'
  inverse-surface: '#1e333c'
  inverse-on-surface: '#dff4ff'
  outline: '#727785'
  outline-variant: '#c1c6d6'
  surface-tint: '#005bc0'
  primary: '#005bbf'
  on-primary: '#ffffff'
  primary-container: '#1a73e8'
  on-primary-container: '#ffffff'
  inverse-primary: '#adc7ff'
  secondary: '#2b5bb5'
  on-secondary: '#ffffff'
  secondary-container: '#759efd'
  on-secondary-container: '#00337c'
  tertiary: '#9e4300'
  on-tertiary: '#ffffff'
  tertiary-container: '#c55500'
  on-tertiary-container: '#0e0200'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc7ff'
  on-primary-fixed: '#001a41'
  on-primary-fixed-variant: '#004493'
  secondary-fixed: '#d9e2ff'
  secondary-fixed-dim: '#b0c6ff'
  on-secondary-fixed: '#001945'
  on-secondary-fixed-variant: '#00429c'
  tertiary-fixed: '#ffdbcb'
  tertiary-fixed-dim: '#ffb691'
  on-tertiary-fixed: '#341100'
  on-tertiary-fixed-variant: '#783100'
  background: '#f3faff'
  on-background: '#071e27'
  surface-variant: '#cfe6f2'
  success-green: '#34a853'
  warning-amber: '#fbbc04'
  error-red: '#ea4335'
  surface-gray: '#f8f9fa'
  border-subtle: '#dadce0'
typography:
  display-lg:
    fontFamily: Manrope
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Manrope
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 28px
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
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  sidebar-width: 260px
  container-max-width: 1440px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 32px
  stack-gap: 12px
---

## Brand & Style

This design system is engineered for **BidFlow**, an AI-powered enterprise platform where high-stakes accuracy meets document automation. The brand personality is **authoritative, analytical, and reliable**, designed to instill confidence in procurement professionals and bid managers.

The chosen style is **Corporate / Modern**, characterized by a rigorous adherence to hierarchy, structured data visualization, and an emphasis on focus. It evolves beyond standard UI kits by introducing subtle depth and refined typography to create a "high-end SaaS" experience. The interface prioritizes clarity over ornamentation, ensuring that complex compliance checklists and generated document drafts remain the primary focus of the user's attention.

## Colors

The color strategy uses **Professional Blue (#1a73e8)** as the anchor, representing intelligence and trust. 

- **Primary:** Used for the most critical actions, active states, and AI-related highlights.
- **Secondary:** A deeper navy for sidebar backgrounds and high-level headers to provide grounding.
- **Neutrals:** A palette of cool-toned grays (`#455a64`) ensures text readability and subtle UI scaffolding.
- **Functional Colors:** Standard semantic colors (Red, Amber, Green) are used strictly for compliance status—Critical Risks (Red), Warnings (Amber), and Passed Checks (Green).

The interface utilizes a **Light Mode** default to mimic the white-paper environment of bidding documents, reducing eye strain during long-form reading and editing.

## Typography

The typography system is built for legibility in data-dense environments. 

- **Headlines:** **Manrope** provides a refined, modern geometric feel that looks premium in large formats.
- **Body:** **Inter** is used for all UI text and document content due to its exceptional readability and neutral character.
- **Labels & Metadata:** **JetBrains Mono** is utilized sparingly for compliance codes, document IDs, and technical metadata, providing a "system-verified" look to AI outputs.

The scale is designed to handle hierarchical document structures (H1-H4) while maintaining clear distinctions between user-generated content and platform UI.

## Layout & Spacing

This design system employs a **Fixed Grid within a Fluid Shell**. 

- **Primary Structure:** A permanent left-hand sidebar (260px) houses navigation, while the main content area occupies the remaining width, capped at 1440px for optimal line length in document editing.
- **The Dashboard:** Follows a 12-column grid with 24px gutters. Elements such as "Compliance Score" or "Recent Bids" span 3, 4, or 6 columns depending on priority.
- **Auth Flow:** Login and Registration pages bypass the sidebar structure in favor of a **centered card layout** (max-width: 440px) to maximize focus.
- **Responsive Behavior:** At 1024px and below, the sidebar collapses into a hamburger menu. Margins compress from 32px to 16px to maximize screen real estate for document viewing.

## Elevation & Depth

To maintain a professional enterprise feel, the design system avoids heavy shadows. Instead, it uses **Tonal Layers** and **Low-Contrast Outlines**.

- **Level 0 (Background):** `surface-gray` (#f8f9fa).
- **Level 1 (Cards/Sidebar):** Pure white background with a 1px solid border (`border-subtle`).
- **Level 2 (Active States/Modals):** A very soft ambient shadow (Blur: 12px, Y: 4px, Color: rgba(0,0,0,0.05)) to lift interactive elements during specific tasks.
- **AI Layers:** Elements generated or suggested by AI should feature a subtle primary-tinted inner glow or a faint blue backdrop blur to distinguish them from manual entries.

## Shapes

The design system utilizes a **Soft (0.25rem)** roundedness profile. This "near-sharp" approach maintains a serious, business-oriented aesthetic while feeling more modern than strictly square corners. 

- **Standard Elements:** Buttons, Input fields, and small Chips use 4px (`rounded`).
- **Containers:** Large form cards and data tables use 8px (`rounded-lg`).
- **Interactive States:** Focus rings should follow the 4px radius with a 2px offset.

## Components

### Buttons
- **Primary:** Solid `#1a73e8` with white text. High-contrast, used for "Generate Bid" or "Submit".
- **Secondary:** White background with `#1a73e8` border and text. Used for "Save Draft" or "Export".
- **Ghost:** No border or background until hover. Used for secondary navigation inside the content area.

### Cards
Cards are the primary container for the "BidFlow" UI. They must have a white background, 1px `#dadce0` border, and 24px internal padding. Card headers should be separated by a subtle horizontal rule.

### Input Fields
Inputs must clearly define states:
- **Default:** Light gray border.
- **Active/Focus:** Primary blue border with a subtle 2px outer glow.
- **Error:** Red border with a small error label below in `label-sm`.
- **AI-Filled:** A very light blue background tint to indicate the value was generated by the platform.

### Chips & Tags
Used primarily for compliance status.
- **Passed:** Green background (10% opacity) with dark green text.
- **Pending:** Gray background (10% opacity) with dark gray text.
- **Risk:** Red background (10% opacity) with dark red text.

### Sidebar
The sidebar uses the secondary navy color with high-contrast white or light-blue icons. Active menu items are highlighted with a vertical primary-blue bar on the left edge.