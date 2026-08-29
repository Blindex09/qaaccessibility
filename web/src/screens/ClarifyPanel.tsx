import React, { useState } from "react";
import { Platform, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";

import { ScreenReaderText, hiddenFromAssistiveTech } from "../design/a11y";
import { colors, font } from "../design/tokens";
import {
  parseClarify,
  planStepStatusLabel,
  type PlanStep,
  type PlanStepStatus,
} from "../services/clarifyModel";
import type { ToolRisk } from "../services/toolMeta";

/**
 * Painel do fluxo `clarify`. Mostra três coisas conforme o que o agente pediu
 * (ver a convenção em `services/clarifyModel`):
 *   - plano/checklist, com o estado visível de cada passo;
 *   - pedido de aprovação de uma ferramenta, com crachá, argumentos legíveis e
 *     diferenciação visual de risco;
 *   - pergunta aberta.
 *
 * Acessibilidade: o tratamento depende de `view.kind`, porque as três coisas não
 * têm o mesmo peso.
 *
 *   - `approval` aparece como um bloco inline da conversa (`role="region"`),
 *     com o pedido e os botões Aprovar/Cancelar no próprio fluxo do chat.
 *   - `plan` e `question` são informativos: mostram um checklist ou perguntam
 *     algo, e não justificam prender o teclado nem roubar o foco a quem está a
 *     ler a conversa. São `role="region"` com nome acessível, e quem avisa que
 *     a vez é do usuário é a live region persistente do `ChatScreen`.
 *
 * Nenhum dos dois casos é live region aqui dentro: uma região inserida no DOM
 * ao mesmo tempo que o seu texto é anunciada de forma pouco fiável (o leitor de
 * tela só observa regiões que já existiam).
 *
 * No web a checklist sai como `<ul>/<li>` e os argumentos como `<dl>/<dt>/<dd>`,
 * para o leitor de tela anunciar contagem e pares chave→valor; o estado de cada
 * passo nunca depende só da cor (há glifo e texto); todos os alvos de toque
 * têm 44px.
 */

/** Nome acessível do diálogo/região — alvo do `aria-labelledby`. */
const PANEL_TITLE_ID = "clarify-panel-title";

interface RiskStyle {
  bg: string;
  text: string;
  border: string;
  accent: string;
  /** Consequência em linguagem simples — nunca só a cor dizendo o risco. */
  label: string;
  /** Glifo decorativo; a informação vai sempre também em texto. */
  glyph: string;
}

const RISK_STYLES: Record<ToolRisk, RiskStyle> = {
  mutating: {
    bg: colors.danger.bg,
    text: colors.danger.text,
    border: colors.danger.border,
    accent: colors.danger.DEFAULT,
    label: "Altera algo fora da app e não dá para desfazer daqui",
    glyph: "!",
  },
  artifact: {
    bg: colors.warning.bg,
    text: colors.warning.text,
    border: colors.warning.border,
    accent: colors.warning.DEFAULT,
    label: "Gera um arquivo para download",
    glyph: "+",
  },
  read: {
    bg: colors.info.bg,
    text: colors.info.text,
    border: colors.info.border,
    accent: colors.info.DEFAULT,
    label: "Apenas consulta informação",
    glyph: "i",
  },
};

const STEP_GLYPH: Record<PlanStepStatus, string> = {
  done: "✓",
  current: "▶",
  pending: "○",
};

const STEP_COLOR: Record<PlanStepStatus, string> = {
  done: colors.success.text,
  current: colors.accent.text,
  pending: colors.text.tertiary,
};

const isWeb = Platform.OS === "web";

/** Marca decorativa: o significado já vai no `accessibilityLabel` do item. */
function DecorativeGlyph({ glyph, color }: { glyph: string; color: string }) {
  return (
    <Text
      style={[styles.glyph, { color }]}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      aria-hidden
    >
      {glyph}
    </Text>
  );
}

function PlanChecklist({ intro, steps }: { intro: string; steps: PlanStep[] }) {
  const items = steps.map((step, index) => {
    const statusText = planStepStatusLabel(step.status);
    const label = `Passo ${index + 1} de ${steps.length}, ${statusText}: ${step.label}`;
    const body = (
      <View style={styles.stepRow}>
        {/* Texto real escondido: `accessibilityRole="text"` + `accessibilityLabel`
            não chega ao leitor de tela no web (ver design/a11y.tsx). */}
        <ScreenReaderText>{label}</ScreenReaderText>
        <DecorativeGlyph glyph={STEP_GLYPH[step.status]} color={STEP_COLOR[step.status]} />
        <View style={styles.stepBody} {...hiddenFromAssistiveTech}>
          <Text
            style={[
              styles.stepText,
              step.status === "done" && styles.stepTextDone,
              step.status === "current" && styles.stepTextCurrent,
            ]}
          >
            {step.label}
          </Text>
          <Text style={[styles.stepStatus, { color: STEP_COLOR[step.status] }]}>{statusText}</Text>
        </View>
      </View>
    );
    return isWeb
      ? React.createElement("li", { key: index, style: { listStyle: "none", margin: 0 } }, body)
      : <View key={index}>{body}</View>;
  });

  return (
    <View style={styles.planBox}>
      <Text id={PANEL_TITLE_ID} style={styles.planTitle}>
        {intro || "Plano proposto"}
      </Text>
      {isWeb
        ? React.createElement("ul", { style: { margin: 0, padding: 0 } }, items)
        : <View accessibilityLabel={`Plano com ${steps.length} passos`}>{items}</View>}
    </View>
  );
}

function ApprovalCard({
  toolLabel,
  risk,
  args,
  digest,
}: {
  toolLabel: string;
  risk: ToolRisk;
  args: { key: string; value: string }[];
  digest?: string;
}) {
  const style = RISK_STYLES[risk];

  const summaryArg = args.find((a) => a.key === "Resumo da ação" || a.key === "pre_exec_msg");
  const filteredArgs = args.filter((a) => a.key !== "Resumo da ação" && a.key !== "pre_exec_msg");

  const argRows = filteredArgs.map((arg) =>
    isWeb
      ? React.createElement(
          React.Fragment,
          { key: arg.key },
          React.createElement(
            "dt",
            { style: { margin: 0, color: colors.text.tertiary, fontFamily: font.body, fontSize: 12 } },
            arg.key,
          ),
          React.createElement(
            "dd",
            {
              style: {
                margin: "0 0 8px 0",
                color: colors.text.primary,
                fontFamily: font.mono,
                fontSize: 13,
                wordBreak: "break-word",
              },
            },
            arg.value,
          ),
        )
      : (
        <View key={arg.key} style={styles.argRow}>
          <ScreenReaderText>{`${arg.key}: ${arg.value}`}</ScreenReaderText>
          <View style={styles.argRow} {...hiddenFromAssistiveTech}>
            <Text style={styles.argKey}>{arg.key}</Text>
            <Text style={styles.argValue}>{arg.value}</Text>
          </View>
        </View>
      ),
  );

  return (
    <View style={[styles.approvalBox, { backgroundColor: style.bg, borderColor: style.border }]}>
      <View style={styles.badgeRow}>
        <View style={[styles.toolBadge, { borderColor: style.accent }]}>
          <Text style={styles.toolBadgeText}>{toolLabel}</Text>
        </View>
        <View style={[styles.riskPill, { borderColor: style.border }]}>
          <DecorativeGlyph glyph={style.glyph} color={style.text} />
          <Text style={[styles.riskPillText, { color: style.text }]}>{style.label}</Text>
        </View>
      </View>

      <Text id={PANEL_TITLE_ID} style={styles.approvalTitle}>
        Esta ação precisa da sua aprovação
      </Text>

      {summaryArg && (
        <Text style={{ color: colors.text.primary, fontFamily: font.body, fontSize: 14, marginTop: 4, lineHeight: 20 }}>
          {summaryArg.value}
        </Text>
      )}

      {filteredArgs.length > 0 && (
        <View style={styles.argsBox}>
          <Text style={styles.argsHeading}>O que será usado</Text>
          {isWeb
            ? React.createElement("dl", { style: { margin: 0 } }, argRows)
            : <View>{argRows}</View>}
        </View>
      )}

      {digest ? (
        <View style={styles.digestBox}>
          <Text style={styles.digestText}>{digest}</Text>
        </View>
      ) : null}
    </View>
  );
}

export interface ClarifyPanelProps {
  question: string;
  choices: string[];
  /** Resposta vazia = negar (o backend falha-fechado nesse caso). */
  onAnswer: (answer: string) => void;
}

export function ClarifyPanel({ question, choices, onAnswer }: ClarifyPanelProps) {
  const [draft, setDraft] = useState("");
  const view = parseClarify(question);
  const isApproval = view.kind === "approval";

  function answer(value: string) {
    setDraft("");
    onAnswer(value);
  }

  return (
    <View
      style={styles.clarifyBox}
      role="region"
      aria-labelledby={PANEL_TITLE_ID}
    >
      {view.kind === "approval" && (
        <ApprovalCard
          toolLabel={view.toolLabel}
          risk={view.risk}
          args={view.args}
          digest={view.digest}
        />
      )}

      {view.kind === "plan" && <PlanChecklist intro={view.intro} steps={view.steps} />}

      {view.kind === "question" && (
        <Text id={PANEL_TITLE_ID} style={styles.clarifyQuestion}>
          {question}
        </Text>
      )}

      {choices.length > 0 ? (
        <View style={styles.clarifyChoices}>
          {choices.map((choice) => {
            const isCancel = choice.toLowerCase() === "cancelar" || choice.toLowerCase() === "negar";
            return (
              <TouchableOpacity
                key={choice}
                onPress={() => answer(isCancel ? "" : choice)}
                accessibilityRole="button"
                accessibilityLabel={choice}
                style={[styles.choiceBtn, isCancel && styles.cancelBtn]}
              >
                <Text style={styles.choiceText}>{choice}</Text>
              </TouchableOpacity>
            );
          })}
          {!choices.some((c) => c.toLowerCase() === "cancelar" || c.toLowerCase() === "negar") && (
            <TouchableOpacity
              onPress={() => answer("")}
              accessibilityRole="button"
              accessibilityLabel="Cancelar"
              style={[styles.choiceBtn, styles.cancelBtn]}
            >
              <Text style={styles.choiceText}>Cancelar</Text>
            </TouchableOpacity>
          )}
        </View>
      ) : (
        <View style={styles.clarifyAnswerRow}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Digite sua resposta…"
            placeholderTextColor={colors.text.tertiary}
            style={styles.input}
            accessibilityLabel="Sua resposta para a pergunta do assistente"
            onSubmitEditing={() => answer(draft)}
          />
          <TouchableOpacity
            onPress={() => answer(draft)}
            accessibilityRole="button"
            accessibilityLabel="Responder"
            style={styles.sendBtn}
          >
            <Text style={styles.sendText}>Responder</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => answer("")}
            accessibilityRole="button"
            accessibilityLabel="Cancelar"
            style={[styles.sendBtn, styles.cancelBtn]}
          >
            <Text style={styles.sendText}>Cancelar</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  clarifyBox: {
    marginHorizontal: 16,
    marginBottom: 8,
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.accent.DEFAULT,
    backgroundColor: colors.accent.subtle,
    gap: 8,
  },
  clarifyQuestion: { color: colors.text.primary, fontFamily: font.body, fontSize: 15, fontWeight: "700" },
  clarifyChoices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choiceBtn: {
    minHeight: 44,
    justifyContent: "center",
    paddingHorizontal: 14,
    backgroundColor: colors.bg.surface,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.accent.DEFAULT,
  },
  choiceText: { color: colors.text.primary, fontFamily: font.body, fontSize: 14 },
  clarifyAnswerRow: { flexDirection: "row", alignItems: "flex-end", gap: 8 },
  cancelBtn: { backgroundColor: colors.bg.elevated },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    backgroundColor: colors.bg.surface,
    color: colors.text.primary,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontFamily: font.body,
    fontSize: 15,
  },
  sendBtn: {
    minHeight: 44,
    paddingHorizontal: 18,
    justifyContent: "center",
    backgroundColor: colors.accent.DEFAULT,
    borderRadius: 10,
  },
  sendText: { color: colors.text.onAccent, fontFamily: font.display, fontSize: 15, fontWeight: "700" },

  // ─── Plano / checklist ────────────────────────────────────────────────────
  planBox: {
    backgroundColor: colors.bg.surface,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.border.DEFAULT,
    padding: 12,
    gap: 8,
  },
  planTitle: { color: colors.text.primary, fontFamily: font.display, fontSize: 15, fontWeight: "700" },
  stepRow: { flexDirection: "row", alignItems: "flex-start", gap: 10, paddingVertical: 6 },
  stepBody: { flex: 1, gap: 2 },
  glyph: { fontFamily: font.body, fontSize: 14, lineHeight: 20, width: 16, textAlign: "center" },
  stepText: { color: colors.text.primary, fontFamily: font.body, fontSize: 14, lineHeight: 20 },
  stepTextDone: { color: colors.text.secondary },
  stepTextCurrent: { fontWeight: "700" },
  stepStatus: { fontFamily: font.body, fontSize: 11, letterSpacing: 0.5, textTransform: "uppercase" },

  // ─── Cartão de aprovação ──────────────────────────────────────────────────
  approvalBox: { borderRadius: 10, borderWidth: 1, padding: 12, gap: 10 },
  badgeRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 },
  toolBadge: {
    borderWidth: 1,
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 8,
    backgroundColor: colors.bg.surface,
  },
  toolBadgeText: { color: colors.text.primary, fontFamily: font.display, fontSize: 13, fontWeight: "700" },
  riskPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  riskPillText: { fontFamily: font.body, fontSize: 12 },
  approvalTitle: { color: colors.text.primary, fontFamily: font.body, fontSize: 15, fontWeight: "700" },
  argsBox: { gap: 4 },
  argsHeading: {
    color: colors.text.tertiary,
    fontFamily: font.body,
    fontSize: 11,
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  argRow: { gap: 2, marginBottom: 6 },
  argKey: { color: colors.text.tertiary, fontFamily: font.body, fontSize: 12 },
  argValue: { color: colors.text.primary, fontFamily: font.mono, fontSize: 13 },
  digestBox: { gap: 2 },
  digestText: { color: colors.text.secondary, fontFamily: font.mono, fontSize: 11, lineHeight: 16 },
});
