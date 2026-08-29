import React, { useEffect, useMemo, useState } from "react";
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator, Platform } from "react-native";

import { colors, font, a11y } from "../design/tokens";
import { useDialogFocus, FOCUSABLE_SELECTOR } from "../hooks/useDialogFocus";
import { deleteChatHistory, listConversations, type ConversationSummary } from "../services/chat";

interface Props {
  currentConversationId: string;
  onSelect: (conversationId: string) => void;
  onClose: () => void;
  /** Chamado quando a conversa que está aberta agora é uma das excluídas --
   * quem usa o modal decide o que fazer (ex.: `startNewConversation()`). */
  onCurrentConversationDeleted?: () => void;
}

const isWeb = Platform.OS === "web";

function formatRelativeTime(unixSeconds: number): string {
  const diffMs = Date.now() - unixSeconds * 1000;
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return "agora mesmo";
  if (diffMin < 60) return `há ${diffMin} min`;
  const diffHours = Math.round(diffMin / 60);
  if (diffHours < 24) return `há ${diffHours}h`;
  const diffDays = Math.round(diffHours / 24);
  return `há ${diffDays}d`;
}

/**
 * Checkbox acessível. React Native Web não dá tecla de espaço de graça a um
 * `role="checkbox"` customizado (só ganha isso de verdade num `<input>`
 * nativo) -- mesmo padrão manual já usado pelo grupo de rádio de provider em
 * SettingsScreen.tsx: `div` com `role`/`aria-checked`/`tabIndex` e
 * `onKeyDown` tratando Espaço e Enter explicitamente.
 */
function Checkbox({
  checked,
  onToggle,
  label,
}: {
  checked: boolean;
  onToggle: () => void;
  label: string;
}) {
  if (isWeb) {
    return React.createElement(
      "div",
      {
        role: "checkbox",
        "aria-checked": checked,
        "aria-label": label,
        tabIndex: 0,
        onClick: (e: React.MouseEvent) => {
          e.stopPropagation();
          onToggle();
        },
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === " " || e.key === "Spacebar" || e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            onToggle();
          }
        },
        style: {
          width: 22,
          height: 22,
          minWidth: 22,
          borderRadius: 5,
          border: `2px solid ${checked ? colors.accent.DEFAULT : colors.border.DEFAULT}`,
          backgroundColor: checked ? colors.accent.DEFAULT : "transparent",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          flexShrink: 0,
        },
      },
      checked
        ? React.createElement(
            "span",
            { style: { color: colors.text.onAccent, fontSize: 14, fontWeight: 700, lineHeight: 1 } },
            "✓",
          )
        : null,
    );
  }
  return (
    <TouchableOpacity
      onPress={onToggle}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={label}
      style={[styles.checkboxNative, checked && styles.checkboxNativeChecked]}
    >
      {checked && <Text style={styles.checkboxNativeMark}>✓</Text>}
    </TouchableOpacity>
  );
}

/**
 * Seletor de conversas anteriores (GET /chat/conversations,
 * chat_history_store.py no backend). Painel modal igual ao LivePreviewModal
 * -- mesmo padrão de diálogo (foco preso, Escape fecha, foco volta a quem
 * abriu) para consistência entre os dois painéis desta tela.
 *
 * Seleção múltipla: checkbox por conversa (Espaço/Enter com foco no
 * checkbox, ou clique/toque), "Selecionar tudo" alterna todas de uma vez, e
 * "Excluir selecionadas" apaga em lote (chat_history_store.clear_history por
 * id, uma chamada por conversa -- não existe endpoint de exclusão em massa
 * no backend, então o loop acontece aqui).
 */
