"""Catálogo dos grupos de ferramentas do chat (regra 9, engenharia de contexto).

O código só sabe QUAIS ferramentas existem e de que grupo são. Quem decide quais grupos uma
tarefa precisa é o roteador, pelo significado do pedido, na mesma consulta em que ele escolhe o
modelo. Sem opinião do roteador (modelo escolhido à mão, falha do roteador), vai tudo.

Nada fica fora de alcance: o agente chama `enable_tool_group` e o grupo entra na hora, sem sair
no meio da tarefa. A concessão de segurança não muda: todas as ferramentas do chat continuam
concedidas ao nascer; aqui só se escolhe o que é OFERECIDO ao modelo em cada chamada.
"""

from collections.abc import Iterable

ENABLE_TOOL_GROUP = "enable_tool_group"

# Sempre oferecidas: perguntar à pessoa, consultar a squad e pedir outro grupo.
CORE_TOOLS: frozenset[str] = frozenset({"clarify", "consult_squad", "load_skill", "remember_skill", ENABLE_TOOL_GROUP})

TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "analise": (
        "analyze_page", "analyze_site", "analyze_document", "verify_screen_reader_announcements",
        "design_review", "unzip_and_list_files", "read_local_project_files",
    ),
    "correcao": ("fix_and_zip_files", "fix_local_project_files", "undo_last_fix", "open_live_preview"),
    "documentos": (
        "generate_checklist", "export_checklist_pdf", "export_xlsx", "export_sarif", "generate_vpat",
        "generate_accessibility_statement", "export_accessibility_statement_pdf",
    ),
    "testes": (
        "generate_test_suite", "generate_automation_script", "run_remote_test", "run_cross_browser_test",
        "install_playwright_browsers", "run_code_in_sandbox",
    ),
    "pesquisa": ("tavily_search", "exa_search", "evaluate_research", "run_deep_research"),
    "integracoes": ("create_github_issue", "create_jira_issue", "create_azure_devops_work_item"),
}

GROUP_DESCRIPTIONS: dict[str, str] = {
    "analise": "examinar a acessibilidade de uma página, site, documento, projeto, requisito ou leitor de tela",
    "correcao": "corrigir código ou arquivos, mostrar o antes e depois e desfazer correções",
    "documentos": "gerar checklist, planilha, VPAT, declaração de acessibilidade ou relatório SARIF",
    "testes": "gerar suíte de testes ou script de automação e executar testes reais em navegadores",
    "pesquisa": (
        "pesquisar na web ou nas normas e avaliar as fontes; a pesquisa profunda gasta centenas de milhares "
        "de tokens, então só quando a pessoa pede aprofundamento"
    ),
    "integracoes": "abrir ticket no GitHub, Jira ou Azure DevOps",
}


def tools_of_group(group: str) -> frozenset[str]:
    return frozenset(TOOL_GROUPS.get(group, ()))


def classified_tools() -> frozenset[str]:
    return CORE_TOOLS | frozenset(name for names in TOOL_GROUPS.values() for name in names)


def offered_tools(selected_groups: Iterable[str] | None, all_tools: Iterable[str]) -> frozenset[str] | None:
    """Ferramentas a oferecer ao modelo. None = sem opinião do roteador: vai tudo.

    Ferramentas ainda não classificadas em nenhum grupo vão sempre, para uma ferramenta nova nunca
    sumir em silêncio (um teste obriga a classificá-la).
    """
    if selected_groups is None:
        return None
    all_names = frozenset(all_tools)
    chosen = set(CORE_TOOLS)
    for group in selected_groups:
        chosen |= tools_of_group(group)
    chosen |= all_names - classified_tools()
    return frozenset(chosen & all_names)
