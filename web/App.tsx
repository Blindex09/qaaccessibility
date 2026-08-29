import React, { useState, useEffect } from "react";
import { Platform, SafeAreaView, StyleSheet, Text, View } from "react-native";
import { SettingsScreen } from "./src/screens/SettingsScreen";
import { ChatScreen } from "./src/screens/ChatScreen";
import { colors, font, a11y } from "./src/design/tokens";

type Screen = "chat" | "settings";

const SCREEN_TITLES: Record<Screen, string> = {
  chat:     "QA Accessibility — Assistente",
  settings: "QA Accessibility — Configurações de IA",
};

function getInitialScreen(): Screen {
  if (typeof window === "undefined") return "chat";
  const hash = window.location.hash.replace(/^#\/?/, "").split("/")[0];
  if (hash === "settings") return "settings";
  const p = window.location.pathname.replace(/^\//, "").split("/")[0];
  if (p === "settings") return "settings";
  return "chat";
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(getInitialScreen);
  const [navAnnouncement, setNavAnnouncement] = useState<string>("");
  const [skipFocused, setSkipFocused] = useState(false);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = "pt-BR";
      document.title = SCREEN_TITLES[getInitialScreen()];
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    function parse(): Screen {
      const hash = window.location.hash.replace(/^#\/?/, "").split("/")[0];
      if (hash === "settings") return "settings";
      const p = window.location.pathname.replace(/^\//, "").split("/")[0];
      if (p === "settings") return "settings";
      return "chat";
    }
    function onChange() {
      setScreen(parse());
    }
    window.addEventListener("hashchange", onChange);
    window.addEventListener("popstate", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
      window.removeEventListener("popstate", onChange);
    };
  }, []);

  function navigate(to: Screen) {
    setScreen(to);
    if (typeof window !== "undefined") {
      window.history.pushState(null, "", to === "chat" ? "/" : `/${to}`);
      document.title = SCREEN_TITLES[to];
    }
    // Anuncia a nova página para leitores de tela
    setNavAnnouncement("");
    setTimeout(() => setNavAnnouncement(SCREEN_TITLES[to]), 50);
    // Move foco para o conteúdo principal apos navegacao SPA
    setTimeout(() => {
      if (typeof document === "undefined") return;
      const el = document.getElementById("main-content");
      if (el) {
        el.setAttribute("tabindex", "-1");
        el.focus();
      }
    }, 120);
  }

  return (
    <SafeAreaView style={styles.root}>
      {/* Skip link — WCAG 2.4.1 */}
      {Platform.OS === "web" && React.createElement("a", {
        href: "#main-content",
        className: "skip-link",
        style: {
          position: "absolute" as const,
          top: skipFocused ? 0 : -100,
          left: 16,
          zIndex: 99999,
          backgroundColor: colors.accent.DEFAULT,
          padding: "12px 24px",
          color: "#ffffff",
          fontWeight: "700" as const,
          fontSize: 14,
          fontFamily: font.display,
          textDecoration: "none",
          borderRadius: "0 0 10px 10px",
          boxShadow: "0 4px 12px rgba(20,184,166,0.4)",
          transition: "top 0.15s ease",
        },
        onFocus: () => setSkipFocused(true),
        onBlur: () => setSkipFocused(false),
        onClick: (e: any) => {
          e.preventDefault();
          const el = typeof document !== "undefined"
            ? document.getElementById("main-content") : null;
          if (el) { el.setAttribute("tabindex", "-1"); el.focus(); }
        },
      }, "Pular para o conteúdo principal")}

      {/* Landmark banner — identifica o app para leitores de tela (h1 da página) */}
      <View role="banner" style={styles.srOnly as any}>
        <Text accessibilityRole="header" aria-level={1}>
          QA Accessibility — Auditoria de Acessibilidade com IA
        </Text>
      </View>

      {/* Live region — anuncia mudança de página */}
      <View accessibilityLiveRegion="polite" style={styles.srOnly}>
        <Text>{navAnnouncement}</Text>
      </View>

      {/* Conteúdo principal — landmark main (WCAG 2.4.1) */}
      <View role="main" style={styles.mainContent} nativeID="main-content">
        {screen === "chat" && <ChatScreen onOpenSettings={() => navigate("settings")} />}
        {screen === "settings" && <SettingsScreen onBack={() => navigate("chat")} />}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg.root },
  mainContent: { flex: 1 },
  srOnly: a11y.srOnly as any,
});
