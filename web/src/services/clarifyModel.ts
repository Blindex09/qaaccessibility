/**
 * Classificação do evento `clarify` para apresentação na UI.
 *
 * O backend usa um único canal (`{type:"clarify", question, choices}`) para três
 * coisas bem diferentes, e a UI precisa distingui-las. A convenção é a seguinte:
 *
 * 1. APROVAÇÃO — a pergunta é gerada pela app, não pelo modelo: é o texto fixo de
 *    `_approval_summary` em `run_agent.py`, disparado para toda ferramenta com
 *    `requires_approval=True`. O formato é determinístico (nome da ferramenta,
 *    argumentos redigidos em JSON e digest SHA-256 de 64 hex), portanto é
 *    interpretado aqui como formato de fio interno — não como linguagem natural.
 *
 * 2. PLANO — a pergunta traz uma lista de passos. É o que as regras 12/13 do
 *    prompt (`chat_runtime.py`) pedem ao modelo antes de `analyze_page`/
 *    `analyze_site` e antes de `fix_and_zip_files`. Convenção de marcação, em
 *    Markdown comum (lista numerada ou com travessão), com estado opcional no
 *    estilo das task lists do GitHub:
 *        `[x]` concluído · `[~]` em curso · `[ ]` ou sem marca → pendente
 *    Duas ou mais entradas de lista caracterizam um plano.
 *
 * 3. PERGUNTA — qualquer outra coisa: pergunta aberta ou de sim/não.
 *
 * Tudo aqui é função pura, sem React, para poder ser testado a sério no ambiente
 * `node` do jest (o preset do React Native não está disponível nos testes).
 */
import { getToolLabel, getToolRisk, type ToolRisk } from "./toolMeta";

/** Estado de um passo do plano. */
export type PlanStepStatus = "pending" | "current" | "done";

export interface PlanStep {
  label: string;
  status: PlanStepStatus;
}

/** Um argumento da ferramenta, já pronto para a lista chave→valor. */
export interface ApprovalArg {
  key: string;
  value: string;
}

export type ClarifyPresentation =
  | {
      kind: "approval";
      /** Nome técnico da ferramenta, como registado no backend. */
      tool: string;
      /** Rótulo curto para o crachá. */
      toolLabel: string;
      risk: ToolRisk;
      args: ApprovalArg[];
      /** Digest SHA-256 que identifica exatamente esta ação. */
      digest: string;
    }
  | { kind: "plan"; intro: string; steps: PlanStep[] }
  | { kind: "question" };

/**
 * Formato de fio de `_approval_summary` (run_agent.py). O digest de 64 hex e o
 * sufixo fixo tornam a âncora inequívoca mesmo com JSON com pontos no meio.
 */
const APPROVAL_RE =
  /^A ferramenta '(.+?)' realizará uma ação com efeito externo ou gravará um artefato\. Argumentos: (.*)\. Identificador da ação: ([0-9a-f]{64})\. Aprovar exatamente esta ação\?$/s;

/** `1. passo` · `1) passo` · `- passo` · `* passo`, com `[x]`/`[~]`/`[ ]` opcional. */
const STEP_RE = /^\s*(?:\d+[.)]|[-*])\s+(?:\[([ x~])\]\s*)?(.+?)\s*$/i;

function statusFromMark(mark: string | undefined): PlanStepStatus {
  if (mark === "x" || mark === "X") return "done";
  if (mark === "~") return "current";
  return "pending";
}

function formatArgValue(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function parseApprovalArgs(raw: string): ApprovalArg[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [{ key: "argumentos", value: raw }];
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return [{ key: "argumentos", value: formatArgValue(parsed) }];
  }
  return Object.entries(parsed as Record<string, unknown>).map(([key, value]) => ({
    key,
    value: formatArgValue(value),
  }));
}

/** Interpreta a pergunta de um evento `clarify` e diz como a UI deve mostrá-la. */
export function parseClarify(question: string): ClarifyPresentation {
  const text = (question ?? "").trim();

  const approval = APPROVAL_RE.exec(text);
  if (approval) {
    const tool = approval[1];
    return {
      kind: "approval",
      tool,
      toolLabel: getToolLabel(tool),
      risk: getToolRisk(tool),
      args: parseApprovalArgs(approval[2]),
      digest: approval[3],
    };
  }

  const intro: string[] = [];
  const steps: PlanStep[] = [];
  for (const line of text.split("\n")) {
    const step = STEP_RE.exec(line);
    if (step) {
      steps.push({ label: step[2], status: statusFromMark(step[1]) });
    } else if (steps.length === 0 && line.trim()) {
      intro.push(line.trim());
    }
  }
  if (steps.length >= 2) {
    return { kind: "plan", intro: intro.join(" "), steps };
  }

  return { kind: "question" };
}

/** Rótulo acessível do estado de um passo (usado no `accessibilityLabel`). */
export function planStepStatusLabel(status: PlanStepStatus): string {
  switch (status) {
    case "done":
      return "Concluído";
    case "current":
      return "Em curso";
    default:
      return "Pendente";
  }
}
