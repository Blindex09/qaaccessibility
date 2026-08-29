/**
 * Metadados de apresentação das ferramentas do agente.
 *
 * Fonte única: o texto observável de progresso (`start`/`end`), o rótulo curto do
 * crachá (`label`) e o nível de risco (`risk`) de cada ferramenta vivem só aqui.
 *
 * O nível de risco NÃO é uma classificação nova: é a leitura em UI do que o
 * registry do backend já declara em `backend/src/services/chat_tools.py`.
 *   - `mutating`  → registrada com `requires_approval=True` E com efeito externo
 *                   irreversível pela app (reescreve o código do usuário,
 *                   publica algo, ou aciona software/alvo de terceiros).
 *   - `artifact`  → registrada com `requires_approval=True` mas o efeito é só
 *                   gerar um ficheiro para download (reversível: é só apagar).
 *   - `read`      → sem `requires_approval`: apenas lê/observa.
 */

import type { ToolResultSummary } from "./chat";

/** Nível de risco derivado do `requires_approval` + reversibilidade do efeito. */
export type ToolRisk = "read" | "artifact" | "mutating";

interface ToolMeta {
  /** Rótulo curto para crachá/etiqueta na UI. */
  label: string;
  risk: ToolRisk;
  /** Texto observável quando a ferramenta começa. */
  start: string;
  /** Texto observável quando a ferramenta termina. */
  end: string;
}

const SEARCH: ToolMeta = {
  label: "Busca na internet",
  risk: "read",
  start: "Buscando informações na internet...",
  end: "Pesquisa finalizada",
};

const EXTRACT: ToolMeta = {
  label: "Leitura de página",
  risk: "read",
  start: "Acessando e lendo o conteúdo da página...",
  end: "Leitura concluída",
};

const TOOL_META: Readonly<Record<string, ToolMeta>> = {
  tavily_search: SEARCH,
  exa_search: SEARCH,
  web_search_tool: SEARCH,
  web_search: SEARCH,
  web_extract_tool: EXTRACT,
  web_extract: EXTRACT,
  analyze_page: {
    label: "Auditoria de página",
    risk: "read",
    start: "Iniciando a auditoria da página...",
    end: "Auditoria concluída",
  },
  analyze_site: {
    label: "Auditoria do site",
    risk: "read",
    start: "Iniciando a auditoria das páginas do site...",
    end: "Auditoria de páginas concluída",
  },
  fix_and_zip_files: {
    label: "Correção de código",
    risk: "mutating",
    start: "Preparando e aplicando correções automáticas no código...",
    end: "Correções aplicadas com sucesso",
  },
  unzip_and_list_files: {
    label: "Extração de arquivos",
    risk: "read",
    start: "Processando e extraindo os arquivos do projeto...",
    end: "Arquivos extraídos com sucesso",
  },
  export_xlsx: {
    label: "Relatório Excel",
    risk: "artifact",
    start: "Gerando relatório em formato Excel...",
    end: "Relatório Excel gerado e pronto para download",
  },
  generate_vpat: {
    label: "Relatório VPAT",
    risk: "artifact",
    start: "Montando o relatório VPAT de conformidade...",
    end: "VPAT gerado e pronto para download",
  },
  generate_test_suite: {
    label: "Suíte de testes",
    risk: "artifact",
    start: "Escrevendo os testes automatizados de acessibilidade...",
    end: "Suíte de testes gerada com sucesso",
  },
  generate_automation_script: {
    label: "Script de automação",
    risk: "artifact",
    start: "Escrevendo o script de automação...",
    end: "Script de automação gerado com sucesso",
  },
  create_github_issue: {
    label: "Issue no GitHub",
    risk: "mutating",
    start: "Abrindo a issue no GitHub...",
    end: "Issue criada no GitHub",
  },
  run_remote_test: {
    label: "Teste remoto",
    risk: "mutating",
    start: "Rodando o teste automatizado no alvo indicado...",
    end: "Teste automatizado concluído",
  },
  nvda_speak: {
    label: "Leitura no NVDA",
    risk: "mutating",
    start: "Pedindo ao NVDA para ler o texto em voz alta…",
    end: "Leitura do NVDA concluída",
  },
  open_live_preview: {
    label: "Live Preview",
    risk: "read",
    start: "Abrindo a visualização antes e depois da página…",
    end: "Visualização pronta",
  },
  evaluate_research: {
    label: "Avaliação da pesquisa",
    risk: "read",
    start: "Avaliando se a pesquisa já responde à pergunta...",
    end: "Avaliação da pesquisa concluída",
  },
  run_deep_research: {
    label: "Pesquisa normativa",
    risk: "read",
    start: "Investigando as normas a fundo nas fontes oficiais...",
    end: "Pesquisa normativa concluída",
  },
  clarify: {
    label: "Confirmação",
    risk: "read",
    start: "Aguardando a sua confirmação...",
    end: "Confirmação recebida",
  },
  generate_image: { label: "Imagem", risk: "artifact", start: "Gerando imagem...", end: "Gerou imagem" },
  describe_image: { label: "Descrição de imagem", risk: "read", start: "Descrevendo imagem...", end: "Descreveu imagem" },
  listen_audio: { label: "Áudio", risk: "read", start: "Ouvindo áudio...", end: "Ouviu áudio" },
  transcribe_audio: { label: "Transcrição", risk: "read", start: "Transcrevendo áudio...", end: "Transcreveu áudio" },
  run_command: { label: "Comando", risk: "mutating", start: "Executando comando...", end: "Executou comando" },
  apply_patch: { label: "Edição de arquivo", risk: "mutating", start: "Editando arquivo...", end: "Editou arquivo" },
  edit_file: { label: "Edição de arquivo", risk: "mutating", start: "Editando arquivo...", end: "Editou arquivo" },
  analyze_document: {
    label: "Análise de documento",
    risk: "read",
    start: "Lendo e analisando o documento...",
    end: "Análise do documento concluída",
  },
  generate_checklist: {
    label: "Checklist de acessibilidade",
    risk: "artifact",
    start: "Gerando o checklist estruturado da análise...",
    end: "Checklist gerado com sucesso",
  },
  export_checklist_pdf: {
    label: "Checklist em PDF",
    risk: "artifact",
    start: "Exportando o checklist em PDF acessível...",
    end: "PDF do checklist pronto para download",
  },
  generate_accessibility_statement: {
    label: "Declaração de acessibilidade",
    risk: "artifact",
    start: "Montando a declaração pública de acessibilidade...",
    end: "Declaração de acessibilidade gerada",
  },
  export_accessibility_statement_pdf: {
    label: "Declaração em PDF",
    risk: "artifact",
    start: "Exportando a declaração de acessibilidade em PDF...",
    end: "PDF da declaração pronto para download",
  },
  read_local_project_files: {
    label: "Leitura de projeto local",
    risk: "read",
    start: "Lendo os arquivos do projeto local...",
    end: "Leitura do projeto local concluída",
  },
  fix_local_project_files: {
    label: "Correção de projeto local",
    risk: "mutating",
    start: "Aplicando correções de acessibilidade nos arquivos do projeto local...",
    end: "Projeto local corrigido",
  },
  undo_last_fix: {
    label: "Desfazer correção",
    risk: "mutating",
    start: "Revertendo a última correção aplicada...",
    end: "Correção revertida",
  },
  run_cross_browser_test: {
    label: "Teste cross-browser",
    risk: "mutating",
    start: "Testando a página nos motores de navegador reais (Chromium, Firefox, WebKit)...",
    end: "Teste cross-browser concluído",
  },
  install_playwright_browsers: {
    label: "Instalação do Playwright",
    risk: "mutating",
    start: "Instalando os navegadores do Playwright nesta máquina...",
    end: "Instalação do Playwright concluída",
  },
};

