/**
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *  QA Accessibility · Design System Tokens
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 *  Direction: "Technical Trust" — Industrial Utilitarian × Luxury Refined
 *
 *  Dois temas, uma só fonte: `palettes.dark` e `palettes.light` (hex). Na web,
 *  `colors` devolve `var(--c-...)` e o tema ativo é decidido pelo CSS
 *  (preferência do sistema, ou `data-theme` escolhido pela pessoa); fora da
 *  web e em testes, `colors` é a paleta escura em hex.
 *
 *  Contrast: the pairings asserted in `__tests__/tokens.contrast.test.ts` are
 *  validated against WCAG 2.2 by computing the real ratio from these values,
 *  in BOTH palettes — text tokens on their surfaces (1.4.3, ≥4.5:1),
 *  `text.onAccent` on every solid button background (1.4.3, ≥4.5:1) and accent
 *  borders/indicators on the surfaces (1.4.11, ≥3:1). Pairings outside that
 *  test are NOT claimed to be validated; add them to the test rather than
 *  assuming.
 *
 *  Fonts (loaded in index.html via Google Fonts):
 *    Display / Headings: Plus Jakarta Sans (700/800)
 *    Body:               DM Sans (400/500/600)
 *    Reading (answers):  Source Serif 4 (400/600)
 *    Code:               JetBrains Mono (400)
 */

// ─── Color Palettes ──────────────────────────────────────────────────────────
const darkPalette = {
  // Core surfaces
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

  // Chat — papéis na conversa, rolagem de ferramentas e botão de envio
  chat: {
    userBg: "rgba(6,182,212,0.07)",
    userAccent: "#22D3EE",    // rótulo/borda da mensagem da pessoa
    assistantBg: "rgba(99,102,241,0.07)",
    assistantAccent: "#A5B4FC", // rótulo/borda da resposta do assistente
    sendBg: "#4F46E5",        // botão enviar (5.7:1 com #FFFFFF)
    sendDisabledBg: "#373890",
    toolBg: "#090D16",
    toolHeaderBg: "#131B2E",
    toolLogBg: "#050811",
    toolLogText: "#A7F3D0",
    toolError: "#F87171",
  },

  // Severity palette (for issue cards)
  severity: {
    critical: { bg: "#2D1215", text: "#FCA5A5", border: "#7F1D1D", badge: "#DC2626" },
    high:     { bg: "#2D1A05", text: "#FDBA74", border: "#78350F", badge: "#EA580C" },
    medium:   { bg: "#2D2305", text: "#FCD34D", border: "#78350F", badge: "#D97706" },
    low:      { bg: "#052E16", text: "#86EFAC", border: "#166534", badge: "#16A34A" },
  },

  // Checklist status
  status: {
    pass:           { color: "#22C55E", bg: "#052E16" },
    fail:           { color: "#EF4444", bg: "#2D1215" },
    manual:         { color: "#F59E0B", bg: "#2D2305" },
    not_applicable: { color: "#64748B", bg: "#1E293B" },
  },
};

type Palette = typeof darkPalette;