export function ConversationHistoryModal({
  currentConversationId,
  onSelect,
  onClose,
  onCurrentConversationDeleted,
}: Props) {
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const containerRef = React.useRef<HTMLElement | null>(null);

  useDialogFocus({
    active: true,
    containerRef,
    onDismiss: onClose,
    getInitialFocus: (container) => container.querySelector<HTMLElement>(FOCUSABLE_SELECTOR),
  });

  const loadConversations = React.useCallback((cancelledRef?: { current: boolean }) => {
    return listConversations().then((list) => {
      if (cancelledRef?.current) return;
      setConversations(list);
      setSelectedIds((prev) => {
        const stillPresent = new Set(list.map((c) => c.conversation_id));
        return new Set(Array.from(prev).filter((id) => stillPresent.has(id)));
      });
    });
  }, []);

  useEffect(() => {
    const cancelledRef = { current: false };
    loadConversations(cancelledRef);
    return () => {
      cancelledRef.current = true;
    };
  }, [loadConversations]);

  const allSelected = useMemo(
    () => !!conversations && conversations.length > 0 && selectedIds.size === conversations.length,
    [conversations, selectedIds],
  );

  const toggleOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (!conversations) return;
    setSelectedIds(allSelected ? new Set() : new Set(conversations.map((c) => c.conversation_id)));
  };

  const deleteSelected = async () => {
    if (selectedIds.size === 0 || deleting) return;
    setDeleting(true);
    const ids = Array.from(selectedIds);
    try {
      await Promise.all(ids.map((id) => deleteChatHistory(id)));
      if (ids.includes(currentConversationId)) onCurrentConversationDeleted?.();
      setSelectedIds(new Set());
      await loadConversations();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <View style={styles.overlay} aria-modal={true} role="dialog" aria-labelledby="history-title">
      <View ref={containerRef as any} style={styles.container}>
        <View style={styles.header}>
          <Text id="history-title" style={styles.title}>
            Conversas anteriores
          </Text>
          <TouchableOpacity
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel="Fechar seletor de conversas"
            style={styles.closeBtn}
          >
            <Text style={styles.closeText}>Fechar</Text>
          </TouchableOpacity>
        </View>

        {!!conversations?.length && (
          <View style={styles.toolbar}>
            <TouchableOpacity
              onPress={toggleAll}
              accessibilityRole="button"
              accessibilityLabel={allSelected ? "Desmarcar todas as conversas" : "Selecionar todas as conversas"}
              style={styles.toolbarBtn}
            >
              <Text style={styles.toolbarBtnText}>{allSelected ? "Desmarcar tudo" : "Selecionar tudo"}</Text>
            </TouchableOpacity>

            {selectedIds.size > 0 && (
              <TouchableOpacity
                onPress={deleteSelected}
                disabled={deleting}
                accessibilityRole="button"
                accessibilityLabel={`Excluir ${selectedIds.size} conversa${selectedIds.size === 1 ? "" : "s"} selecionada${selectedIds.size === 1 ? "" : "s"}`}
                accessibilityState={{ disabled: deleting }}
                style={[styles.deleteBtn, deleting && styles.toolbarBtnDisabled]}
              >
                <Text style={styles.deleteBtnText}>
                  {deleting ? "Excluindo…" : `Excluir selecionadas (${selectedIds.size})`}
                </Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        <ScrollView style={styles.list} contentContainerStyle={styles.listContent}>
          {conversations === null && (
            <View style={styles.centerBox}>
              <ActivityIndicator />
              <Text style={styles.emptyText}>Carregando conversas…</Text>
            </View>
          )}

          {conversations !== null && conversations.length === 0 && (
            <View style={styles.centerBox}>
              <Text style={styles.emptyText}>Nenhuma conversa anterior ainda.</Text>
            </View>
          )}

          {conversations?.map((c) => {
            const isCurrent = c.conversation_id === currentConversationId;
            const isSelected = selectedIds.has(c.conversation_id);
            const label = `${c.title || "(sem título)"}, ${c.message_count} mensagens, ${formatRelativeTime(c.last_updated)}`;
            return (
              <View key={c.conversation_id} style={[styles.row, isSelected && styles.rowSelected]}>
                <Checkbox
                  checked={isSelected}
                  onToggle={() => toggleOne(c.conversation_id)}
                  label={`Selecionar conversa: ${label}`}
                />
                <TouchableOpacity
                  onPress={() => {
                    onSelect(c.conversation_id);
                    onClose();
                  }}
                  accessibilityRole="button"
                  accessibilityLabel={`${isCurrent ? "Conversa atual: " : "Abrir conversa: "}${label}`}
                  accessibilityState={{ selected: isCurrent }}
                  style={[styles.item, isCurrent && styles.itemActive]}
                >
                  <Text style={styles.itemTitle} numberOfLines={1}>
                    {c.title || "(sem título)"}
                  </Text>
                  <Text style={styles.itemMeta}>
                    {c.message_count} mensagem{c.message_count === 1 ? "" : "s"} · {formatRelativeTime(c.last_updated)}
                    {isCurrent ? " · conversa atual" : ""}
                  </Text>
                </TouchableOpacity>
              </View>
            );
          })}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: "rgba(0,0,0,0.35)",
    zIndex: 10000,
    alignItems: "center",
    justifyContent: "center",
  },
  container: {
    width: "90%",
    maxWidth: 480,
    maxHeight: "80%",
    backgroundColor: colors.bg.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border.DEFAULT,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 24,
    elevation: 10,
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
  title: {
    fontSize: 16,
    fontWeight: "700",
    color: colors.text.primary,
    fontFamily: font.display,
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
  toolbar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.DEFAULT,
    gap: 8,
  },
  toolbarBtn: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    minHeight: a11y.minTarget,
    justifyContent: "center",
  },
  toolbarBtnDisabled: {
    opacity: 0.5,
  },
  toolbarBtnText: {
    fontSize: 13,
    color: colors.accent.text,
    fontFamily: font.body,
    fontWeight: "600",
  },
  deleteBtn: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    minHeight: a11y.minTarget,
    justifyContent: "center",
    borderRadius: 6,
    backgroundColor: colors.danger.DEFAULT,
  },
  deleteBtnText: {
    fontSize: 13,
    color: colors.text.onAccent,
    fontFamily: font.body,
    fontWeight: "700",
  },
  list: {
    maxHeight: 420,
  },
  listContent: {
    padding: 8,
  },
  centerBox: {
    padding: 24,
    alignItems: "center",
    gap: 8,
  },
  emptyText: {
    fontSize: 14,
    color: colors.text.secondary,
    fontFamily: font.body,
    textAlign: "center",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 4,
    borderRadius: 8,
  },
  rowSelected: {
    backgroundColor: colors.bg.elevated,
  },
  checkboxNative: {
    width: 22,
    height: 22,
    borderRadius: 5,
    borderWidth: 2,
    borderColor: colors.border.DEFAULT,
    alignItems: "center",
    justifyContent: "center",
    minWidth: 22,
  },
  checkboxNativeChecked: {
    backgroundColor: colors.accent.DEFAULT,
    borderColor: colors.accent.DEFAULT,
  },
  checkboxNativeMark: {
    color: colors.text.onAccent,
    fontSize: 14,
    fontWeight: "700",
  },
  item: {
    flex: 1,
    paddingVertical: 10,
    paddingHorizontal: 8,
    borderRadius: 8,
    minHeight: a11y.minTarget,
    justifyContent: "center",
  },
  itemActive: {
    backgroundColor: colors.accent.muted,
  },
  itemTitle: {
    fontSize: 14,
    color: colors.text.primary,
    fontFamily: font.body,
    fontWeight: "600",
  },
  itemMeta: {
    fontSize: 12,
    color: colors.text.secondary,
    fontFamily: font.body,
    marginTop: 2,
  },
});
