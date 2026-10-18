import React, { useEffect, useState } from "react";
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from "react-native";

import {
  a11y,
  applyThemePreference,
  colors,
  font,
  radius,
  readThemePreference,
  type ThemePreference,
} from "../design/tokens";
import { listConversations, type ConversationSummary } from "../services/chat";

const THEME_ORDER: readonly ThemePreference[] = ["system", "light", "dark"];
const THEME_NAME: Record<ThemePreference, string> = {
  system: "automático (segue o sistema)",
  light: "claro",
  dark: "escuro",
};

/**
 * Alterna o tema entre automático, claro e escuro. O rótulo diz o estado atual
 * e o que acontece ao ativar, para quem usa leitor de tela.
 */
export function ThemeToggle({ variant = "sidebar" }: { variant?: "sidebar" | "header" }) {
  const [preference, setPreference] = useState<ThemePreference>(readThemePreference);
  const next = THEME_ORDER[(THEME_ORDER.indexOf(preference) + 1) % THEME_ORDER.length];
  return (
    <TouchableOpacity
      onPress={() => {
        applyThemePreference(next);
        setPreference(next);
      }}
      accessibilityRole="button"
      accessibilityLabel={`Tema ${THEME_NAME[preference]}. Ativar para mudar para ${THEME_NAME[next]}`}
      style={variant === "header" ? styles.headerAction : styles.action}
    >
      <Text style={variant === "header" ? styles.headerActionText : styles.actionText}>Tema: {THEME_NAME[preference].split(" ")[0]}</Text>
    </TouchableOpacity>
  );
}

interface Props {
  currentConversationId: string;
  /** Recarrega a lista quando um turno termina (a conversa atual ganha título/ordem). */
  streaming: boolean;
  onSelect: (conversationId: string) => void;
  onNew: () => void;
  onManage: () => void;
  onOpenSettings?: () => void;
}

/**
 * Barra lateral fixa de conversas. Reaproveita `listConversations`; a seleção
 * múltipla e a exclusão continuam no ConversationHistoryModal ("Gerenciar").
 */
export function ConversationSidebar({
  currentConversationId,
  streaming,
  onSelect,
  onNew,
  onManage,
  onOpenSettings,
}: Props) {
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);

  useEffect(() => {
    if (streaming) return;
    let cancelled = false;
    void listConversations().then((list) => {
      if (!cancelled) setConversations(list);
    });
    return () => {
      cancelled = true;
    };
  }, [streaming, currentConversationId]);

  return (
    <View role="navigation" aria-label="Conversas" style={styles.root}>
      <TouchableOpacity
        onPress={onNew}
        disabled={streaming}
        accessibilityRole="button"
        accessibilityState={{ disabled: streaming }}
        accessibilityLabel="Iniciar uma nova conversa"
        style={[styles.newBtn, streaming && styles.disabled]}
      >
        <Text style={styles.newBtnText}>Nova conversa</Text>
      </TouchableOpacity>

      <Text accessibilityRole="header" aria-level={2} style={styles.sectionTitle}>
        Recentes
      </Text>

      <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
        {conversations === null && <Text style={styles.meta}>Carregando conversas…</Text>}
        {conversations?.length === 0 && <Text style={styles.meta}>Nenhuma conversa anterior ainda.</Text>}
        {conversations?.map((c) => {
          const isCurrent = c.conversation_id === currentConversationId;
          const title = c.title || "(sem título)";
          return (
            <TouchableOpacity
              key={c.conversation_id}
              onPress={() => onSelect(c.conversation_id)}
              disabled={streaming && !isCurrent}
              accessibilityRole="button"
              accessibilityState={{ disabled: streaming && !isCurrent }}
              accessibilityLabel={`${isCurrent ? "Conversa atual: " : "Abrir conversa: "}${title}, ${c.message_count} mensagens`}
              {...({ "aria-current": isCurrent ? "true" : undefined } as object)}
              style={[styles.item, isCurrent && styles.itemActive]}
            >
              <Text style={[styles.itemTitle, isCurrent && styles.itemTitleActive]} numberOfLines={1}>
                {title}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          onPress={onManage}
          accessibilityRole="button"
          accessibilityLabel="Gerenciar conversas: selecionar e excluir"
          style={styles.action}
        >
          <Text style={styles.actionText}>Gerenciar conversas</Text>
        </TouchableOpacity>
        <ThemeToggle />
        {onOpenSettings && (
          <TouchableOpacity
            onPress={onOpenSettings}
            accessibilityRole="button"
            accessibilityLabel="Abrir configurações de IA"
            style={styles.action}
          >
            <Text style={styles.actionText}>Configurações</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    width: 280,
    backgroundColor: colors.bg.subtle,
    borderRightWidth: 1,
    borderRightColor: colors.border.DEFAULT,
    padding: 12,
    gap: 8,
  },
  newBtn: {
    minHeight: a11y.minTarget,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: colors.accent.DEFAULT,
    borderRadius: radius.md,
    paddingHorizontal: 12,
  },
  newBtnText: { color: colors.text.onAccent, fontFamily: font.display, fontSize: 14, fontWeight: "700" },
  disabled: { opacity: 0.6 },
  sectionTitle: {
    color: colors.text.secondary,
    fontFamily: font.body,
    fontSize: 12,
    fontWeight: "600",
    marginTop: 8,
    paddingHorizontal: 8,
  },
  list: { flex: 1 },
  listContent: { gap: 2 },
  meta: { color: colors.text.secondary, fontFamily: font.body, fontSize: 13, padding: 8 },
  item: {
    minHeight: a11y.minTarget,
    justifyContent: "center",
    paddingHorizontal: 10,
    borderRadius: radius.md,
  },
  itemActive: { backgroundColor: colors.accent.muted },
  itemTitle: { color: colors.text.primary, fontFamily: font.body, fontSize: 14 },
  itemTitleActive: { fontWeight: "600" },
  footer: { gap: 2, borderTopWidth: 1, borderTopColor: colors.border.DEFAULT, paddingTop: 8 },
  action: {
    minHeight: a11y.minTarget,
    justifyContent: "center",
    paddingHorizontal: 10,
    borderRadius: radius.md,
  },
  actionText: { color: colors.text.secondary, fontFamily: font.body, fontSize: 14 },
  // Mesmo visual dos botões do cabeçalho do ChatScreen quando a barra lateral não cabe.
  headerAction: {
    minHeight: a11y.minTarget,
    justifyContent: "center",
    paddingVertical: 8,
    paddingHorizontal: 12,
    backgroundColor: colors.border.strong,
    borderRadius: 6,
  },
  headerActionText: { color: colors.accent.text, fontFamily: font.body, fontSize: 14 },
});