/** Tema claro quente: papel off-white, tinta quase preta, o mesmo teal de marca. */
const lightPalette: Palette = {
  bg: {
    root: "#F5F4EE",
    surface: "#FFFFFF",
    elevated: "#FBFAF6",
    subtle: "#EFEDE4",
    overlay: "rgba(31,30,27,0.45)",
  },
  text: {
    primary: "#1F1E1B",
    secondary: "#55524A",
    tertiary: "#67645B",
    inverse: "#FAF9F5",
    onAccent: "#FFFFFF",
  },
  accent: {
    DEFAULT: "#0F766E",
    hover: "#115E59",
    subtle: "#E1F0ED",
    muted: "rgba(15,118,110,0.10)",
    text: "#0B5F58",
  },
  danger: { DEFAULT: "#DC2626", bg: "#FDECEC", text: "#B91C1C", border: "#FCA5A5" },
  warning: { DEFAULT: "#D97706", bg: "#FEF3C7", text: "#92400E", border: "#FCD34D" },
  success: { DEFAULT: "#16A34A", bg: "#DCFCE7", text: "#166534", border: "#86EFAC" },
  info: { DEFAULT: "#2563EB", bg: "#DBEAFE", text: "#1E40AF", border: "#93C5FD" },
  border: {
    DEFAULT: "#E4E1D6",
    strong: "#CFCBBD",
    focus: "#0F766E",
  },
  chat: {
    userBg: "rgba(8,145,178,0.08)",
    userAccent: "#0E7490",
    assistantBg: "rgba(79,70,229,0.06)",
    assistantAccent: "#4338CA",
    sendBg: "#4F46E5",
    sendDisabledBg: "#373890",
    toolBg: "#F0EEE6",
    toolHeaderBg: "#E8E5DA",
    toolLogBg: "#F7F6F1",
    toolLogText: "#065F46",
    toolError: "#B91C1C",
  },
  severity: {
    critical: { bg: "#FDECEC", text: "#991B1B", border: "#FCA5A5", badge: "#DC2626" },
    high:     { bg: "#FFEDD5", text: "#9A3412", border: "#FDBA74", badge: "#EA580C" },
    medium:   { bg: "#FEF3C7", text: "#92400E", border: "#FCD34D", badge: "#D97706" },
    low:      { bg: "#DCFCE7", text: "#166534", border: "#86EFAC", badge: "#16A34A" },
  },
  status: {
    pass:           { color: "#15803D", bg: "#DCFCE7" },
    fail:           { color: "#DC2626", bg: "#FDECEC" },
    manual:         { color: "#B45309", bg: "#FEF3C7" },
    not_applicable: { color: "#64748B", bg: "#ECEAE0" },
  },
};

export const palettes = { dark: darkPalette, light: lightPalette } as const;

// ─── Tema em runtime (web) ───────────────────────────────────────────────────
const isBrowser = typeof document !== "undefined" && typeof window !== "undefined";

/** `--c-bg-root`, `--c-accent` (DEFAULT some do nome), `--c-severity-high-bg`. */
function cssVarName(path: string[]): string {
  const parts = path[path.length - 1] === "DEFAULT" ? path.slice(0, -1) : path;
  return `--c-${parts.join("-").replace(/_/g, "-")}`;
}

function mapPalette<T>(node: T, path: string[], leaf: (value: string, path: string[]) => string): T {
  if (typeof node === "string") return leaf(node, path) as unknown as T;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    out[key] = mapPalette(value, [...path, key], leaf);
  }
  return out as T;
}

function declarations(palette: Palette): string {
  const lines: string[] = [];
  mapPalette(palette, [], (value, path) => {
    lines.push(`${cssVarName(path)}:${value};`);
    return value;
  });
  return lines.join("");
}

/** CSS completo dos dois temas: sistema por padrão, `data-theme` força um. */
export function themeCss(): string {
  const dark = declarations(darkPalette);
  const light = declarations(lightPalette);
  return (
    `:root{color-scheme:dark light;${dark}}` +
    `@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){${light}}}` +
    `:root[data-theme="light"]{${light}}` +
    `:root[data-theme="dark"]{${dark}}`
  );
}

export type ThemePreference = "system" | "light" | "dark";

const THEME_STORAGE_KEY = "qa-theme";

export function readThemePreference(): ThemePreference {
  if (!isBrowser) return "system";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

export function applyThemePreference(preference: ThemePreference): void {
  if (!isBrowser) return;
  const root = document.documentElement;
  if (preference === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", preference);
  try {
    if (preference === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Sem armazenamento (modo privado): o tema vale só nesta sessão.
  }
}

if (isBrowser) {
  let style = document.getElementById("qa-theme-vars") as HTMLStyleElement | null;
  if (!style) {
    style = document.createElement("style");
    style.id = "qa-theme-vars";
    document.head.appendChild(style);
  }
  style.textContent = themeCss();
  applyThemePreference(readThemePreference());
}

export const colors: Palette = isBrowser
  ? mapPalette(darkPalette, [], (_value, path) => `var(${cssVarName(path)})`)
  : darkPalette;

// ─── Typography ──────────────────────────────────────────────────────────────
export const font = {
  display: '"Plus Jakarta Sans", sans-serif',
  body: '"DM Sans", sans-serif',
  serif: '"Source Serif 4", Georgia, serif',
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
  composer: 24,
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
