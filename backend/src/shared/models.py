from enum import Enum

from pydantic import BaseModel, Field, field_validator

# Frameworks detectaveis pelo ClassifierAgent.
# Fonte unica de verdade: compartilhada entre classifier.py e orchestrator.py.
# Adicionar suporte a novo framework = adicionar aqui + criar o agente correspondente.
SUPPORTED_FRAMEWORKS: frozenset[str] = frozenset({"react", "vue", "angular", "svelte", "tailwind"})


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(str, Enum):
    """Confianca de deteccao (o agente acha que isso E uma violacao real) --
    eixo distinto de Severity (impacto SE for real). Um issue critical com
    confidence low significa "se isso for real, e grave, mas nao tenho
    certeza que e" -- informacao que severity sozinha nao carrega."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Guideline(str, Enum):
    WCAG_2_2 = "WCAG 2.2"
    WAI_ARIA = "WAI-ARIA"
    ADA_508 = "ADA/Section 508"


_GUIDELINE_NORMALIZE = {
    "WCAG 2.0": "WCAG 2.2",
    "WCAG 2.1": "WCAG 2.2",
    "WCAG 2.3": "WCAG 2.2",
    "WCAG 2.4": "WCAG 2.2",
    "WCAG 2.5": "WCAG 2.2",
    "WCAG 3.0": "WCAG 2.2",
    "WCAG": "WCAG 2.2",
    "WAI ARIA": "WAI-ARIA",
    "ARIA": "WAI-ARIA",
    "Section 508": "ADA/Section 508",
    "ADA": "ADA/Section 508",
    "508": "ADA/Section 508",
}


class TaskType(str, Enum):
    ANALYZE = "analyze"
    FIX = "fix"
    CHECKLIST = "checklist"
    REPORT = "report"
    VPAT = "vpat"
    TESTS = "tests"


class ChecklistStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MANUAL = "manual"
    NOT_APPLICABLE = "not_applicable"


class AccessibilityIssue(BaseModel):
    id: str
    guideline: Guideline
    criterion: str = Field(..., description="Ex: 1.1.1 Non-text Content")
    severity: Severity
    element: str = Field(..., description="HTML element ou seletor CSS")
    description: str
    suggestion: str
    # confidence de deteccao -- opcional para compatibilidade com agentes/
    # respostas antigas que nao preenchem este campo ainda
    confidence: Confidence | None = None
    # bilingual rich fields (all optional for backward compatibility)
    level: str | None = None
    description_technical: str | None = None
    why_simple: str | None = None
    why_technical: str | None = None
    suggestion_technical: str | None = None
    wcag_url: str | None = None
    # i18n fields — populated by i18n layer after agent output
    criterion_pt: str | None = None
    severity_pt: str | None = None
    # preview fields — element HTML after fix (populated by fixer pipeline)
    fixed_element_html: str | None = None
    url: str | None = None

    @field_validator("guideline", mode="before")
    @classmethod
    def normalize_guideline(cls, v: object) -> object:
        if isinstance(v, str):
            val = v.strip().upper()
            if val.startswith("WCAG"):
                return "WCAG 2.2"
            if "ARIA" in val:
                return "WAI-ARIA"
            if "508" in val or "ADA" in val:
                return "ADA/Section 508"
            return _GUIDELINE_NORMALIZE.get(v, v)
        return v

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v


class ChecklistItem(BaseModel):
    id: str
    criterion: str
    guideline: Guideline
    status: ChecklistStatus
    priority: Severity
    notes: str | None = None


class ReportOutput(BaseModel):
    report_id: str
    summary: str
    score: int = Field(..., ge=0, le=100, description="Score de acessibilidade 0-100")
    issues: list[AccessibilityIssue]
    checklist: list[ChecklistItem]
    fixed_html: str | None = None
    download_url: str | None = None


class AnalyzeUrlRequest(BaseModel):
    url: str = Field(..., description="URL externa para analisar")
    only_agents: list[str] | None = Field(
        default=None,
        description="Lista opcional de agentes a executar. Se omitido, o orquestrador seleciona automaticamente os agentes relevantes.",
    )
    cookies: list[dict] | None = Field(default=None, description="Cookies de sessao para autenticacao")
    auth_headers: dict[str, str] | None = Field(default=None, description="Cabecalhos HTTP extras para a requisicao")
    actions: list[dict] | None = Field(default=None, description="Ações Playwright interativas sequenciais")


class CrawlRequest(BaseModel):
    url: str = Field(..., description="URL raiz do site a ser crawleado")
    max_pages: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Limite de páginas a visitar (1-50, padrão 10)",
    )
    cookies: list[dict] | None = Field(default=None, description="Cookies de sessao para autenticacao")
    auth_headers: dict[str, str] | None = Field(default=None, description="Cabecalhos HTTP extras para as requisicoes")


class AgentMetrics(BaseModel):
    """Métricas de execução por sub-agente, usadas pelo orquestrador."""

    agent: str
    duration_ms: float
    issues_found: int
    success: bool
    delegated_by: str | None = None


class CrawlPageIssues(BaseModel):
    url: str
    issues: list[AccessibilityIssue]
    agent_metrics: list[AgentMetrics] = Field(default_factory=list)
    success: bool
    error: str | None = None


class CrawlResult(BaseModel):
    total_pages: int
    pages_ok: int
    pages_failed: int
    all_issues: list[AccessibilityIssue]
    pages: list[CrawlPageIssues]
    total_issues: int
    score: int = Field(..., ge=0, le=100)


class AnalyzeFileRequest(BaseModel):
    html_content: str = Field(..., description="Conteúdo HTML do arquivo local")
    filename: str | None = None


class FixRequest(BaseModel):
    html_content: str
    issues: list[AccessibilityIssue]
    approved_issue_ids: list[str] | None = None
    custom_instruction: str | None = None
    self_healing: bool | None = Field(default=True, description="Executa o loop autocicatrizante com axe-core")


class FixResponse(BaseModel):
    fixed_html: str
    changes_summary: list[str]


class AgentResult(BaseModel):
    agent: str
    success: bool
    data: dict
    error: str | None = None


# ── Test Generator models ─────────────────────────────────────────────────────
# Derivados de: playwright-expert.toml + accessibility-tester.md + tdd-orchestrator.toml


class AccessibilityTest(BaseModel):
    """Teste gerado para uma violação de acessibilidade específica."""

    test_id: str
    criterion: str
    severity: Severity
    framework: str = Field(..., description="playwright | axe-core | jest-axe")
    description: str = Field(..., description="O que o teste valida")
    code: str = Field(..., description="Código do teste pronto para colar no CI")
    element_hint: str = Field(..., description="Seletor ou contexto do elemento testado")


class TestSuite(BaseModel):
    """Suite de testes gerada a partir dos issues encontrados."""

    target: str = Field(..., description="URL ou nome do arquivo analisado")
    total_tests: int
    tests: list[AccessibilityTest]
    setup_snippet: str = Field(..., description="Código de setup/imports necessario")
    ci_instructions: str = Field(..., description="Como integrar ao CI")


class TestGeneratorRequest(BaseModel):
    issues: list[AccessibilityIssue] = Field(default_factory=list)
    target: str = Field(default="", description="URL ou nome do projeto analisado")
    html_content: str | None = Field(
        default=None,
        description="HTML para analisar e gerar testes em uma chamada (HTML->entregavel). "
        "Se fornecido, roda o pipeline completo; senao usa 'issues' diretamente.",
    )


# ── VPAT Reporter models ──────────────────────────────────────────────────────
# Derivados de: compliance-auditor.md


class ConformanceLevel(str, Enum):
    SUPPORTS = "Supports"
    PARTIALLY_SUPPORTS = "Partially Supports"
    DOES_NOT_SUPPORT = "Does Not Support"
    NOT_APPLICABLE = "Not Applicable"
    NOT_EVALUATED = "Not Evaluated"


class VPATCriterion(BaseModel):
    """Conformidade declarada para um criterio WCAG 2.2."""

    criterion_id: str = Field(..., description="Ex: 1.1.1")
    criterion_name: str = Field(..., description="Ex: Non-text Content")
    wcag_level: str = Field(..., description="A | AA | AAA")
    conformance: ConformanceLevel
    remarks: str = Field(..., description="Justificativa e detalhes da conformidade")
    issues_found: list[str] = Field(default_factory=list, description="IDs dos issues relacionados")


class VPATReport(BaseModel):
    """VPAT - Voluntary Product Accessibility Template (WCAG 2.2 Edition)."""

    product_name: str
    target: str
    wcag_version: str = "WCAG 2.2"
    evaluation_date: str
    overall_conformance: str = Field(..., description="Resumo executivo de conformidade")
    level_a_criteria: list[VPATCriterion]
    level_aa_criteria: list[VPATCriterion]
    total_criteria_evaluated: int
    total_supports: int
    total_partially_supports: int
    total_does_not_support: int
    total_not_applicable: int


class VPATRequest(BaseModel):
    issues: list[AccessibilityIssue] = Field(default_factory=list)
    target: str = Field(default="", description="URL ou nome do produto avaliado")
    product_name: str = Field(default="Produto Avaliado")
    html_content: str | None = Field(
        default=None,
        description="HTML para analisar e gerar o VPAT em uma chamada (HTML->entregavel). "
        "Se fornecido, roda o pipeline completo; senao usa 'issues' diretamente.",
    )


# ── Screen Reader Verification models ─────────────────────────────────────────
# Cruza a arvore de acessibilidade REAL do Chromium (mesma API que NVDA/JAWS/
# Narrator consultam) contra regras deterministicas de nome acessivel ausente
# ou generico -- ver services/screen_reader_verification.py.


class ScreenReaderVerificationRequest(BaseModel):
    url: str = Field(..., description="URL da pagina a verificar")
    speak_via_nvda: bool = Field(
        default=False,
        description="Se true, e o NVDA real estiver rodando na maquina do servidor, "
        "le os achados em voz alta para confirmacao humana.",
    )


class ScreenReaderFindingResponse(BaseModel):
    role: str
    path: str
    problem: str
    severity: str
    announcement_preview: str


class ScreenReaderVerificationResponse(BaseModel):
    url: str
    total_interactive_nodes: int
    findings: list[ScreenReaderFindingResponse]
    nvda_running: bool
    spoken_findings: int


# ── Design Review (shift-left) models ─────────────────────────────────────────
# Diferente de AccessibilityIssue (violacao confirmada em HTML/codigo que ja
# existe), DesignRiskFlag e um risco ANTECIPADO a partir de um requisito, user
# story ou descricao de componente -- antes de qualquer linha de codigo. Ver
# agents/design_review/design_review.py.


class DesignRiskFlag(BaseModel):
    id: str
    risk: str = Field(..., description="Risco de acessibilidade identificado no requisito")
    wcag_criteria: list[str] = Field(
        default_factory=list, description="Criterios WCAG 2.2 provavelmente afetados (ex.: '2.4.3 Focus Order')"
    )
    severity: Severity
    rationale: str = Field(..., description="Por que esse requisito especifico gera esse risco")
    recommendation: str = Field(..., description="Orientacao concreta para construir accessivel desde o design")


class DesignReviewRequest(BaseModel):
    requirement_text: str = Field(
        ..., description="Texto livre: requisito, user story, PRD ou descricao de componente/fluxo a revisar"
    )
    component_type: str | None = Field(
        default=None,
        description="Opcional: tipo de componente/fluxo (ex.: 'formulario multi-etapa', 'drag-and-drop', 'modal')",
    )


class DesignReviewResponse(BaseModel):
    requirement_text: str
    risk_flags: list[DesignRiskFlag]