/**
 * Texto de conclusão com CONTAGEM REAL quando o backend forneceu um
 * `result_summary` (ver chat_runtime.py::_extract_result_summary) -- ex.:
 * "Corrigiu 8 arquivos" em vez do texto fixo genérico "Correções aplicadas
 * com sucesso". Sem contagem disponível (ferramenta sem mapeamento, ou
 * resultado deu erro), cai no texto estático de sempre.
 */
export function getToolResultText(name: string, summary?: ToolResultSummary | null): string {
  if (summary && typeof summary.count === "number") {
    const label = getToolLabel(name);
    const item = summary.count === 1 ? summary.item_singular : summary.item_plural;
    if (item) {
      return `${label}: ${summary.count} ${item}.`;
    }
  }
  return getToolProgressText(name, "end");
}

/** Texto observável de progresso. Ferramentas desconhecidas caem no genérico. */
export function getToolProgressText(name: string, status: "start" | "end"): string {
  const meta = TOOL_META[name];
  if (!meta) {
    if (name.startsWith("connector_")) {
      const connector = name.slice("connector_".length).split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
      return status === "start" ? `Executando ${connector}...` : `Executou ${connector}.`;
    }
    if (name.startsWith("mcp:") || name.startsWith("mcp_")) {
      const parts = name.split(/[:_]/).filter((part) => part && part !== "mcp");
      const rawServer = parts.shift() || "não identificado";
      const server = rawServer.charAt(0).toUpperCase() + rawServer.slice(1);
      const operation = parts.join(" ") || "ferramenta";
      return status === "start"
        ? `Executando ${operation} no servidor MCP ${server}...`
        : `Executou ${operation} no servidor MCP ${server}.`;
    }
    return status === "start" ? "Processando ação..." : "Ação finalizada";
  }
  return status === "start" ? meta.start : meta.end;
}

/** Família visual usada para agrupar execuções equivalentes no turno inteiro. */
export function getToolGroupKey(name: string): string {
  if (["tavily_search", "exa_search", "web_search_tool", "web_search", "web_extract_tool", "web_extract"].includes(name)) {
    return "web_research";
  }
  if (/file|zip|fix_and_zip/.test(name)) return "files";
  if (/command|terminal|script/.test(name)) return "commands";
  if (/^connector[_:]/.test(name)) return `connector:${name.split(/[_:]/).slice(1).join("_")}`;
  if (/^mcp[_:]/.test(name)) return `mcp:${name}`;
  return `tool:${name}`;
}

/** Rótulo curto para o crachá da ferramenta. Desconhecida → o próprio nome. */
export function getToolLabel(name: string): string {
  return TOOL_META[name]?.label ?? name;
}

/**
 * Risco da ferramenta. Uma ferramenta desconhecida que chegou pelo canal de
 * aprovação é tratada como `mutating`: o pedido de aprovação só existe para
 * ferramentas com efeito, então o padrão seguro é o mais cauteloso (fail-safe).
 */
export function getToolRisk(name: string): ToolRisk {
  return TOOL_META[name]?.risk ?? "mutating";
}
