/**
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *  QA Accessibility · Design System Tokens
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 *  Direction: "Technical Trust" — Industrial Utilitarian × Luxury Refined
 *
 *  Contrast: the pairings asserted in `__tests__/tokens.contrast.test.ts` are
 *  validated against WCAG 2.2 by computing the real ratio from these values —
 *  text tokens on their surfaces (1.4.3, ≥4.5:1), `text.onAccent` on every
 *  solid button background (1.4.3, ≥4.5:1) and accent borders/indicators on
 *  the dark surfaces (1.4.11, ≥3:1). Pairings outside that test are NOT
 *  claimed to be validated; add them to the test rather than assuming.
 *
 *  Fonts (loaded in index.html via Google Fonts):
 *    Display / Headings: Plus Jakarta Sans (700/800)
 *    Body:               DM Sans (400/500/600)
 *    Code:               JetBrains Mono (400)
 */

// ─── Color Palette ───────────────────────────────────────────────────────────
export const colors = {
  // Core surfaces (dark-first)
  bg: {
    root: "#0B1120",          // deepest background
    surface: "#111827",       // cards, panels
    elevated: "#1E293B",      // elevated cards, modals
    subtle: "#1A2332",        // slightly lifted from root
    overlay: "rgba(0,0,0,0.6)",
  },

  // Text — all pass ≥4.5:1 on bg.root / bg.surface
  text: {
    primary: "#F1F5F9",       // 15.4:1 on #0B1120
    secondary: "#94A3B8",     // 6.3:1 on #0B1120
    tertiary: "#7B8BA3",      // 5.0:1 on #0B1120 — meets AA for all text sizes
    inverse: "#0F172A",       // dark text for light backgrounds
    onAccent: "#FFFFFF",      // white on teal/danger buttons
  },

  // Brand accent — teal
  accent: {
    // teal-700. Menor passo da rampa teal que garante 5.47:1 com texto branco
    // (1.4.3): teal-500 dava 2.49:1 e teal-600 3.74:1, ambos reprovados. Ainda
    // rende 3.44:1 sobre bg.root, então segue válido como borda/indicador (1.4.11).
    DEFAULT: "#0F766E",       // teal-700 — primary CTA (5.47:1 com #FFFFFF)
    hover: "#115E59",         // teal-800 (7.58:1 com #FFFFFF)
    subtle: "#042F2E",        // teal-950ish — subtle bg
    muted: "rgba(20,184,166,0.12)", // glow overlay
    text: "#5EEAD4",          // teal-300 — text on dark (10.2:1 on #0B1120)
  },

  // Semantic
  danger: {
    // red-600. Menor passo da rampa red que garante 4.83:1 com texto branco
    // (1.4.3); red-500 dava 3.76:1. Para texto vermelho sobre fundo escuro use
    // `danger.text`, não este token.
    DEFAULT: "#DC2626",       // red-600 (4.83:1 com #FFFFFF)
    bg: "#2D1215",            // dark red bg
    text: "#FCA5A5",          // red-300 (10.1:1 on #111827)
    border: "#7F1D1D",
  },
  warning: {
    DEFAULT: "#F59E0B",       // amber-500
    bg: "#2D2305",            // dark amber bg
    text: "#FCD34D",          // amber-300 (11.6:1 on #111827)
    border: "#78350F",
  },
  success: {
    DEFAULT: "#22C55E",       // green-500
    bg: "#052E16",            // dark green bg
    text: "#86EFAC",          // green-300 (11.2:1 on #111827)
    border: "#166534",
  },
  info: {
    DEFAULT: "#3B82F6",       // blue-500
    bg: "#172554",            // dark blue bg
    text: "#93C5FD",          // blue-300 (8.5:1 on #111827)
    border: "#1E40AF",
  },

  // Borders & dividers
  border: {
    DEFAULT: "#1E293B",       // subtle border
    strong: "#334155",        // prominent border
    focus: "#14B8A6",         // focus ring color (teal)
  },

  // Severity palette (for issue cards)
  severity: {
    critical: { bg: "#2D1215", text: "#FCA5A5", border: "#7F1D1D", badge: "#DC2626", label: "Crítico" },
    high:     { bg: "#2D1A05", text: "#FDBA74", border: "#78350F", badge: "#EA580C", label: "Alto" },
    medium:   { bg: "#2D2305", text: "#FCD34D", border: "#78350F", badge: "#D97706", label: "Médio" },
    low:      { bg: "#052E16", text: "#86EFAC", border: "#166534", badge: "#16A34A", label: "Baixo" },
  },

  // Checklist status
  status: {
    pass:           { color: "#22C55E", bg: "#052E16", label: "Aprovado" },
    fail:           { color: "#EF4444", bg: "#2D1215", label: "Falhou" },
    manual:         { color: "#F59E0B", bg: "#2D2305", label: "Verificação manual" },
    not_applicable: { color: "#64748B", bg: "#1E293B", label: "Não aplicável" },
  },
} as const;

