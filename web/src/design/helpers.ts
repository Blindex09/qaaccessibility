/**
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *  QA Accessibility · Design System Helpers
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 *
 *  Platform-aware typography helpers that work with StyleSheet.create()
 */
import { Platform } from "react-native";
import { font } from "./tokens";

/** Font family for headings (web only) */
export const displayFont = Platform.OS === "web" ? font.display : undefined;

/** Font family for body text (web only) */
export const bodyFont = Platform.OS === "web" ? font.body : undefined;

/** Font family for code (web uses JetBrains Mono, native uses system monospace) */
export const monoFont = Platform.OS === "web" ? font.mono : "monospace";
