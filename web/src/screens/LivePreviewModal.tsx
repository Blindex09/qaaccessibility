import React, { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Platform,
  ScrollView,
  useWindowDimensions,
} from "react-native";
import { colors, font, a11y } from "../design/tokens";
import { BASE_URL } from "../services/chat";

interface Props {
  sessionId: string;
  totalPages: number;
}

const isWeb = Platform.OS === "web";

// Abaixo desse breakpoint o painel lateral vira tela cheia -- 45% da largura
// de uma viewport de celular estreita demais pra ser um painel de leitura.
const MOBILE_BREAKPOINT = 768;

export function LivePreviewModal({ sessionId, totalPages }: Props) {
  const [currentPage, setCurrentPage] = useState(0);
  const [mode, setMode] = useState<"fixed" | "original">("fixed");
  const { width: windowWidth } = useWindowDimensions();
  const isMobile = windowWidth < MOBILE_BREAKPOINT;

  const previewUrl = `${BASE_URL}/preview/render/${sessionId}/${currentPage}?mode=${mode}`;

  // O preview roda numa origem própria (porta do backend), então não dá pra
  // ler window.location do iframe depois que o usuário navega clicando num
  // link interno -- o backend injeta um script de confiança (liberado no CSP
  // só por hash exato) que avisa a página/modo atuais via postMessage; aqui a
  // gente escuta isso pra manter os chips e o toggle Corrigido/Original
  // sincronizados com o que está de fato carregado no iframe.
  React.useEffect(() => {
    if (!isWeb || typeof window === "undefined") return;

    let previewOrigin: string | null = null;
    try {
      previewOrigin = new URL(BASE_URL).origin;
    } catch {
      previewOrigin = null;
    }

    function handleMessage(event: MessageEvent) {
      if (previewOrigin && event.origin !== previewOrigin) return;
      const data = event.data;
      if (!data || data.source !== "a11y-live-preview" || data.sessionId !== sessionId) return;

      if (typeof data.pageIndex === "number" && data.pageIndex >= 0 && data.pageIndex < totalPages) {
        setCurrentPage((prev) => (prev === data.pageIndex ? prev : data.pageIndex));
      }
      if ((data.mode === "fixed" || data.mode === "original")) {
        setMode((prev) => (prev === data.mode ? prev : data.mode));
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [sessionId, totalPages]);


  return (
    <View style={styles.panelShell} role="complementary" aria-label="Live Preview Acessível">
      <View
        style={[styles.container, isMobile && styles.containerMobile]}
      >
        {/* Header do Painel Replit */}
        <View style={styles.header}>
          <View style={styles.headerTitleGroup}>
            <Text style={styles.title}>
              Live Preview Acessível
            </Text>

            {/* Alternador de Modo (Before / After) — padrão tablist para leitores de tela */}
            <View style={styles.toggleGroup} accessibilityRole="tablist" aria-label="Modo de visualização">
              <TouchableOpacity
                onPress={() => setMode("fixed")}
                accessibilityRole="tab"
                accessibilityLabel="Mostrar visualização corrigida pela IA"
                accessibilityState={{ selected: mode === "fixed" }}
                aria-selected={mode === "fixed"}
                style={[styles.toggleBtn, mode === "fixed" && styles.toggleActive]}
              >
                <Text style={[styles.toggleText, mode === "fixed" && styles.toggleActiveText]}>
                  Corrigido (IA)
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => setMode("original")}
                accessibilityRole="tab"
                accessibilityLabel="Mostrar versão original com falhas"
                accessibilityState={{ selected: mode === "original" }}
                aria-selected={mode === "original"}
                style={[styles.toggleBtn, mode === "original" && styles.toggleActiveDanger]}
              >
                <Text style={[styles.toggleText, mode === "original" && styles.toggleActiveText]}>
                  Original (Com Falhas)
                </Text>
              </TouchableOpacity>
            </View>
          </View>

        </View>

        {/* Barra de Navegação de Páginas (1 até 50) */}
        {totalPages > 1 && (
          <View style={styles.pageBar}>
            <Text style={styles.pageBarLabel}>Páginas Auditadas ({totalPages}):</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.pageList}>
              {Array.from({ length: totalPages }).map((_, idx) => (
                <TouchableOpacity
                  key={idx}
                  onPress={() => setCurrentPage(idx)}
                  accessibilityRole="button"
                  accessibilityLabel={`Visualizar página ${idx + 1}`}
                  style={[
                    styles.pageChip,
                    currentPage === idx && styles.pageChipActive,
                    // content-visibility:auto adia o render dos chips fora da
                    // tela na ScrollView horizontal (relevantes perto de 50
                    // páginas). Aplicado só no web; RN nativo ignora.
                    isWeb ? ({ contentVisibility: "auto", containIntrinsicSize: 44 } as any) : undefined,
                  ]}
                >
                  <Text style={[styles.pageChipText, currentPage === idx && styles.pageChipActiveText]}>
                    Página {idx + 1}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Viewport do Renderizador (IFrame no Web) */}
        <View style={styles.viewport}>
          {Platform.OS === "web" &&
            React.createElement(
              "a",
              {
                href: previewUrl,
                target: "_blank",
                rel: "noopener noreferrer",
                "aria-label": "Abrir a visualização em uma nova aba",
                style: {
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  alignSelf: "flex-start",
                  color: colors.accent.text,
                  textDecorationLine: "underline",
                  fontFamily: font.body,
                  fontSize: 13,
                },
              },
              "Abrir conteúdo em nova aba",
            )}
          {Platform.OS === "web" ? (
            React.createElement("iframe", {
              src: previewUrl,
              title: "Visualização do Site Corrigido",
              tabIndex: 0,
              style: {
                width: "100%",
                height: "100%",
                border: "none",
                backgroundColor: "#ffffff",
              },
            })
          ) : (
            <View style={styles.fallbackBox}>
              <Text style={styles.fallbackText}>
                Live Preview interativo disponível no navegador web em: {previewUrl}
              </Text>
            </View>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panelShell: {
    // Área lateral permanente da própria página: não é modal, não bloqueia a
    // conversa e não captura o foco. O estado só é encerrado quando uma nova
    // auditoria começa.
    position: "fixed",
    top: 0,
    right: 0,
    bottom: 0,
    width: "45%",
    minWidth: 420,
    maxWidth: 640,
    zIndex: 10000,
    backgroundColor: colors.bg.surface,
    borderLeftWidth: 1,
    borderColor: colors.border.DEFAULT,
    shadowColor: "#000",
    shadowOffset: { width: -6, height: 0 },
    shadowOpacity: 0.35,
    shadowRadius: 16,
    elevation: 10,
  },
  /* Mantido separado para o layout interno do painel. */
  overlay: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: "transparent",
    zIndex: 10000,
    alignItems: "flex-end",
  },
  container: {
    flex: 1,
    width: "100%",
    height: "100%",
    backgroundColor: colors.bg.surface,
    overflow: "hidden",
    elevation: 10,
  },
  containerMobile: {
    // Em telas estreitas o painel ocupa a viewport, mantendo-se parte da
    // página e não um diálogo sobreposto.
    width: "100%",
    minWidth: 0,
    maxWidth: "100%",
    borderLeftWidth: 0,
  },
  openExternalBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    alignSelf: "flex-start",
  },
  openExternalText: {
    color: colors.accent.text,
    textDecorationLine: "underline",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: colors.bg.elevated,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.DEFAULT,
  },
  headerTitleGroup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
  },
  title: {
    fontSize: 16,
    fontWeight: "700",
    color: colors.text.primary,
    fontFamily: font.display,
  },
  toggleGroup: {
    flexDirection: "row",
    backgroundColor: colors.bg.root,
    borderRadius: 8,
    padding: 2,
  },
  toggleBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 6,
    minHeight: a11y.minTarget,
    justifyContent: "center",
  },
  toggleActive: {
    backgroundColor: colors.accent.DEFAULT,
  },
  toggleActiveDanger: {
    backgroundColor: colors.danger.DEFAULT,
  },
  toggleText: {
    fontSize: 13,
    color: colors.text.secondary,
    fontFamily: font.body,
  },
  toggleActiveText: {
    color: colors.text.onAccent,
    fontWeight: "700",
  },
  closeBtn: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    backgroundColor: colors.bg.surface,
    borderRadius: 6,
    minHeight: a11y.minTarget,
    justifyContent: "center",
  },
  closeText: {
    fontSize: 13,
    color: colors.text.secondary,
    fontFamily: font.body,
  },
  pageBar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: colors.bg.root,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.DEFAULT,
    gap: 12,
  },
  pageBarLabel: {
    fontSize: 13,
    color: colors.text.secondary,
    fontFamily: font.body,
  },
  pageList: {
    gap: 8,
  },
  pageChip: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 6,
    backgroundColor: colors.bg.elevated,
    minHeight: a11y.minTarget,
    justifyContent: "center",
  },
  pageChipActive: {
    backgroundColor: colors.accent.muted,
  },
  pageChipText: {
    fontSize: 12,
    color: colors.text.secondary,
    fontFamily: font.body,
  },
  pageChipActiveText: {
    color: colors.accent.text,
    fontWeight: "700",
  },
  viewport: {
    flex: 1,
    backgroundColor: "#ffffff",
  },
  fallbackBox: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  fallbackText: {
    fontSize: 15,
    color: colors.text.secondary,
    textAlign: "center",
  },
});