// ─── Typography ──────────────────────────────────────────────────────────────
export const font = {
  display: '"Plus Jakarta Sans", sans-serif',
  body: '"DM Sans", sans-serif',
  mono: '"JetBrains Mono", monospace',

  // Sizes (rem-based in concept, px for RN)
  size: {
    xs: 11,
    sm: 13,
    base: 15,
    md: 16,
    lg: 18,
    xl: 22,
    "2xl": 28,
    "3xl": 36,
  },

  // Weights
  weight: {
    regular: "400" as const,
    medium: "500" as const,
    semibold: "600" as const,
    bold: "700" as const,
    extrabold: "800" as const,
  },

  // Line heights
  leading: {
    tight: 1.15,
    snug: 1.3,
    normal: 1.5,
    relaxed: 1.7,
  },

  // Letter spacing
  tracking: {
    tight: -0.5,
    normal: 0,
    wide: 0.5,
    wider: 1,
    widest: 1.5,
  },
} as const;

// ─── Spacing ─────────────────────────────────────────────────────────────────
export const space = {
  0: 0,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
  16: 64,
} as const;

// ─── Radii ───────────────────────────────────────────────────────────────────
export const radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  full: 9999,
} as const;

// ─── Shadows ─────────────────────────────────────────────────────────────────
export const shadow = {
  sm: {
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  md: {
    shadowColor: "#000",
    shadowOpacity: 0.25,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  lg: {
    shadowColor: "#000",
    shadowOpacity: 0.35,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  glow: {
    shadowColor: "#14B8A6",
    shadowOpacity: 0.3,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 0 },
    elevation: 6,
  },
} as const;

// ─── Motion (durations in ms) ────────────────────────────────────────────────
export const motion = {
  fast: 150,
  normal: 250,
  slow: 400,
  spring: { damping: 15, stiffness: 150 },
} as const;

// ─── Z-index ─────────────────────────────────────────────────────────────────
export const zIndex = {
  base: 0,
  dropdown: 10,
  sticky: 20,
  overlay: 30,
  modal: 40,
  skipLink: 9999,
} as const;

// ─── Accessibility Helpers ───────────────────────────────────────────────────
export const a11y = {
  /** Minimum interactive target size (WCAG 2.5.8 — 44×44) */
  minTarget: 44,

  /** Visually hidden but accessible to screen readers */
  srOnly: {
    position: "absolute" as const,
    width: 1,
    height: 1,
    overflow: "hidden" as const,
    left: -9999,
    top: -9999,
  },

  /**
   * Remove um nó da árvore de acessibilidade em web (aria-hidden), iOS
   * (accessibilityElementsHidden) e Android (importantForAccessibility).
   * Aplica-se ao conteúdo visual já descrito por um texto sr-only irmão.
   */
  hiddenFromAssistiveTech: {
    "aria-hidden": true,
    accessibilityElementsHidden: true,
    importantForAccessibility: "no-hide-descendants" as const,
  },

  /** Focus ring styles applied via index.html (CSS handles this for web) */
  focusRing: {
    outline: `3px solid ${colors.border.focus}`,
    outlineOffset: 2,
  },
} as const;
