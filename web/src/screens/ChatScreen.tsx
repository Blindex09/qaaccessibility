import React, { useEffect, useRef, useState } from "react";
import {
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";

import { useChat } from "../hooks/useChat";
import { useDialogFocus } from "../hooks/useDialogFocus";
import { BASE_URL } from "../services/chat";
import { toolStatusText, type ToolCallData } from "../services/toolPresentation";
import { type TokenUsage } from "../services/usage";
import { a11y, colors, font } from "../design/tokens";
import { ClarifyPanel } from "./ClarifyPanel";
import { ConversationHistoryModal } from "./ConversationHistoryModal";
import { LivePreviewModal } from "./LivePreviewModal";


/**
 * Chat agentico de acessibilidade com streaming token-a-token.
 * O agente conversa, processa quando necessário, chama a tool de análise e
 * narra tudo em tempo real (eventos SSE de /chat/stream).
 */
interface Attachment {
  name: string;
  content: string;
}

function ToolCallCard({ toolCall, messageIndex }: { toolCall: ToolCallData; messageIndex?: number }) {
  const isRunning = toolCall.status === "running";
  const isError = toolCall.status === "failed";
  const statusLabel = toolStatusText(toolCall);
  const statusColor = isError ? "#f87171" : isRunning ? "#fbbf24" : "#34d399";

  return (
    <View
      style={styles.toolRegion}
      aria-busy={isRunning}
      {...(Platform.OS === "web"
        ? { dataSet: { messageIndex: String(messageIndex) }, tabIndex: 0, "aria-label": `Status da ferramenta: ${statusLabel}` }
        : {})}
    >
      <View style={styles.toolHeader}>
        <Text style={{ fontSize: 13, fontWeight: "600", color: statusColor, fontFamily: font.body }}>
          {statusLabel}
        </Text>
      </View>

      {isRunning && (
        <View
          style={styles.toolLogContainer}
          {...(Platform.OS === "web"
            ? { dataSet: { toolLog: "active" }, tabIndex: 0, "aria-label": `Andamento da ferramenta ${toolCall.name}` }
            : {})}
        >
          {toolCall.logs?.length ? toolCall.logs.map((line, idx) => (
            <Text key={idx} style={styles.toolLogText}>{line}</Text>
          )) : (
            <Text style={styles.toolLogMuted}>Aguardando andamento da ferramenta...</Text>
          )}
        </View>
      )}

      {toolCall.error && (
        <Text style={styles.toolError}>{toolCall.error}</Text>
      )}
    </View>
  );
}

/**
 * Fontes reais consultadas por ferramentas de pesquisa (deep_research,
 * tavily_search, exa_search) no turno corrente -- links clicáveis, cada um
 * abrindo em nova aba (pesquisa externa: nunca navega a própria conversa
 * pra fora).
 */
function SourcesSection({ sources }: { sources: { title: string; url: string }[] }) {
  if (!sources.length) return null;

  return (
    <View style={[styles.statusGroupContainer, { marginTop: 8 }]} accessibilityRole={Platform.OS === "web" ? undefined : "list"}>
      <View style={styles.statusGroupHeader}>
        <Text style={styles.statusGroupHeaderText}>Fontes consultadas ({sources.length})</Text>
      </View>
      <View style={styles.statusGroupContent}>
        {sources.map((source, idx) => (
          <View key={source.url + idx} style={styles.statusLine}>
            <Text
              accessibilityRole="link"
              onPress={() => Linking.openURL(source.url)}
              style={[styles.statusLineText, { color: colors.accent.text, textDecorationLine: "underline" }]}
              aria-label={`${source.title} (abre em uma nova janela)`}
            >
              {source.title}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/**
 * Atualizações da squad em um feed consultável. Os itens têm foco próprio e
 * as setas percorrem o feed; não há aria-live, portanto nada é falado sem que
 * a pessoa escolha consultar o andamento.
 */
function ActivityFeed({
  label,
  messages,
}: {
  label: string;
  messages: { content: string; groupKey?: string }[];
}) {
  if (!messages.length) return null;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const current = event.currentTarget;
    const feed = current.parentElement;
    const items = feed
      ? Array.from(
          feed.querySelectorAll<HTMLElement>("[data-execution-status='true'], [data-squad-status='true']"),
        )
      : [];
    const index = items.indexOf(current);
    const nextIndex = event.key === "ArrowDown" ? index + 1 : index - 1;
    if (nextIndex >= 0 && nextIndex < items.length) {
      event.preventDefault();
      event.stopPropagation();
      items[nextIndex].focus();
    }
  };

  return (
    <View
      style={styles.squadFeed}
      accessibilityRole={Platform.OS === "web" ? undefined : "list"}
      {...(Platform.OS === "web"
          ? { "aria-label": `${label}. Use as setas para navegar entre as atualizações.` }
        : {})}
    >
      <Text style={styles.squadFeedTitle}>{label}</Text>
      {messages.map((message, index) =>
        Platform.OS === "web" ? (
          React.createElement(
            "div",
            {
              key: message.groupKey || `${message.content}-${index}`,
              role: "listitem",
              tabIndex: 0,
              "data-execution-status": "true",
              // Compatibilidade com o contrato de automação existente da
              // squad; o feed agora também serve para os especialistas.
              "data-squad-status": "true",
              "aria-label": message.content,
              onKeyDown: handleKeyDown,
              style: {
                color: colors.text.tertiary,
                fontFamily: font.body,
                fontSize: 13,
                lineHeight: "19px",
                padding: "3px 4px",
                outlineOffset: 2,
              },
            },
            message.content,
          )
        ) : (
          <View key={message.groupKey || `${message.content}-${index}`}>
            <Text style={styles.statusLineText}>{message.content}</Text>
          </View>
        ),
      )}
    </View>
  );
}

/**
 * Indicador discreto de consumo de tokens. Segue a convenção minimalista do
 * chat: é metadado de rodapé, não um painel de analytics. Não mostra valor em
 * dinheiro — o preço por modelo não chega ao frontend, e inventar um número
 * seria pior do que não mostrar nenhum.
 */
function UsageNote({ usage, scope }: { usage: TokenUsage; scope: "turn" | "session" }) {
  return null;
}

function processInlineLinks(lineText: string, itemKey: string | number) {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  // Marcadores de wiring são consumidos e nunca aparecem como texto ou botão.
  const markerRegex = /\[LIVE_PREVIEW:([a-zA-Z0-9_-]+):(\d+)\]|\[CLOSE_PREVIEW\]/g;
  const linkRegex = /(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))|(https?:\/\/[^\s)\u00a0]+)/g;

  let match;
  while ((match = markerRegex.exec(lineText)) !== null) {
    if (match.index > lastIndex) {
      parts.push(...processInlineLinks(lineText.substring(lastIndex, match.index), `${itemKey}-pre`));
    }
    lastIndex = markerRegex.lastIndex;
  }

  if (lastIndex > 0) {
    if (lastIndex < lineText.length) {
      parts.push(...processInlineLinks(lineText.substring(lastIndex), `${itemKey}-post`));
    }
    return parts.length > 0 ? parts : lineText;
  }

  while ((match = linkRegex.exec(lineText)) !== null) {
    if (match.index > lastIndex) {
      parts.push(lineText.substring(lastIndex, match.index));
    }
    if (match.index > lastIndex) {
      parts.push(lineText.substring(lastIndex, match.index));
    }

    if (match[1]) {
      const label = match[2];
      let url = match[3];
      if (url.includes("localhost:8001")) {
        url = url.replace("http://localhost:8001", BASE_URL);
      }
      if (Platform.OS === "web") {
        parts.push(
          React.createElement(
            "a",
            {
              key: `${itemKey}-link-${match.index}`,
              href: url,
              target: "_blank",
              rel: "noreferrer",
              style: {
                color: colors.accent.text,
                textDecoration: "underline",
                fontWeight: "bold",
                fontFamily: font.body,
                fontSize: 15,
              },
            },
            label
          )
        );
      } else {
        parts.push(
          <Text
            key={`${itemKey}-link-${match.index}`}
            style={{
              color: colors.accent.text,
              textDecorationLine: "underline",
              fontWeight: "bold",
            }}
            onPress={() => Linking.openURL(url).catch(() => {})}
          >
            {label}
          </Text>
        );
      }
    } else {
      let url = match[4];
      if (url.includes("localhost:8001")) {
        url = url.replace("http://localhost:8001", BASE_URL);
      }
      if (Platform.OS === "web") {
        parts.push(
          React.createElement(
            "a",
            {
              key: `${itemKey}-link-${match.index}`,
              href: url,
              target: "_blank",
              rel: "noreferrer",
              style: {
                color: colors.accent.text,
                textDecoration: "underline",
                fontWeight: "bold",
                fontFamily: font.body,
                fontSize: 15,
              },
            },
            url
          )
        );
      } else {
        parts.push(
          <Text
            key={`${itemKey}-link-${match.index}`}
            style={{
              color: colors.accent.text,
              textDecorationLine: "underline",
              fontWeight: "bold",
            }}
            onPress={() => Linking.openURL(url).catch(() => {})}
          >
            {url}
          </Text>
        );
      }
    }

    lastIndex = linkRegex.lastIndex;
  }

  if (lastIndex < lineText.length) {
    parts.push(lineText.substring(lastIndex));
  }

  return parts.length > 0 ? parts : lineText;
}

function cleanAssistantMarkup(text: string): string {
  return text
    .replace(/```[\w-]*\s*\n?/g, "")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*(?:[-*_]\s*){3,}$/gm, "")
    .replace(/[*_~`]/g, "")
    .replace(/(^|\s)>(?=\s)/gm, "$1")
    .trim();
}

function renderTextWithLinks(text: string) {
  if (!text) return null;

  const rawLines = cleanAssistantMarkup(text).split("\n");
  const blocks: React.ReactNode[] = [];
  let currentListItems: React.ReactNode[] = [];
  let isOrderedList = false;

  const flushList = (keyPrefix: string) => {
    if (currentListItems.length > 0) {
      if (Platform.OS === "web") {
        const Tag = isOrderedList ? "ol" : "ul";
        blocks.push(
          React.createElement(
            Tag,
            {
              key: `${keyPrefix}-list`,
              style: {
                marginTop: 4,
                marginBottom: 6,
                paddingLeft: 24,
                color: colors.text.primary,
                fontFamily: font.body,
                fontSize: 15,
                lineHeight: "22px",
              },
            },
            currentListItems
          )
        );
      } else {
        blocks.push(
          <View key={`${keyPrefix}-list`} accessibilityRole="list" style={{ marginTop: 4, marginBottom: 6, paddingLeft: 8 }}>
            {currentListItems}
          </View>
        );
      }
      currentListItems = [];
    }
  };

  rawLines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) return; // Elimina linhas em branco vazias repetidas

    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    const bulletMatch = trimmed.match(/^[-*•]\s+(.*)$/);

    if (numMatch) {
      if (currentListItems.length > 0 && !isOrderedList) {
        flushList(`line-${idx}`);
      }
      isOrderedList = true;
      const content = numMatch[2];
      if (Platform.OS === "web") {
        currentListItems.push(
          React.createElement(
            "li",
            { key: `li-${idx}`, style: { marginBottom: 4 } },
            processInlineLinks(content, `li-${idx}`)
          )
        );
      } else {
        currentListItems.push(
          <View key={`li-${idx}`} accessibilityRole={"listitem" as any} style={{ flexDirection: "row", marginBottom: 4 }}>
            <Text style={[styles.bubbleText, { fontWeight: "bold", marginRight: 6 }]}>{numMatch[1]}.</Text>
          <Text style={styles.bubbleText}>{processInlineLinks(content, `li-${idx}`)}</Text>
          </View>
        );
      }
    } else if (bulletMatch) {
      if (currentListItems.length > 0 && isOrderedList) {
        flushList(`line-${idx}`);
      }
      isOrderedList = false;
      const content = bulletMatch[1];
      if (Platform.OS === "web") {
        currentListItems.push(
          React.createElement(
            "li",
            { key: `li-${idx}`, style: { marginBottom: 4 } },
            processInlineLinks(content, `li-${idx}`)
          )
        );
      } else {
        currentListItems.push(
          <View key={`li-${idx}`} accessibilityRole={"listitem" as any} style={{ flexDirection: "row", marginBottom: 4 }}>
            <Text style={[styles.bubbleText, { marginRight: 6 }]}>•</Text>
          <Text style={styles.bubbleText}>{processInlineLinks(content, `li-${idx}`)}</Text>
          </View>
        );
      }
    } else {
      flushList(`line-${idx}`);
      const isHeading = trimmed.endsWith(":") || (trimmed.startsWith("**") && trimmed.endsWith("**"));
      const cleanText = trimmed.replace(/^\*\*(.*)\*\*$/, "$1");

      if (Platform.OS === "web") {
        blocks.push(
          React.createElement(
            "p",
            {
              key: `p-${idx}`,
              style: {
                marginTop: idx === 0 ? 0 : 4,
                marginBottom: 4,
                color: colors.text.primary,
                fontFamily: font.body,
                fontSize: 15,
                lineHeight: "22px",
                fontWeight: isHeading ? "bold" : "normal",
              },
            },
            processInlineLinks(cleanText, `p-${idx}`)
          )
        );
      } else {
        blocks.push(
          <Text
            key={`p-${idx}`}
            style={[
              styles.bubbleText,
              isHeading && { fontWeight: "bold" },
              { marginTop: idx === 0 ? 0 : 4, marginBottom: 4 },
            ]}
          >
            {processInlineLinks(cleanText, `p-${idx}`)}
          </Text>
        );
      }
    }
  });

  flushList("final");

  return <React.Fragment>{blocks}</React.Fragment>;
}

