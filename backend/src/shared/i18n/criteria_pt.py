"""
criteria_pt.py
Camada centralizada de tradução oficial (W3C Brasil / CEWEB / WCAG 2.2)
para critérios, diretrizes, princípios e severidades de acessibilidade digital.

Garante acentuação rigorosa em português (á, é, í, ó, ú, â, ê, ô, ã, õ, ç)
para perfeita pronúncia por sintetizadores de voz e leitores de tela (NVDA, JAWS).
"""

import logging

from backend.src.shared.models import AccessibilityIssue, Severity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severidades em Português Formal
# ---------------------------------------------------------------------------
_SEVERITY_PT: dict[str, str] = {
    Severity.CRITICAL: "Crítica",
    Severity.HIGH: "Alta",
    Severity.MEDIUM: "Média",
    Severity.LOW: "Baixa",
}

# ---------------------------------------------------------------------------
# Princípios Oficiais WCAG 2.2 (POUR)
# ---------------------------------------------------------------------------
_PRINCIPLES_PT: dict[str, tuple[str, str]] = {
    "1": (
        "Princípio 1: Perceptível",
        "A informação e os componentes da interface do usuário devem ser apresentados de forma que possam ser percebidos por todos os sentidos.",
    ),
    "2": (
        "Princípio 2: Operável",
        "Os componentes da interface do usuário e a navegação devem ser operáveis por qualquer pessoa, inclusive exclusivamente via teclado.",
    ),
    "3": (
        "Princípio 3: Compreensível",
        "A informação e a operação da interface do usuário devem ser compreensíveis, previsíveis e com instruções claras de uso.",
    ),
    "4": (
        "Princípio 4: Robusto",
        "O conteúdo deve ser robusto o suficiente para ser interpretado com segurança por tecnologias assistivas e leitores de tela.",
    ),
}

# ---------------------------------------------------------------------------
# Diretrizes Oficiais WCAG 2.2 (13 Diretrizes)
# ---------------------------------------------------------------------------
_GUIDELINES_PT: dict[str, str] = {
    "1.1": "Diretriz 1.1: Alternativas em Texto",
    "1.2": "Diretriz 1.2: Mídias Baseadas em Tempo",
    "1.3": "Diretriz 1.3: Adaptável",
    "1.4": "Diretriz 1.4: Discernível",
    "2.1": "Diretriz 2.1: Acessível por Teclado",
    "2.2": "Diretriz 2.2: Tempo Suficiente",
    "2.3": "Diretriz 2.3: Convulsões e Reações Físicas",
    "2.4": "Diretriz 2.4: Navegável",
    "2.5": "Diretriz 2.5: Modalidades de Entrada",
    "3.1": "Diretriz 3.1: Legível",
    "3.2": "Diretriz 3.2: Previsível",
    "3.3": "Diretriz 3.3: Assistência de Entrada",
    "4.1": "Diretriz 4.1: Compatível",
}

