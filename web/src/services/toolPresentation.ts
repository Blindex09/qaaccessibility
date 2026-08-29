/**
 * toolPresentation.ts
 * Utilitário de apresentação acessível de ferramentas e status da IA.
 * Portado fielmente da arquitetura de referência do agent-chat-app.
 */

export interface ToolCallData {
  id?: string;
  name: string;
  displayName?: string;
  status: "running" | "complete" | "failed";
  executionCount?: number;
  affectedCount?: number;
  logs?: string[];
  summary?: string;
  error?: string;
  params?: Record<string, any>;
  targets?: string[];
  action?: string;
  resultAction?: string;
  itemType?: string;
  itemSingular?: string;
  itemPlural?: string;
  connectorName?: string;
  serverName?: string;
}

function asArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  return value ? [String(value)] : [];
}

function humanizeName(raw?: string, fallback = "item"): string {
  const text = String(raw || fallback || "")
    .replace(/^mcp[_:]+/i, "")
    .replace(/[_-]+/g, " ")
    .trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : fallback;
}

function fileTargets(tool: ToolCallData): string[] {
  const params = tool.params || {};
  return asArray(tool.targets || params.files || params.paths || params.file || params.path || params.file_path);
}

function commandTargets(tool: ToolCallData): string[] {
  const params = tool.params || {};
  return asArray(tool.targets || params.commands || params.command || params.cmd || params.script);
}

function countedOutcome(tool: ToolCallData): string {
  const count = tool.affectedCount || 0;
  const action = tool.resultAction;
  const itemType = count === 1
    ? (tool.itemSingular || tool.itemType)
    : (tool.itemPlural || tool.itemType);
  if (!count || !action || !itemType) return "";
  return `${action} ${count} ${itemType}`;
}

export function operationKind(tool: ToolCallData): string {
  const name = (tool.name || "").toLowerCase();
  if (name.includes("image") && (name.includes("gen") || name.includes("create"))) return "image_generation";
  if (name.includes("image") && (name.includes("desc") || name.includes("read") || name.includes("vision"))) return "image_description";
  if (name.includes("audio") && (name.includes("listen") || name.includes("play"))) return "audio_listen";
  if (name.includes("audio") && name.includes("transcrib")) return "audio_transcription";
  if (name.includes("search") || name.includes("extract") || name.includes("web") || name.includes("tavily") || name.includes("exa")) return "web";
  if (/(apply|write|create|delete|move|copy|edit|patch).*file|file.*(write|create|delete|move|copy|edit|patch)|apply_patch|fix_and_zip/.test(name)) return "file_edit";
  if (name.includes("command") || name.includes("bash") || name.includes("exec") || name.includes("terminal")) return "command";
  if (tool.connectorName) return "connector";
  if (tool.serverName) return "mcp";
  return "tool";
}

export function isDirectMediaOperation(tool: ToolCallData): boolean {
  const kind = operationKind(tool);
  return kind === "image_generation" || kind === "image_description" || kind === "audio_listen" || kind === "audio_transcription";
}

export function toolGroupKey(tool: ToolCallData): string {
  const kind = operationKind(tool);
  if (kind === "web") return "group:web";
  if (kind === "file_edit") return "group:files";
  if (kind === "command") return "group:commands";
  if (kind === "connector") return `connector:${String(tool.connectorName || tool.displayName || tool.name).toLowerCase()}:${String(tool.resultAction || tool.action || "").toLowerCase()}`;
  if (kind === "mcp") return `mcp:${String(tool.serverName || "servidor").toLowerCase()}:${String(tool.displayName || tool.name).toLowerCase()}:${String(tool.resultAction || tool.action || "").toLowerCase()}`;
  return `tool:${tool.name || "generic"}`;
}

export function toolStatusText(tool: ToolCallData): string {
  const running = tool.status === "running";
  const kind = operationKind(tool);

  if (kind === "image_generation") return running ? "Criando imagem..." : tool.status === "failed" ? "Não foi possível criar a imagem." : "";
  if (kind === "image_description") return running ? "Descrevendo imagem..." : tool.status === "failed" ? "Não foi possível descrever a imagem." : "";
  if (kind === "audio_listen") return running ? "Ouvindo..." : tool.status === "failed" ? "Não foi possível processar o áudio." : "";
  if (kind === "audio_transcription") return running ? "Transcrevendo áudio..." : tool.status === "failed" ? "Não foi possível transcrever o áudio." : "";

  if (kind === "connector") {
    const connector = humanizeName(tool.connectorName || tool.displayName || tool.name, "Conector");
    if (running) return `Executando ${connector}...`;
    if (tool.status === "failed") return `Não foi possível executar ${connector}.`;
    const outcome = countedOutcome(tool);
    return outcome ? `Executou ${connector}; ${outcome}.` : tool.summary || `Executou ${connector}.`;
  }

  if (kind === "mcp") {
    const server = humanizeName(tool.serverName, "não identificado");
    const operation = humanizeName(tool.displayName || tool.name, "ferramenta");
    if (running) return `Executando ${operation} no servidor MCP ${server}...`;
    if (tool.status === "failed") return `Não foi possível executar ${operation} no servidor MCP ${server}.`;
    const outcome = countedOutcome(tool);
    return outcome
      ? `Executou ${operation} no servidor MCP ${server}; ${outcome}.`
      : tool.summary || `Executou ${operation} no servidor MCP ${server}.`;
  }

  if (kind === "web") {
    if (running) return (tool.executionCount || 1) > 1 ? "Pesquisando e navegando na web..." : "Pesquisando na web...";
    if (tool.status === "failed") return "Não foi possível concluir a pesquisa web.";
    const pages = tool.affectedCount || 0;
    if (pages === 1) return "Executou pesquisa web; navegou em 1 página.";
    if (pages > 1) return `Executou pesquisa web; navegou em ${pages} páginas.`;
    return "Executou pesquisa web.";
  }

  if (kind === "file_edit") {
    const targets = fileTargets(tool);
    const count = tool.affectedCount || targets.length;
    if (running) return count > 1 ? "Editando arquivos..." : `Editando arquivo${targets[0] ? ` ${targets[0]}` : ""}...`;
    if (tool.status === "failed") return count > 1 ? "Não foi possível editar os arquivos." : "Não foi possível editar o arquivo.";
    return count > 1 ? "Editou arquivos." : "Editou um arquivo.";
  }

  if (kind === "command") {
    const targets = commandTargets(tool);
    const count = tool.affectedCount || targets.length;
    if (running) return count > 1 ? "Executando comandos..." : `Executando comando${targets[0] ? ` ${targets[0]}` : ""}...`;
    if (tool.status === "failed") return count > 1 ? "A execução dos comandos falhou." : "A execução do comando falhou.";
    return count > 1 ? "Executou comandos." : `Executou comando${targets[0] ? ` ${targets[0]}` : ""}.`;
  }

  if (running) return `Executando ferramenta ${tool.name}...`;
  if (tool.status === "failed") return `A ferramenta ${tool.name} falhou.`;
  return tool.summary || `Executou ${tool.name}.`;
}