// Texto VISÍVEL do campo de mensagem. O nome acessível é derivado dele para
// satisfazer o WCAG 2.5.3 (Label in Name): o nome precisa CONTER o visível.
const PLACEHOLDER_MENSAGEM = "Pergunte, cole uma URL, ou anexe arquivos…";
const ROTULO_ACESSIVEL_MENSAGEM = `${PLACEHOLDER_MENSAGEM} — mensagem para o assistente`;


export function ChatScreen({ onOpenSettings }: { onOpenSettings?: () => void }) {
  const {
    messages,
    streaming,
    activity,
    auditRunCount,
    announcement,
    elapsedMs,
    durationMs,
    turnSources,
    pendingClarify,
    sessionUsage,
    send,
    answerClarify,
    stop,
    steer,
    conversationId,
    startNewConversation,
    switchConversation,
  } = useChat();
  const [historyModalVisible, setHistoryModalVisible] = useState(false);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [attachmentsExpanded, setAttachmentsExpanded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const chatInputRef = useRef<any>(null);

  // Estado do Modal Acessivel de Chaves de Servico
  const [keyModalVisible, setKeyModalVisible] = useState(false);
  const [keyModalService, setKeyModalService] = useState("");
  const [keyModalValue, setKeyModalValue] = useState("");
  const [keyModalSaving, setKeyModalSaving] = useState(false);
  const [keyModalError, setKeyModalError] = useState<string | null>(null);
  const keyInputRef = useRef<any>(null);
  const keyModalContainerRef = useRef<HTMLElement | null>(null);

  // Estado do Live Preview Modal (estilo Replit)
  const [previewModalVisible, setPreviewModalVisible] = useState(false);
  const [previewSessionId, setPreviewSessionId] = useState("");
  const [previewTotalPages, setPreviewTotalPages] = useState(1);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [messages, activity, pendingClarify]);

  // Navegação acessível direta por teclado: Setas (↑ / ↓) navegam diretamente
  // entre as mensagens da conversa sem necessidade de segurar Alt.
  const focusedMessageIndexRef = useRef(-1);
  useEffect(() => {
    if (Platform.OS !== "web") return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.altKey && event.key.toLowerCase() === "i") {
        event.preventDefault();
        chatInputRef.current?.focus();
        return;
      }
      if (event.altKey && event.key.toLowerCase() === "l") {
        event.preventDefault();
        document.querySelector<HTMLElement>("[data-tool-log=\"active\"]")?.focus();
        return;
      }
      if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;

      const activeTag = document.activeElement?.tagName?.toLowerCase() || "";
      const isInputActive = activeTag === "textarea" || activeTag === "input";
      const isInputEmpty = isInputActive && !(document.activeElement as HTMLInputElement | HTMLTextAreaElement)?.value?.trim();

      // Se estiver digitando texto não-vazio no campo, preserva as setas para movimentação do cursor
      if (isInputActive && !isInputEmpty && !event.altKey) {
        return;
      }

      const allMessageElements = Array.from(document.querySelectorAll<HTMLElement>("[data-message-index]"));
      if (!allMessageElements.length) return;

      event.preventDefault();

      if (event.key === "ArrowUp") {
        if (focusedMessageIndexRef.current === -1) {
          focusedMessageIndexRef.current = allMessageElements.length - 1;
        } else {
          focusedMessageIndexRef.current = Math.max(0, focusedMessageIndexRef.current - 1);
        }
      } else {
        if (focusedMessageIndexRef.current === -1) {
          focusedMessageIndexRef.current = 0;
        } else {
          focusedMessageIndexRef.current = Math.min(allMessageElements.length - 1, focusedMessageIndexRef.current + 1);
        }
      }

      const targetEl = allMessageElements[focusedMessageIndexRef.current];
      if (targetEl) {
        targetEl.focus();
        targetEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [messages]);

  // Uma nova auditoria começa uma sessão limpa, sem misturar previews de páginas.
  //
  // O gatilho é o fato de o backend ter DISPARADO uma ferramenta de análise
  // (`auditRunCount`, alimentado pelo evento `tool_start`), nunca uma leitura da
  // frase do usuário. A versão anterior testava palavras-chave em português e
  // errava dos dois lados: não reconhecia "roda o axe nesse site" nem um pedido
  // em inglês, e fechava o painel num acompanhamento sobre a MESMA auditoria
  // ("verifique se o botão ficou certo").
  useEffect(() => {
    if (auditRunCount === 0) return;
    setPreviewModalVisible(false);
    setPreviewSessionId("");
    setPreviewTotalPages(1);
  }, [auditRunCount]);

  // Registra a sessão criada pela IA e abre automaticamente o painel após uma
  // correção concluída. O painel permanece aberto enquanto a sessão avança.
  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg && lastMsg.role === "assistant") {
      if (lastMsg.content.includes("[CLOSE_PREVIEW]")) {
        setPreviewModalVisible(false);
      } else if (lastMsg.content.includes("[LIVE_PREVIEW:")) {
        const match = lastMsg.content.match(/\[LIVE_PREVIEW:([a-zA-Z0-9_-]+):?(\d+)?\]/);
        if (match && match[1]) {
          setPreviewSessionId(match[1]);
          setPreviewTotalPages(match[2] ? parseInt(match[2], 10) : 1);
          setPreviewModalVisible(true);
        }
      }
    }
  }, [messages]);



  // Diálogo da chave de API: Tab preso, Escape fecha, foco devolvido a quem
  // estava a editar. Mesma implementação partilhada do LivePreviewModal e do
  // pedido de aprovação do ClarifyPanel.
  useDialogFocus({
    active: keyModalVisible,
    containerRef: keyModalContainerRef,
    onDismiss: () => setKeyModalVisible(false),
    getInitialFocus: () => keyInputRef.current,
  });

  // Monitora se a IA ou o sistema solicitaram alguma chave de servico (ex.: [PRECISE_KEY:postman])
  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg && lastMsg.role === "assistant" && lastMsg.content.includes("[PRECISE_KEY:")) {
      const match = lastMsg.content.match(/\[PRECISE_KEY:([a-zA-Z0-9_-]+)\]/);
      if (match && match[1]) {
        setKeyModalService(match[1]);
        setKeyModalValue("");
        setKeyModalError(null);
        setKeyModalVisible(true);
      }
    }
  }, [messages]);

  async function handleSaveKey() {
    if (!keyModalValue.trim() || !keyModalService) return;
    setKeyModalSaving(true);
    setKeyModalError(null);
    try {
      const { saveServiceKey } = await import("../services/api");
      await saveServiceKey(keyModalService, keyModalValue.trim());
      setKeyModalVisible(false);
      // Notifica a IA que a chave foi inserida e retoma a conversa
      void send(`Chave para o serviço '${keyModalService}' configurada com sucesso. Pode prosseguir com o teste.`);
    } catch (err) {
      console.error("[KeyModal] Erro ao salvar chave:", err);
      // Anúncio acessível: a mensagem entra numa live region assertiva
      // (role=alert) e é lida imediatamente pelo leitor de tela, em vez de
      // ficar só no console. Inclui o próximo passo sugerido.
      const reason =
        err instanceof Error && err.message ? err.message : "Verifique a chave e a ligação ao backend.";
      setKeyModalError(`Não foi possível guardar a chave. ${reason} Pode tentar novamente ou cancelar.`);
    } finally {
      setKeyModalSaving(false);
    }
  }


  function onPickFiles(e: { target: { files: FileList | null } }) {
    const files = e.target.files;
    if (!files) return;
    const readers = Array.from(files).map(
      (file) =>
        new Promise<Attachment>((resolve) => {
          const reader = new FileReader();
          const isZip = file.name.toLowerCase().endsWith(".zip");
          const isDocx = file.name.toLowerCase().endsWith(".docx");
          const isPdf = file.name.toLowerCase().endsWith(".pdf");
          const isPptx = file.name.toLowerCase().endsWith(".pptx");
          const isBinary = isZip || isDocx || isPdf || isPptx;

          reader.onload = () => {
            let content = String(reader.result ?? "");
            if (isBinary) {
              const parts = content.split(",");
              content = parts[1] || parts[0];
            }
            resolve({ name: file.name, content });
          };
          reader.onerror = () => resolve({ name: file.name, content: "" });
          if (isBinary) {
            reader.readAsDataURL(file);
          } else {
            reader.readAsText(file);
          }
        }),
    );
    Promise.all(readers).then((loaded) =>
      setAttachments((prev) => [...prev, ...loaded.filter((a) => a.content)]),
    );
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeAttachment(name: string) {
    setAttachments((prev) => prev.filter((a) => a.name !== name));
  }

  // Condição única de "não dá para enviar": usada no estado acessível, no
  // rótulo e no estilo. Antes era a mesma expressão repetida três vezes.
  const naoPodeEnviar = !streaming && !input.trim() && attachments.length === 0;

  function handleSend() {
    const text = input.trim();
    if ((!text && attachments.length === 0) || streaming) return;

    // Os anexos viajam como DADO estruturado; quem serializa o prompt e o
    // backend (`_compor_mensagem_com_anexos`). Antes esta tela montava o blob
    // de texto e o backend reconhecia o anexo por substring ("===" na
    // mensagem), o que dava falso positivo em qualquer texto colado com
    // separador markdown, diff ou tabela ASCII -- e pulava a triagem em silencio.
    const anexosDoTurno = attachments.map((a) => ({ name: a.name, content: a.content }));
    const message =
      text || (anexosDoTurno.length > 0 ? "Analise a acessibilidade dos arquivos anexados." : text);
    const displayText = message;

    setInput("");
    setAttachments([]);
    // Sem override de provider/modelo: o chat usa a configuração salva em
    // /settings (provider + chave + modelo "Alto"). Config única, sem duplicação.
    void send(message, displayText, anexosDoTurno);
  }

  // Ação do botão principal e do Enter enquanto o turno está rodando: com
  // texto digitado, redireciona/corrige sem perder o progresso já feito
  // (CLAUDE.md, "agente = modelo + harness" -> comportamento conversacional
  // obrigatório); com o campo vazio, continua parando o turno como antes.
  function handlePrimaryAction() {
    if (!streaming) {
      handleSend();
      return;
    }
    const correction = input.trim();
    if (!correction) {
      stop();
      return;
    }
    setInput("");
    void steer(correction);
  }

  return (
    <View
      style={[
        styles.root,
        previewModalVisible && Platform.OS === "web"
          ? ({ width: "55%", maxWidth: "none", alignSelf: "flex-start" } as any)
          : null,
      ]}
    >
      <View style={styles.header}>
        <Text accessibilityRole="header" aria-level={2} style={styles.title}>
          QA Accessibility — Assistente
        </Text>
        <View style={styles.headerSpacer} />
        <UsageNote usage={sessionUsage} scope="session" />
        <TouchableOpacity
          onPress={() => setHistoryModalVisible(true)}
          accessibilityRole="button"
          accessibilityLabel="Ver conversas anteriores"
          style={styles.backBtn}
        >
          <Text style={styles.backText}>Conversas</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => {
            if (streaming) return;
            startNewConversation();
            setInput("");
            setAttachments([]);
            setTimeout(() => {
              if (chatInputRef.current) {
                chatInputRef.current.focus();
              }
            }, 60);
          }}
          disabled={streaming}
          accessibilityRole="button"
          accessibilityLabel="Iniciar uma nova conversa"
          accessibilityState={{ disabled: streaming }}
          style={[styles.backBtn, streaming && styles.backBtnDisabled]}
        >
          <Text style={styles.backText}>Nova conversa</Text>
        </TouchableOpacity>
        {onOpenSettings && (
          <TouchableOpacity
            onPress={onOpenSettings}
            accessibilityRole="button"
            accessibilityLabel="Abrir configurações de IA"
            style={styles.backBtn}
          >
            <Text style={styles.backText}>Configurações</Text>
          </TouchableOpacity>
        )}
      </View>

      <ScrollView
        ref={scrollRef}
        style={styles.messages}
        contentContainerStyle={styles.messagesContent}
      >
        {messages.length === 0 && (
          <View style={styles.emptyState}>
            <Text accessibilityRole="header" aria-level={2} style={styles.emptyTitle}>Nenhuma conversa iniciada</Text>
            <Text style={styles.empty}>
              Oi! Eu sou seu assistente de acessibilidade digital. Digite uma mensagem, cole uma URL ou anexe arquivos para iniciar uma auditoria.
            </Text>
          </View>
        )}

        {(() => {
          interface Turn {
            user: typeof messages[0];
            assistant?: typeof messages[0];
            statuses: typeof messages;
          }

          const turns: Turn[] = [];
          let currentTurn: Turn | null = null;

          messages.forEach((m) => {
            if (m.role === "user") {
              if (currentTurn) {
                turns.push(currentTurn);
              }
              currentTurn = { user: m, statuses: [] };
            } else if (m.role === "assistant") {
              if (currentTurn) {
                currentTurn.assistant = m;
              }
            } else if (m.role === "status") {
              if (currentTurn) {
                currentTurn.statuses.push(m);
              }
            }
          });
          if (currentTurn) {
            turns.push(currentTurn);
          }

          let messageIndex = 0;
          return turns.map((turn, turnIdx) => {
            const isLastTurn = turnIdx === turns.length - 1;
            const isTurnBusy = streaming && isLastTurn;

            return (
              <React.Fragment key={`turn-${turnIdx}`}>
                {/* 1. Balão do Usuário */}
                <View
                  style={[styles.bubble, styles.userBubble]}
                  {...(Platform.OS === "web"
                    ? { dataSet: { messageIndex: String(messageIndex++) }, tabIndex: 0, "aria-label": `Mensagem de Você: ${turn.user.content}` }
                    : {})}
                >
                  {Platform.OS === "web" ? (
                    React.createElement(
                      "h2",
                      {
                        style: {
                          color: "#06b6d4",
                          fontFamily: font.body,
                          fontSize: 12,
                          marginBottom: 4,
                          marginTop: 0,
                          fontWeight: "600",
                          textTransform: "uppercase",
                          letterSpacing: 0.6,
                        },
                        "aria-level": 2,
                      },
                      "Você"
                    )
                  ) : (
                    <Text
                      accessibilityRole="header"
                      aria-level={2}
                      style={styles.roleLabel}
                    >
                      Você
                    </Text>
                  )}
                  {renderTextWithLinks(turn.user.content)}
                </View>

                {/* 2. Bloco de Execução do Turno (posicionado ANTES da resposta do assistente) */}
                <View
                  style={{ alignSelf: "stretch", marginVertical: 4 }}
                  aria-busy={isTurnBusy}
                >
                  {/* Timer de processamento: "Processando resposta em Xs" -> "Processou resposta em Xs" */}
                  {(isTurnBusy || (!isTurnBusy && (turn.assistant?.content || turn.statuses.length > 0))) && (
                    Platform.OS === "web" ? (
                      React.createElement(
                        "p",
                        isTurnBusy
                          ? { role: "timer", style: { color: colors.text.tertiary, fontSize: "12px", margin: "4px 0" } }
                          : { style: { color: colors.text.tertiary, fontSize: "12px", margin: "4px 0" } },
                        isTurnBusy
                          ? `Processando há ${Math.round(elapsedMs / 1000)}s`
                          : `Processou em ${Math.round(((isLastTurn ? durationMs : null) ?? 1000) / 1000)}s`
                      )
                    ) : (
                      <Text style={styles.usageNote}>
                        {isTurnBusy
                          ? `Processando há ${Math.round(elapsedMs / 1000)}s`
                          : `Processou em ${Math.round(((isLastTurn ? durationMs : null) ?? 1000) / 1000)}s`}
                      </Text>
                    )
                  )}

                  {/* Status de atividade em tempo real (como no agent-chat-app: turn.statusText) */}
                  {isLastTurn && isTurnBusy && !!activity && (
                    <View style={styles.activity}>
                      <Text style={styles.activityText}>{activity}</Text>
                    </View>
                  )}

                  <ActivityFeed
                    label="Andamento da squad"
                    messages={turn.statuses.filter((message) => message.kind === "squad")}
                  />

                  <ActivityFeed
                    label="Andamento dos especialistas"
                    messages={turn.statuses.filter((message) => message.kind === "agent" || message.kind === "phase")}
                  />

                  {/* Uma região por grupo de ferramenta, igual ao agent-chat-app. */}
                  {turn.statuses
                    .filter((message) => message.kind === "tool" && message.toolCall)
                    .map((message) => (
                      <ToolCallCard
                        key={message.groupKey || message.toolCall!.name}
                        toolCall={message.toolCall!}
                        messageIndex={messageIndex++}
                      />
                    ))}
                </View>

                {/* 3. Balão do Assistente (IA ASSISTENTE) - apenas o texto da resposta */}
                {(!!turn.assistant?.content || (!isTurnBusy && !turn.statuses.length)) && (
                  <View
                    style={[styles.bubble, styles.assistantBubble]}
                    {...(Platform.OS === "web"
                      ? { dataSet: { messageIndex: String(messageIndex++) }, tabIndex: 0, "aria-label": `Resposta do Assistente: ${turn.assistant?.content || ""}` }
                      : {})}
                  >
                    {Platform.OS === "web" ? (
                      React.createElement(
                        "h2",
                        {
                          style: {
                            color: "#818cf8",
                            fontFamily: font.body,
                            fontSize: 12,
                            marginBottom: 4,
                            marginTop: 0,
                            fontWeight: "600",
                            textTransform: "uppercase",
                            letterSpacing: 0.6,
                          },
                          "aria-level": 2,
                        },
                        "IA ASSISTENTE"
                      )
                    ) : (
                      <Text
                        accessibilityRole="header"
                        aria-level={2}
                        style={styles.roleLabel}
                      >
                        IA ASSISTENTE
                      </Text>
                    )}

                    {/* Conteúdo textual puro */}
                    {!!turn.assistant?.content && renderTextWithLinks(turn.assistant.content)}

                    {/* Fontes consultadas */}
                    {isLastTurn && !streaming && turnSources.length > 0 && (
                      <SourcesSection sources={turnSources} />
                    )}
                  </View>
                )}
              </React.Fragment>
            );
          });
        })()}

      </ScrollView>

      {/* Live region dos anúncios do turno (idêntico ao agent-chat-app) */}
      {Platform.OS === "web" ? (
        React.createElement(
          "div",
          {
            className: "sr-only",
            role: "status",
            "aria-live": "polite",
            "aria-atomic": "true",
            style: styles.webSrOnly,
          },
          announcement
        )
      ) : (
        <View accessibilityLiveRegion="polite" style={styles.srOnly}>
          <Text>{announcement}</Text>
        </View>
      )}

      {/* Anexos recolhidos em botão expansível */}
      {attachments.length > 0 && (
        <View style={{ paddingHorizontal: 16, paddingBottom: 8 }}>
          <TouchableOpacity
            onPress={() => setAttachmentsExpanded(!attachmentsExpanded)}
            style={[styles.choiceBtn, { alignSelf: "flex-start", marginBottom: attachmentsExpanded ? 8 : 0 }]}
            accessibilityRole="button"
            accessibilityLabel={
              attachmentsExpanded
                ? `Ocultar anexos (${attachments.length} arquivos)`
                : `Ver anexos (${attachments.length} arquivos)`
            }
            accessibilityState={{ expanded: attachmentsExpanded }}
          >
            <Text style={styles.choiceText}>
              {attachmentsExpanded
                ? `- Ocultar anexos (${attachments.length} arquivos)`
                : `+ Anexos adicionados (${attachments.length} arquivos)`}
            </Text>
          </TouchableOpacity>

          {attachmentsExpanded && (
            <View style={[styles.attachRow, { paddingHorizontal: 0, paddingBottom: 0 }]}>
              {attachments.map((a) => (
                <TouchableOpacity
                  key={a.name}
                  onPress={() => removeAttachment(a.name)}
                  accessibilityRole="button"
                  accessibilityLabel={`Remover anexo ${a.name}`}
                  style={styles.chip}
                >
                  <Text style={styles.chipText}>{a.name} ✕</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>
      )}

      {pendingClarify && (
        <ClarifyPanel
          key={pendingClarify.requestId}
          question={pendingClarify.question}
          choices={pendingClarify.choices}
          onAnswer={(answer) => void answerClarify(answer)}
        />
      )}

      <View style={styles.inputPanel}>
        {Platform.OS === "web" &&
          React.createElement("input", {
            ref: fileInputRef,
            type: "file",
            multiple: true,
            onChange: onPickFiles,
            style: { display: "none" },
            "aria-hidden": true,
          })}
        <Text style={styles.srOnly}>{PLACEHOLDER_MENSAGEM}</Text>
        <TextInput
          ref={chatInputRef}
          value={input}
          onChangeText={setInput}
          placeholder={PLACEHOLDER_MENSAGEM}
          placeholderTextColor={colors.text.tertiary}
          style={styles.input}
          // WCAG 2.5.3 Label in Name: o nome acessível PRECISA conter o texto
          // visível. Antes eram três strings diferentes para o mesmo campo --
          // visível "Pergunte, cole uma URL, ou anexe arquivos…", nome acessível
          // "Mensagem para o assistente", e um texto só-para-leitor "Digite sua
          // mensagem para a IA". Quem usa controle por voz falava o que via e
          // não ativava nada. Derivar do mesmo `PLACEHOLDER_MENSAGEM` impede que
          // voltem a divergir. Achado pelo próprio pipeline do produto
          // auditando a própria interface, confirmado em duas execuções.
          accessibilityLabel={
            streaming
              ? `${ROTULO_ACESSIVEL_MENSAGEM} — digite uma correção para redirecionar o assistente sem perder o que já foi feito`
              : ROTULO_ACESSIVEL_MENSAGEM
          }
          multiline
          autoComplete="off"
          onKeyPress={(e: any) => {
            if (e.nativeEvent.key === "Enter" && !e.nativeEvent.shiftKey) {
              e.preventDefault();
              handlePrimaryAction();
            }
          }}
        />
        <View style={styles.promptActions}>
          <TouchableOpacity
            onPress={() => {
              if (streaming) return;
              fileInputRef.current?.click();
            }}
            accessibilityRole="button"
            accessibilityState={{ disabled: streaming }}
            accessibilityLabel={
              streaming
                ? "Anexar arquivos — indisponível enquanto o assistente responde"
                : "Anexar arquivos ou projeto para análise"
            }
            style={[styles.attachActionBtn, streaming && styles.sendBtnDisabled]}
          >
            <Text style={styles.attachActionText}>Anexar arquivos</Text>
          </TouchableOpacity>
          {/* O estado nativo disabled mantém a semântica correta para teclado,
              automação e leitores de tela; o rótulo continua explicando como
              tornar o controle disponível. `handleSend` também mantém o guarda
              para chamadas programáticas. */}
          <TouchableOpacity
            onPress={handlePrimaryAction}
            accessibilityRole="button"
            accessibilityState={{ disabled: naoPodeEnviar }}
            disabled={naoPodeEnviar}
            accessibilityLabel={
              streaming
                ? input.trim()
                  ? "Redirecionar o assistente com esta correção, sem perder o progresso já feito"
                  : "Parar geração"
                : naoPodeEnviar
                  ? "Enviar mensagem — digite uma mensagem ou anexe um arquivo primeiro"
                  : "Enviar mensagem"
            }
            style={[styles.sendBtn, streaming && styles.stopBtn, naoPodeEnviar && styles.sendBtnDisabled]}
          >
            <Text style={styles.sendText}>
              {streaming ? (input.trim() ? "Redirecionar" : "Parar") : "Enviar mensagem"}
            </Text>
          </TouchableOpacity>
        </View>
      </View>


      {/* Modal Acessivel WAI-ARIA para Solicitacao Dinamica de Chaves de Servico */}
      {keyModalVisible && (
        <View
          style={styles.modalOverlay}
          aria-modal={true}
          role="dialog"
          aria-labelledby="modal-title"
        >
          <View ref={keyModalContainerRef as any} style={styles.modalContent}>
            <Text id="modal-title" style={styles.modalTitle}>
              Chave de API Solicitada
            </Text>
            <Text style={styles.modalDescription}>
              A IA precisa da sua chave para o serviço{" "}
              <Text style={{ fontWeight: "bold", color: colors.accent.text }}>
                {keyModalService.toUpperCase()}
              </Text>{" "}
              para concluir a ação na nuvem.
            </Text>

            <TextInput
              ref={keyInputRef}
              value={keyModalValue}
              onChangeText={setKeyModalValue}
              placeholder={`Cole sua chave do ${keyModalService} aqui…`}
              placeholderTextColor={colors.text.tertiary}
              secureTextEntry
              accessibilityLabel={`Campo para digitar a chave do serviço ${keyModalService}`}
              style={styles.modalInput}
              autoComplete="off"
              spellCheck={false}
              autoCapitalize="none"
              autoCorrect={false}
              aria-invalid={keyModalError ? true : undefined}
              aria-describedby={keyModalError ? "keyModalError" : undefined}
              // Escape é tratado uma única vez, no `useDialogFocus`.
              onKeyPress={(e: any) => {
                if (e.nativeEvent.key === "Enter") void handleSaveKey();
              }}
            />

            {keyModalError && (
              <Text
                style={styles.modalError}
                accessibilityRole="alert"
                role="alert"
                nativeID="keyModalError"
              >
                {keyModalError}
              </Text>
            )}

            <View style={styles.modalActions}>
              <TouchableOpacity
                onPress={() => setKeyModalVisible(false)}
                accessibilityRole="button"
                accessibilityLabel="Cancelar e fechar modal"
                style={styles.modalCancelBtn}
              >
                <Text style={styles.modalCancelText}>Cancelar</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={handleSaveKey}
                disabled={keyModalSaving || !keyModalValue.trim()}
                accessibilityRole="button"
                accessibilityLabel="Salvar chave e continuar execução da IA"
                style={[
                  styles.modalSaveBtn,
                  (!keyModalValue.trim() || keyModalSaving) && styles.sendBtnDisabled,
                ]}
              >
                <Text style={styles.modalSaveText}>
                  {keyModalSaving ? "Salvando…" : "Salvar e Continuar"}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      {/* Seletor de conversas anteriores */}
      {historyModalVisible && (
        <ConversationHistoryModal
          currentConversationId={conversationId}
          onSelect={(id) => switchConversation(id)}
          onClose={() => setHistoryModalVisible(false)}
          onCurrentConversationDeleted={startNewConversation}
        />
      )}

      {/* Live Preview Modal (estilo Replit) */}
      {previewModalVisible && (
        <LivePreviewModal
          sessionId={previewSessionId}
          totalPages={previewTotalPages}
        />
      )}

    </View>
  );
}



const styles = StyleSheet.create({
  root: {
    flex: 1,
    width: "100%",
    maxWidth: 1200,
    alignSelf: "center",
    backgroundColor: colors.bg.root,
    padding: 16,
    gap: 16,
  },
  header: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 12,
    paddingVertical: 16,
    paddingHorizontal: 24,
    backgroundColor: colors.bg.elevated,
    borderWidth: 1,
    borderColor: colors.border.strong,
    borderRadius: 12,
  },
  headerSpacer: { flex: 1 },
  // WCAG 2.5.8: alvo mínimo de 44px, igual ao backBtn do SettingsScreen.
  backBtn: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    minHeight: a11y.minTarget,
    justifyContent: "center",
    backgroundColor: colors.border.strong,
    borderRadius: 6,
  },
  backBtnDisabled: { opacity: 0.5 },
  backText: { color: colors.accent.text, fontFamily: font.body, fontSize: 14 },
  title: { color: colors.text.primary, fontFamily: font.display, fontSize: 20, fontWeight: "700" },
  attachRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, paddingHorizontal: 16, paddingBottom: 8 },
  chip: { backgroundColor: colors.accent.muted, borderRadius: 8, paddingVertical: 6, paddingHorizontal: 10, minHeight: 44, justifyContent: "center" },
  chipText: { color: colors.accent.text, fontFamily: font.body, fontSize: 13 },
  choiceBtn: {
    minHeight: 44,
    paddingVertical: 8,
    paddingHorizontal: 12,
    justifyContent: "center",
    backgroundColor: colors.bg.elevated,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: colors.border.strong,
  },
  choiceText: { color: colors.text.primary, fontFamily: font.body, fontSize: 14, fontWeight: "600" },
  messages: {
    flex: 1,
    backgroundColor: colors.bg.elevated,
    borderWidth: 1,
    borderColor: colors.border.strong,
    borderRadius: 12,
  },
  messagesContent: { padding: 24, gap: 24, flexGrow: 1 },
  emptyState: { alignItems: "center", justifyContent: "center", flex: 1, paddingVertical: 48 },
  emptyTitle: { color: colors.text.secondary, fontFamily: font.display, fontSize: 18, fontWeight: "700", marginBottom: 8 },
  empty: { color: colors.text.secondary, fontFamily: font.body, fontSize: 15, lineHeight: 22 },
  bubble: {
    alignSelf: "stretch",
    padding: 20,
    borderRadius: 8,
    maxWidth: "100%",
    borderLeftWidth: 4,
  },
  userBubble: { backgroundColor: "rgba(6, 182, 212, 0.05)", borderLeftColor: "#06b6d4" },
  assistantBubble: { backgroundColor: "rgba(99, 102, 241, 0.05)", borderLeftColor: "#6366f1" },
  roleLabel: { color: colors.text.tertiary, fontFamily: font.body, fontSize: 12, marginBottom: 4 },
  bubbleText: { color: colors.text.primary, fontFamily: font.body, fontSize: 15, lineHeight: 22 },
  srOnly: a11y.srOnly as any,
  webSrOnly: {
    position: "absolute",
    width: 1,
    height: 1,
    padding: 0,
    margin: -1,
    overflow: "hidden",
    whiteSpace: "nowrap",
    borderWidth: 0,
  } as any,
  activity: { alignSelf: "flex-start", paddingVertical: 6, paddingHorizontal: 10 },
  activityText: { color: colors.accent.text, fontFamily: font.body, fontSize: 13, fontStyle: "italic" },
  squadFeed: {
    alignSelf: "stretch",
    marginTop: 4,
    padding: 8,
    borderWidth: 1,
    borderColor: colors.border.DEFAULT,
    borderRadius: 8,
  },
  squadFeedTitle: { color: colors.text.secondary, fontFamily: font.body, fontSize: 12, marginBottom: 3 },
  statusLine: { alignSelf: "stretch", paddingVertical: 2, paddingHorizontal: 4 },
  statusLineText: { color: colors.text.tertiary, fontFamily: font.body, fontSize: 13, lineHeight: 19 },
  usageNoteRow: { marginTop: 8 },
  usageNote: { color: colors.text.tertiary, fontFamily: font.body, fontSize: 11 },
  inputPanel: {
    gap: 12,
    padding: 16,
    backgroundColor: colors.bg.elevated,
    borderWidth: 1,
    borderColor: colors.border.strong,
    borderRadius: 12,
  },
  promptActions: { flexDirection: "row", alignItems: "center", gap: 12 },
  inputHint: { color: colors.text.secondary, fontFamily: font.body, fontSize: 13 },
  input: {
    width: "100%",
    minHeight: 70,
    maxHeight: 120,
    backgroundColor: colors.bg.root,
    color: colors.text.primary,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border.strong,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontFamily: font.body,
    fontSize: 16,
  },
  attachActionBtn: {
    minHeight: 44,
    paddingHorizontal: 16,
    justifyContent: "center",
    backgroundColor: colors.border.strong,
    borderRadius: 6,
  },
  attachActionText: { color: colors.text.primary, fontFamily: font.body, fontSize: 14, fontWeight: "600" },
  sendBtn: {
    flex: 1,
    minHeight: 44,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#4f46e5",
    borderRadius: 6,
  },
  stopBtn: {
    backgroundColor: colors.danger.DEFAULT,
  },
  // Não reduzir opacity: o texto branco precisa manter contraste AA no estado
  // desabilitado (o navegador já comunica a indisponibilidade pelo atributo).
  sendBtnDisabled: { backgroundColor: "#373890" },
  sendText: { color: colors.text.onAccent, fontFamily: font.display, fontSize: 15, fontWeight: "700" },
  statusGroupContainer: {
    marginVertical: 6,
    backgroundColor: colors.bg.surface,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border.DEFAULT,
    overflow: "hidden",
    alignSelf: "stretch",
  },
  statusGroupHeader: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: colors.bg.elevated,
    flexDirection: "row",
    alignItems: "center",
    minHeight: 44,
  },
  statusGroupHeaderText: {
    fontSize: 13,
    color: colors.text.secondary,
    fontWeight: "600",
    fontFamily: font.body,
  },
  statusGroupContent: {
    padding: 8,
    borderTopWidth: 1,
    borderTopColor: colors.border.DEFAULT,
    backgroundColor: colors.bg.root,
  },
  toolRegion: {
    marginVertical: 8,
    backgroundColor: "#090d16",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border.strong,
    overflow: "hidden",
    alignSelf: "stretch",
  },
  toolHeader: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    backgroundColor: "#131b2e",
    borderBottomWidth: 1,
    borderBottomColor: colors.border.strong,
  },
  toolLogContainer: {
    padding: 16,
    maxHeight: 200,
    backgroundColor: "#050811",
  },
  toolLogText: { color: "#a7f3d0", fontFamily: font.mono, fontSize: 13, lineHeight: 19 },
  toolLogMuted: { color: colors.text.secondary, fontFamily: font.mono, fontSize: 13 },
  toolError: { color: "#f87171", fontFamily: font.body, fontSize: 13, paddingHorizontal: 16, paddingVertical: 12 },
  modalOverlay: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: "rgba(0,0,0,0.6)",
    justifyContent: "center",
    alignItems: "center",
    padding: 16,
    zIndex: 9999,
  },
  modalContent: {
    width: "100%",
    maxWidth: 480,
    backgroundColor: colors.bg.surface,
    borderRadius: 12,
    padding: 24,
    borderWidth: 1,
    borderColor: colors.border.DEFAULT,
    gap: 16,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: colors.text.primary,
    fontFamily: font.display,
  },
  modalDescription: {
    fontSize: 14,
    color: colors.text.secondary,
    fontFamily: font.body,
    lineHeight: 20,
  },
  modalError: {
    fontSize: 13,
    color: colors.danger.text,
    backgroundColor: colors.danger.bg,
    borderWidth: 1,
    borderColor: colors.danger.border,
    borderRadius: 8,
    padding: 10,
    fontFamily: font.body,
    lineHeight: 18,
  },
  modalInput: {
    minHeight: 44,
    backgroundColor: colors.bg.root,
    color: colors.text.primary,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border.DEFAULT,
    paddingHorizontal: 12,
    fontSize: 15,
    fontFamily: font.body,
  },
  modalActions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 12,
    marginTop: 8,
  },
  modalCancelBtn: {
    minHeight: 44,
    paddingHorizontal: 16,
    justifyContent: "center",
    alignItems: "center",
    borderRadius: 8,
    backgroundColor: colors.bg.elevated,
  },
  modalCancelText: {
    fontSize: 14,
    color: colors.text.secondary,
    fontFamily: font.body,
  },
  modalSaveBtn: {
    minHeight: 44,
    paddingHorizontal: 20,
    justifyContent: "center",
    alignItems: "center",

    borderRadius: 8,
    backgroundColor: colors.accent.DEFAULT,
  },
  modalSaveText: {
    fontSize: 14,
    fontWeight: "700",
    color: colors.text.onAccent,
    fontFamily: font.display,
  },
  floatingPreviewBtn: {
    position: "absolute",
    bottom: 80,
    right: 20,
    backgroundColor: colors.accent.DEFAULT,
    paddingVertical: 12,
    paddingHorizontal: 18,
    borderRadius: 24,
    minHeight: 44,
    minWidth: 44,
    justifyContent: "center",
    alignItems: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 6,
    zIndex: 999,
  },
  floatingPreviewText: {
    color: colors.text.onAccent,
    fontSize: 14,
    fontWeight: "700",
    fontFamily: font.display,
  },
  inlinePreviewBtn: {
    marginTop: 10,
    paddingVertical: 10,
    paddingHorizontal: 16,
    backgroundColor: colors.accent.DEFAULT,
    borderRadius: 8,
    minHeight: 44,
    alignSelf: "flex-start",
    justifyContent: "center",
    alignItems: "center",
  },
  inlinePreviewText: {
    color: colors.text.onAccent,
    fontSize: 14,
    fontWeight: "700",
    fontFamily: font.display,
  },
});