# ---------------------------------------------------------------------------
# Critérios de Sucesso WCAG 2.2 (Tradução Oficial W3C Brasil / CEWEB)
# ---------------------------------------------------------------------------
_CRITERION_PT: dict[str, str] = {
    # 1. Perceptível
    "1.1.1": "1.1.1 Conteúdo Não Textual",
    "1.2.1": "1.2.1 Apenas Áudio e Apenas Vídeo (Pré-gravado)",
    "1.2.2": "1.2.2 Legendas (Pré-gravadas)",
    "1.2.3": "1.2.3 Audiodescrição ou Alternativa em Mídia (Pré-gravada)",
    "1.2.4": "1.2.4 Legendas (Ao Vivo)",
    "1.2.5": "1.2.5 Audiodescrição (Pré-gravada)",
    "1.3.1": "1.3.1 Informações e Relações",
    "1.3.2": "1.3.2 Sequência com Significado",
    "1.3.3": "1.3.3 Características Sensoriais",
    "1.3.4": "1.3.4 Orientação",
    "1.3.5": "1.3.5 Identificar a Finalidade da Entrada",
    "1.3.6": "1.3.6 Identificar a Finalidade",
    "1.4.1": "1.4.1 Uso de Cor",
    "1.4.2": "1.4.2 Controle de Áudio",
    "1.4.3": "1.4.3 Contraste (Mínimo)",
    "1.4.4": "1.4.4 Redimensionamento de Texto",
    "1.4.5": "1.4.5 Imagens de Texto",
    "1.4.6": "1.4.6 Contraste (Aprimorado)",
    "1.4.10": "1.4.10 Redistribuição de Conteúdo (Reflow)",
    "1.4.11": "1.4.11 Contraste Não Textual",
    "1.4.12": "1.4.12 Espaçamento de Texto",
    "1.4.13": "1.4.13 Conteúdo no Foco ou no Ponteiro",
    # 2. Operável
    "2.1.1": "2.1.1 Teclado",
    "2.1.2": "2.1.2 Sem Armadilha de Teclado",
    "2.1.4": "2.1.4 Atalhos de Teclado de Caractere Único",
    "2.2.1": "2.2.1 Tempo Ajustável",
    "2.2.2": "2.2.2 Pausar, Parar, Ocultar",
    "2.3.1": "2.3.1 Três Flashes ou Abaixo do Limite",
    "2.4.1": "2.4.1 Ignorar Blocos (Evitar Blocos Repetitivos)",
    "2.4.2": "2.4.2 Página com Título",
    "2.4.3": "2.4.3 Ordem do Foco",
    "2.4.4": "2.4.4 Finalidade do Link (Em Contexto)",
    "2.4.5": "2.4.5 Múltiplas Formas",
    "2.4.6": "2.4.6 Cabeçalhos e Rótulos",
    "2.4.7": "2.4.7 Foco Visível",
    "2.4.8": "2.4.8 Localização",
    "2.4.11": "2.4.11 Foco Não Ocultado (Mínimo)",
    "2.4.12": "2.4.12 Foco Não Ocultado (Aprimorado)",
    "2.5.1": "2.5.1 Gestos de Ponteiro",
    "2.5.2": "2.5.2 Cancelamento de Ponteiro",
    "2.5.3": "2.5.3 Rótulo no Nome",
    "2.5.4": "2.5.4 Acionamento por Movimento",
    "2.5.7": "2.5.7 Movimentos de Arraste",
    "2.5.8": "2.5.8 Tamanho do Alvo (Mínimo)",
    # 3. Compreensível
    "3.1.1": "3.1.1 Idioma da Página",
    "3.1.2": "3.1.2 Idioma das Partes",
    "3.1.3": "3.1.3 Palavras Incomuns",
    "3.1.4": "3.1.4 Abreviaturas",
    "3.1.5": "3.1.5 Nível de Leitura",
    "3.2.1": "3.2.1 Ao Receber Foco",
    "3.2.2": "3.2.2 Ao Receber Entrada",
    "3.2.3": "3.2.3 Navegação Consistente",
    "3.2.4": "3.2.4 Identificação Consistente",
    "3.3.1": "3.3.1 Identificação de Erro",
    "3.3.2": "3.3.2 Rótulos ou Instruções",
    "3.3.3": "3.3.3 Sugestão de Erro",
    "3.3.4": "3.3.4 Prevenção de Erros (Jurídicos, Financeiros e Dados)",
    "3.3.7": "3.3.7 Entrada Redundante",
    "3.3.8": "3.3.8 Autenticação Acessível (Mínima)",
    "3.3.9": "3.3.9 Autenticação Acessível (Aprimorada)",
    # 4. Robusto
    "4.1.2": "4.1.2 Nome, Função e Valor",
    "4.1.3": "4.1.3 Mensagens de Status",
}


def _extract_code(criterion: str) -> str:
    """Extrai o código numérico do critério. Ex: '1.1.1 Non-text Content' -> '1.1.1'."""
    if not criterion:
        return ""
    return criterion.split(" ")[0].strip()


def get_guideline_for_code(code: str) -> str:
    """Retorna a diretriz oficial WCAG correspondente ao código numérico."""
    parts = code.split(".")
    if len(parts) >= 2:
        g_key = f"{parts[0]}.{parts[1]}"
        if g_key in _GUIDELINES_PT:
            return _GUIDELINES_PT[g_key]
    return "Diretrizes de Acessibilidade para Conteúdo Web (WCAG 2.2)"


def translate_issue(issue: AccessibilityIssue) -> AccessibilityIssue:
    """
    Preenche criterion_pt e severity_pt em um AccessibilityIssue com acentuação rigorosa.
    """
    code = _extract_code(issue.criterion)
    criterion_pt = _CRITERION_PT.get(code, issue.criterion)
    sev_val = issue.severity.value if hasattr(issue.severity, "value") else str(issue.severity)
    severity_pt = _SEVERITY_PT.get(issue.severity, _SEVERITY_PT.get(sev_val, sev_val.capitalize()))

    return issue.model_copy(
        update={
            "criterion_pt": criterion_pt,
            "severity_pt": severity_pt,
        }
    )


def translate_issues(issues: list[AccessibilityIssue]) -> list[AccessibilityIssue]:
    """Aplica translate_issue em uma lista."""
    return [translate_issue(i) for i in issues]
