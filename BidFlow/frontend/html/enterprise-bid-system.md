---
name: Intelligent Enterprise Bid System
colors:
  surface: '#f7f9fc'
  surface-dim: '#d8dadd'
  surface-bright: '#f7f9fc'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f7'
  surface-container: '#eceef1'
  surface-container-high: '#e6e8eb'
  surface-container-highest: '#e0e3e6'
  on-surface: '#191c1e'
  on-surface-variant: '#414754'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f4'
  outline: '#727785'
  outline-variant: '#c1c6d6'
  surface-tint: '#005bc0'
  primary: '#005bbf'
  on-primary: '#ffffff'
  primary-container: '#1a73e8'
  on-primary-container: '#ffffff'
  inverse-primary: '#adc7ff'
  secondary: '#5e5e60'
  on-secondary: '#ffffff'
  secondary-container: '#e0dfe1'
  on-secondary-container: '#626265'
  tertiary: '#286c00'
  on-tertiary: '#ffffff'
  tertiary-container: '#348800'
  on-tertiary-container: '#010600'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc7ff'
  on-primary-fixed: '#001a41'
  on-primary-fixed-variant: '#004493'
  secondary-fixed: '#e3e2e4'
  secondary-fixed-dim: '#c7c6c8'
  on-secondary-fixed: '#1a1c1d'
  on-secondary-fixed-variant: '#464749'
  tertiary-fixed: '#9bfa6b'
  tertiary-fixed-dim: '#80dd52'
  on-tertiary-fixed: '#072100'
  on-tertiary-fixed-variant: '#1d5200'
  background: '#f7f9fc'
  on-background: '#191c1e'
  surface-variant: '#e0e3e6'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
  mono-code:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  sidebar-width: 260px
  header-height: 64px
  container-max-width: 1440px
  gutter: 24px
  padding-page: 32px
  stack-gap-sm: 8px
  stack-gap-md: 16px
  stack-gap-lg: 24px
---

## Brand & Style

The design system is engineered for a high-stakes professional environment where accuracy, compliance, and efficiency are paramount. The brand personality is **Authoritative, Precise, and Augmentative**, positioning AI not as a gimmick, but as a sophisticated co-pilot for document procurement.

The visual style follows a **Corporate Modern** aesthetic with subtle **Glassmorphism** cues to denote AI-powered layers. It prioritizes clarity and information density without overwhelming the user. The interface should feel like a high-performance workspace—stable, reliable, and intelligently structured to reduce the cognitive load of complex regulatory tasks.

## Colors

The palette is anchored by **Digital Blue (#1a73e8)**, symbolizing trust and technological precision. This is the primary action color used for focal points and AI-driven interactions.

- **Surface & Background:** The primary workspace uses a neutral light gray (`#F5F7FA`) to reduce eye strain during long reading sessions, while pure white (`#FFFFFF`) is reserved for document canvases and cards.
- **Typography:** Deep charcoal (`#303133`) provides high-contrast legibility for body text, with a lighter slate for secondary metadata.
- **Semantic Feedback:** Standardized colors for success, warning, and error states are used strictly for compliance status and validation results to ensure instant user recognition.

## Typography

The system utilizes **Inter** for its exceptional legibility in data-heavy environments and professional character. For specialized AI outputs, code snippets, or document metadata, **JetBrains Mono** is introduced to provide a distinct "system-level" feel.

- **Hierarchy:** Use bold weights sparingly for headers to maintain a clean, un-cluttered look. 
- **Readability:** Body text is set at 14px with a generous 1.5x line height to facilitate the review of long-form bidding documents.
- **Data Display:** Numerical data and compliance tags should use the mono-spaced font variants to ensure alignment in tables.

## Layout & Spacing

The layout is a structured **Fixed-Fluid Hybrid** optimized for 1920x1080 resolution. 

- **Global Navigation:** A fixed 260px sidebar handles primary module switching (Drafting, Compliance, Archive). A 64px top bar manages global search, AI status, and user profile.
- **The Workspace:** The main content area utilizes a 12-column grid. For document editing, a centered "Paper" layout is used (8 columns) with side-panels for AI suggestions (4 columns).
- **Rhythm:** An 8px base unit governs all spacing. Page margins are set to 32px to provide breathing room, while internal card padding remains at 24px for a compact yet professional density.

## Elevation & Depth

This design system uses a **Tonal Layering** approach combined with **Lightweight Shadows** to define hierarchy without adding visual noise.

- **Level 0 (Background):** `#F5F7FA` - The canvas.
- **Level 1 (Cards/Sidebar):** White background with a 1px border (`#EBEEF5`) and no shadow. Used for secondary information.
- **Level 2 (Active Elements):** White background with a soft, diffused shadow: `0 2px 12px 0 rgba(0,0,0,0.05)`. Used for primary content containers.
- **Level 3 (Modals/Popovers):** Higher elevation shadow: `0 8px 24px rgba(0,0,0,0.12)`.
- **AI Accents:** Elements generated or highlighted by AI utilize a subtle blue inner-glow or a backdrop-blur (Glassmorphism) to distinguish them from manual entries.

## Shapes

The design system adopts a **Medium Rounded** language. A standard **8px (0.5rem)** radius is applied to all primary components (buttons, input fields, cards). 

- **Small Components:** Tags and badges use a 4px radius to maintain sharpness at small scales.
- **Large Components:** Modals and large dashboard sections may scale up to 12px or 16px to soften the overall interface.
- **Consistency:** All borders should be 1px wide, using `#DCDFE6` for interactive states and `#EBEEF5` for static dividers.

## Components

Following the **Element Plus** visual logic, components are clean, functional, and state-aware.

- **Buttons:** Primary buttons use the `#1a73e8` fill. AI-action buttons should feature a subtle gradient or a "Sparkle" icon prefix.
- **Input Fields:** Use 8px rounded corners with a focus state border of 2px in the primary blue. Labels are positioned above the field for clarity.
- **Compliance Chips/Badges:** Pill-shaped with light background tints of the semantic colors (e.g., Light Green background with Dark Green text for "Compliant").
- **AI Insight Cards:** Specifically styled cards with a left-hand blue border accent to indicate machine-generated suggestions or warnings.
- **Data Tables:** Borderless between rows, using a subtle background hover state (`#F2F6FC`). Headers are sticky and use a light gray background with bold labels.
- **Checkboxes & Radios:** Standard 8px rounded squares for checkboxes; circular for radios. Always use the primary blue for the active state.