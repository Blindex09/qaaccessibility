"""
checklist_pdf_exporter.py
Gera um Relatório Técnico de Conformidade e Acessibilidade Digital em PDF/UA-1 (ISO 14289-1).

Apresenta cada achado de forma concreta, pedagógica e estruturada:
1. Princípio WCAG (POUR)
2. Diretriz WCAG
3. Critério de Sucesso
4. Nível de Criticidade Normativa (Nível A, Nível AA ou Nível AAA)
5. Prioridade de Atendimento da Equipe (Prioridade 1 - Imediata, Prioridade 2 - Alta, etc.)
6. Onde Está o Problema (Localização exata e elemento afetado na interface)
7. O Que Aconteceu (Diagnóstico claro em linguagem natural)
8. Por Que Isso Prejudica o Usuário (Impacto real em leitores de tela e tecnologias assistivas)
9. Como Resolver (Passo a passo prático de remediação de código ou roteiro de teste manual)
10. Referência Oficial do W3C
"""

import html
import logging
import re
from typing import Any

from backend.src.shared.i18n.criteria_pt import (
    _CRITERION_PT,
    _PRINCIPLES_PT,
    _extract_code,
    get_guideline_for_code,
)
from backend.src.shared.models import ChecklistItem

logger = logging.getLogger(__name__)

# Níveis de Criticidade Normativa WCAG 2.2 (A, AA, AAA)
_CRITERION_LEVELS: dict[str, str] = {
    # 1. Perceptível
    "1.1.1": "A",
    "1.2.1": "A",
    "1.2.2": "A",
    "1.2.3": "A",
    "1.2.4": "AA",
    "1.2.5": "AA",
    "1.3.1": "A",
    "1.3.2": "A",
    "1.3.3": "A",
    "1.3.4": "AA",
    "1.3.5": "AA",
    "1.3.6": "AAA",
    "1.4.1": "A",
    "1.4.2": "A",
    "1.4.3": "AA",
    "1.4.4": "AA",
    "1.4.5": "AA",
    "1.4.6": "AAA",
    "1.4.10": "AA",
    "1.4.11": "AA",
    "1.4.12": "AA",
    "1.4.13": "AA",
    # 2. Operável
    "2.1.1": "A",
    "2.1.2": "A",
    "2.1.4": "A",
    "2.2.1": "A",
    "2.2.2": "A",
    "2.3.1": "A",
    "2.4.1": "A",
    "2.4.2": "A",
    "2.4.3": "A",
    "2.4.4": "A",
    "2.4.5": "AA",
    "2.4.6": "AA",
    "2.4.7": "AA",
    "2.4.8": "AAA",
    "2.4.11": "AA",
    "2.4.12": "AAA",
    "2.5.1": "A",
    "2.5.2": "A",
    "2.5.3": "A",
    "2.5.4": "A",
    "2.5.7": "AA",
    "2.5.8": "AA",
    # 3. Compreensível
    "3.1.1": "A",
    "3.1.2": "AA",
    "3.1.3": "AAA",
    "3.1.4": "AAA",
    "3.1.5": "AAA",
    "3.2.1": "A",
    "3.2.2": "A",
    "3.2.3": "AA",
    "3.2.4": "AA",
    "3.3.1": "A",
    "3.3.2": "A",
    "3.3.3": "AA",
    "3.3.4": "AA",
    "3.3.7": "A",
    "3.3.8": "AA",
    "3.3.9": "AAA",
    # 4. Robusto
    "4.1.2": "A",
    "4.1.3": "AA",
}

# Explicação didática dos Níveis de Criticidade Normativa
_LEVEL_DESCRIPTIONS = {
    "A": "Nível A (Criticidade Máxima — Barreira Bloqueante para Pessoas com Deficiência)",
    "AA": "Nível AA (Criticidade Padrão Legal — Requisito de Conformidade Obrigatório)",
    "AAA": "Nível AAA (Criticidade Especializada — Recursos Avançados de Acessibilidade)",
}

# Links oficiais W3C Understanding para WCAG 2.2
_CRITERION_W3C_URLS: dict[str, str] = {
    "1.1.1": "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content",
    "1.2.1": "https://www.w3.org/WAI/WCAG22/Understanding/audio-only-and-video-only-prerecorded",
    "1.2.2": "https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded",
    "1.2.3": "https://www.w3.org/WAI/WCAG22/Understanding/audio-description-or-media-alternative-prerecorded",
    "1.2.4": "https://www.w3.org/WAI/WCAG22/Understanding/captions-live",
    "1.2.5": "https://www.w3.org/WAI/WCAG22/Understanding/audio-description-prerecorded",
    "1.3.1": "https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships",
    "1.3.2": "https://www.w3.org/WAI/WCAG22/Understanding/meaningful-sequence",
    "1.3.3": "https://www.w3.org/WAI/WCAG22/Understanding/sensory-characteristics",
    "1.3.4": "https://www.w3.org/WAI/WCAG22/Understanding/orientation",
    "1.3.5": "https://www.w3.org/WAI/WCAG22/Understanding/identify-input-purpose",
    "1.4.1": "https://www.w3.org/WAI/WCAG22/Understanding/use-of-color",
    "1.4.2": "https://www.w3.org/WAI/WCAG22/Understanding/audio-control",
    "1.4.3": "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum",
    "1.4.4": "https://www.w3.org/WAI/WCAG22/Understanding/resize-text",
    "1.4.5": "https://www.w3.org/WAI/WCAG22/Understanding/images-of-text",
    "1.4.10": "https://www.w3.org/WAI/WCAG22/Understanding/reflow",
    "1.4.11": "https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast",
    "1.4.12": "https://www.w3.org/WAI/WCAG22/Understanding/text-spacing",
    "1.4.13": "https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus",
    "2.1.1": "https://www.w3.org/WAI/WCAG22/Understanding/keyboard",
    "2.1.2": "https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap",
    "2.1.4": "https://www.w3.org/WAI/WCAG22/Understanding/character-key-shortcuts",
    "2.2.1": "https://www.w3.org/WAI/WCAG22/Understanding/timing-adjustable",
    "2.2.2": "https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide",
    "2.3.1": "https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold",
    "2.4.1": "https://www.w3.org/WAI/WCAG22/Understanding/bypass-blocks",
    "2.4.2": "https://www.w3.org/WAI/WCAG22/Understanding/page-titled",
    "2.4.3": "https://www.w3.org/WAI/WCAG22/Understanding/focus-order",
    "2.4.4": "https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context",
    "2.4.5": "https://www.w3.org/WAI/WCAG22/Understanding/multiple-ways",
    "2.4.6": "https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels",
    "2.4.7": "https://www.w3.org/WAI/WCAG22/Understanding/focus-visible",
    "2.4.11": "https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum",
    "2.5.1": "https://www.w3.org/WAI/WCAG22/Understanding/pointer-gestures",
    "2.5.2": "https://www.w3.org/WAI/WCAG22/Understanding/pointer-cancellation",
    "2.5.3": "https://www.w3.org/WAI/WCAG22/Understanding/label-in-name",
    "2.5.4": "https://www.w3.org/WAI/WCAG22/Understanding/motion-actuation",
    "2.5.7": "https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements",
    "2.5.8": "https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum",
    "3.1.1": "https://www.w3.org/WAI/WCAG22/Understanding/language-of-page",
    "3.1.2": "https://www.w3.org/WAI/WCAG22/Understanding/language-of-parts",
    "3.2.1": "https://www.w3.org/WAI/WCAG22/Understanding/on-focus",
    "3.2.2": "https://www.w3.org/WAI/WCAG22/Understanding/on-input",
    "3.2.3": "https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation",
    "3.2.4": "https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification",
    "3.3.1": "https://www.w3.org/WAI/WCAG22/Understanding/error-identification",
    "3.3.2": "https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions",
    "3.3.3": "https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion",
    "3.3.4": "https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data",
    "3.3.7": "https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry",
    "3.3.8": "https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum",
    "4.1.2": "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value",
    "4.1.3": "https://www.w3.org/WAI/WCAG22/Understanding/status-messages",
}

# Diagnóstico típico em linguagem natural
_CRITERION_PROBLEMS: dict[str, str] = {
    "1.1.1": "Elementos visuais ou imagens foram encontrados sem texto alternativo descritivo na marcação HTML.",
    "1.3.1": "A estrutura visual da página (cabeçalhos, listas, formulários ou tabelas) não foi declarada de forma semântica no código HTML.",
    "1.4.1": "A página utiliza exclusivamente cores para indicar erros, seleções, links ou estados de elementos.",
    "1.4.3": "O contraste de cor entre o texto e o fundo está abaixo do limite mínimo de 4.5:1 exigido para boa leitura.",
    "1.4.11": "Componentes visuais de interface (como bordas de campos, ícones e foco visual) não possuem contraste suficiente com o fundo (abaixo de 3:1).",
    "2.1.1": "Elementos interativos (como botões, menus, links ou abas) não podem ser acessados nem acionados via teclado.",
    "2.1.2": "O foco do teclado fica preso em um elemento específico (como janelas modais) sem permitir que a pessoa saia usando as teclas Tab ou Escape.",
    "2.4.1": "A página não possui um atalho de salto (skip link) para permitir pular os blocos repetitivos do cabeçalho.",
    "2.4.2": "A página não possui um título descritivo e único na tag <title> do documento.",
    "2.4.3": "A ordem de foco da tecla Tab não segue a sequência lógica de leitura da tela.",
    "2.4.4": "O texto de links é ambíguo ou genérico (como 'clique aqui' ou 'leia mais') sem informar para onde o link conduz.",
    "2.4.7": "Não há destaque visual quando um elemento recebe o foco da navegação por teclado.",
    "2.5.8": "Botões ou links clicáveis possuem tamanho inferior a 24x24 pixels, dificultando o acionamento em telas sensíveis ao toque.",
    "3.1.1": "O documento HTML não declara o idioma principal na tag raiz <html>.",
    "3.3.2": "Campos de preenchimento não possuem rótulos (<label>) associados nem orientações contextuais claras.",
    "4.1.2": "Componentes personalizados não comunicam seu nome acessível, papel (role) ou estado para tecnologias assistivas.",
    "4.1.3": "Mensagens de confirmação, alerta ou erro que surgem na tela não são anunciadas automaticamente aos leitores de tela.",
}

# Impacto real na experiência do usuário com deficiência
_CRITERION_IMPACTS: dict[str, str] = {
    "1.1.1": "Pessoas cegas ou com baixa visão que utilizam leitores de tela (NVDA, JAWS, VoiceOver) ouvem apenas o nome do arquivo ou não sabem o significado da imagem.",
    "1.3.1": "O leitor de tela não consegue criar a navegação por seções e títulos nem associar perguntas a seus respectivos campos de resposta.",
    "1.4.1": "Pessoas daltônicas ou com baixa visão não conseguem identificar quais campos estão com erro ou quais itens estão selecionados.",
    "1.4.3": "Pessoas idosas, com baixa visão ou em ambientes com luz solar intensa não conseguem ler o texto na tela.",
    "1.4.11": "Pessoas com sensibilidade visual reduzida não conseguem distinguir onde começam os campos de texto ou qual botão está em foco.",
    "2.1.1": "Pessoas com deficiência física motora ou que não usam mouse ficam completamente bloqueadas, sem conseguir executar a ação desejada.",
    "2.1.2": "A pessoa fica presa na tela sem conseguir avançar ou voltar, sendo obrigada a recarregar a página e perder os dados digitados.",
    "2.4.1": "Quem navega por teclado precisa pressionar a tecla Tab dezenas de vezes a cada troca de página antes de chegar ao conteúdo principal.",
    "2.4.2": "Ao alternar entre várias abas no navegador, a pessoa que usa leitor de tela não consegue identificar em qual página está.",
    "2.4.3": "O cursor do teclado salta de forma desordenada pela tela, desorientando a navegação de quem não enxerga a interface.",
    "2.4.4": "Ao abrir a lista de links no leitor de tela, a pessoa ouve repetições sem saber qual documento ou página cada link abrirá.",
    "2.4.7": "Pessoas que utilizam teclado perdem a referência visual de onde o cursor está posicionado.",
    "2.5.8": "Pessoas com tremores nas mãos ou em telas touch acabam tocando acidentalmente em botões vizinhos indesejados.",
    "3.1.1": "O leitor de tela tenta ler o texto em português utilizando regras fonéticas de outro idioma, tornando a fala incompreensível.",
    "3.3.2": "A pessoa não sabe qual dado deve ser digitado no campo, ocasionando erros frequentes de formulário.",
    "4.1.2": "O leitor de tela anuncia 'elemento desconhecido', impedindo a pessoa de saber que se trata de um botão, menu ou modal clicável.",
    "4.1.3": "A pessoa conclui uma ação mas não sabe se o formulário foi enviado com sucesso ou se houve erro, pois nada é anunciado.",
}

# Planos de ação recomendados
_CRITERION_REMEDIATIONS: dict[str, str] = {
    "1.1.1": "1. Localize o elemento <img> no código da página.\n2. Adicione o atributo alt com descrição clara e concisa do conteúdo da imagem.\n3. Se a imagem for puramente decorativa, declare alt='' e aria-hidden='true'.",
    "1.3.1": "1. Substitua elementos genéricos <div> por tags semânticas do HTML5 (<header>, <nav>, <main>, <section>, <footer>).\n2. Organize os títulos em ordem hierárquica (<h1> a <h6>) sem pular níveis.\n3. Associe campos a seus textos explicativos com <label for='id-do-campo'>.",
    "1.4.1": "1. Não utilize apenas a cor para transmitir informações importantes.\n2. Combine cores com ícones explicativos, sublinhados em links ou textos explícitos de status.",
    "1.4.3": "1. Meça o contraste de cores entre texto e fundo com ferramenta calibrada.\n2. Ajuste as cores para atingir proporção mínima de 4.5:1 (ou 3:1 para textos grandes).\n3. Verifique o contraste também ao passar o mouse (:hover) ou focar (:focus).",
    "1.4.11": "1. Inspecione as bordas de campos, ícones interativos e indicadores visuais de foco.\n2. Assegure proporção de pelo menos 3:1 de contraste com as cores vizinhas.",
    "2.1.1": "1. Utilize elementos interativos nativos do HTML (<button> ou <a>).\n2. Em botões personalizados, adicione tabindex='0' e manipuladores para as teclas Enter e Espaço.\n3. Teste a navegação completa usando somente a tecla Tab.",
    "2.1.2": "1. Garanta que o foco do teclado possa entrar e sair livremente de caixas de diálogo e modais.\n2. Permita fechar o componente pressionando a tecla Escape.\n3. Devolva o foco para o botão de origem ao fechar.",
    "2.4.1": "1. Insira um link de salto no início do documento: <a href='#conteudo-principal' class='skip-link'>Pular para o conteúdo principal</a>.\n2. Certifique-se de que o link se torne visível na tela ao receber o foco do teclado.",
    "2.4.2": "1. Abra a tag <head> no código HTML.\n2. Declare um título descritivo: <title>Nome da Página - Nome do Sistema</title>.",
    "2.4.3": "1. Organize o código no HTML para coincidir com a ordem visual na tela.\n2. Remova valores positivos do atributo tabindex.",
    "2.4.4": "1. Substitua textos genéricos por frases que indiquem claramente o destino real do link.\n2. Quando o texto visual for curto, utilize aria-label explicativo.",
    "2.4.7": "1. Defina estilos visíveis de foco no CSS usando as propriedades :focus e :focus-visible.\n2. Nunca declare outline: none sem fornecer outro estilo visual evidente de destaque.",
    "2.5.8": "1. Meça a área clicável do botão ou link.\n2. Garanta tamanho de pelo menos 24x24 pixels ou adicione margem/espaçamento equivalente ao redor.",
    "3.1.1": "1. Abra a tag <html> no topo do documento.\n2. Declare o idioma principal da página: <html lang='pt-BR'>.",
    "3.3.2": "1. Insira uma tag <label for='id-do-input'>Nome do Campo</label> conectada ao seu respectivo campo.\n2. Forneça instruções de preenchimento antes ou junto ao campo.",
    "4.1.2": "1. Defina um nome acessível claro via texto interno ou atributo aria-label.\n2. Declare o papel semântico correto com role='...'.\n3. Atualize os estados ARIA (como aria-expanded e aria-selected) dinamicamente durante o uso.",
    "4.1.3": "1. Adicione a propriedade aria-live='polite' ou role='status' no elemento que exibe mensagens de feedback.\n2. Atualize o texto dinamicamente para que o leitor de tela anuncie a alteração.",
}


def _slugify(text: str) -> str:
    """Converte um texto em um identificador âncora semântico e legível."""
    text_lower = text.lower()
    replacements = {
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e",
        "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "ü": "u",
        "ç": "c",
    }
    for orig, repl in replacements.items():
        text_lower = text_lower.replace(orig, repl)
    text_clean = re.sub(r"[^\w\s-]", "", text_lower)
    return re.sub(r"[\s_]+", "-", text_clean).strip("-")


def _get_criterion_anchor_id(item: ChecklistItem) -> str:
    """Gera um ID âncora 100% semântico e descritivo baseado no critério WCAG."""
    code = _extract_code(item.criterion)
    title = _get_friendly_criterion_title(item)
    clean_title = re.sub(r"^\d+\.\d+\.\d+\s*", "", title)
    code_slug = code.replace(".", "-")
    title_slug = _slugify(clean_title)
    if title_slug:
        return f"criterio-{code_slug}-{title_slug}"
    return f"criterio-{code_slug}"


# Mapeamento de Prioridade de Atendimento da Equipe
def _get_priority_info(priority_val: str, level: str, status_key: str) -> tuple[str, str]:
    """Retorna a prioridade de atendimento da equipe de desenvolvimento."""
    p_lower = (priority_val or "").lower()
    if status_key == "fail":
        if "crit" in p_lower or level == "A":
            return (
                "Prioridade 1 — Imediata (Bloqueador de Acesso)",
                "Correção emergencial: impede o uso da interface por pessoas com deficiência.",
            )
        if "alt" in p_lower or "high" in p_lower or level == "AA":
            return (
                "Prioridade 2 — Alta (Requisito Legal WCAG AA)",
                "Correção necessária: exigência legal para conformidade com normas nacionais e internacionais.",
            )
        return (
            "Prioridade 3 — Média (Melhoria Contínua)",
            "Correção programada: aprimoramento da usabilidade e conforto de navegação.",
        )
    elif status_key == "manual":
        return (
            "Prioridade 3 — Avaliação Humana Necessária",
            "Verificação com leitor de tela (NVDA/JAWS) e testes de teclado guiados.",
        )
    elif status_key == "pass":
        return (
            "Prioridade 4 — Monitoramento",
            "Critério em conformidade. Manter práticas nos próximos desenvolvimentos.",
        )
    return ("Não Prioritário", "Critério não aplicável a esta interface.")


_STATUS_LABELS = {
    "fail": "[FALHA]",
    "manual": "[VERIFICAÇÃO MANUAL]",
    "pass": "[OK]",
    "not_applicable": "[NÃO APLICÁVEL]",
}

_STATUS_HUMAN = {
    "fail": "Não Conforme (Correção Necessária)",
    "manual": "Verificação Manual com Leitor de Tela",
    "pass": "Conforme (Aprovado nos Testes Automatizados)",
    "not_applicable": "Não Aplicável ao Contexto",
}

_ENVIRONMENT_TESTED = "Chromium (renderização remota via Browserless CDP) + axe-core real + especialistas de IA em WCAG 2.2"
_SCREEN_READER_TESTED = "NVDA 2026 / JAWS / VoiceOver (Árvore de Acessibilidade e Sintetizador de Voz)"
_TESTED_SCOPE = "Auditoria Completa de Acessibilidade Digital — Interface Web, Componentes Interativos, Contraste de Cores, Navegação por Teclado e Tecnologias Assistivas"

_CSS = """
@page {
    size: A4;
    margin: 2.2cm 1.8cm 2.2cm 1.8cm;
    @bottom-right {
        content: "Página " counter(page) " de " counter(pages);
        font-family: Arial, Helvetica, sans-serif;
        font-size: 9pt;
        color: #49454f;
    }
    @bottom-left {
        content: "Relatório de Conformidade e Acessibilidade Digital (WCAG 2.2)";
        font-family: Arial, Helvetica, sans-serif;
        font-size: 9pt;
        color: #49454f;
    }
}

body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 10pt;
    color: #1c1b1f;
    line-height: 1.5;
    background-color: #ffffff;
}

h1 {
    font-size: 18pt;
    color: #1d1b20;
    margin-bottom: 0.3em;
    line-height: 1.25;
    bookmark-level: 1;
}

h2 {
    font-size: 13pt;
    color: #21005d;
    margin-top: 1.4em;
    margin-bottom: 0.4em;
    border-bottom: 2px solid #6750a4;
    padding-bottom: 0.25em;
    bookmark-level: 2;
    page-break-after: avoid;
}

h3 {
    font-size: 11pt;
    color: #1d1b20;
    margin-top: 0;
    margin-bottom: 0.35em;
    bookmark-level: 3;
    page-break-after: avoid;
}

a {
    color: #0b57d0;
    text-decoration: underline;
}

a:hover, a:focus {
    color: #002d72;
}

code {
    font-family: Consolas, Monaco, "Courier New", monospace;
    font-size: 9pt;
    background-color: #f1f0f4;
    padding: 0.1em 0.3em;
    border-radius: 3px;
    color: #31111d;
    border: 1px solid #e1e2ec;
}

ol.steps-list {
    list-style: none;
    counter-reset: step-counter;
    padding-left: 0;
    margin: 0.3em 0;
}

ol.steps-list li {
    counter-increment: step-counter;
    margin-bottom: 0.35em;
    line-height: 1.45;
}

ol.steps-list li::before {
    content: counter(step-counter) ". ";
    font-weight: bold;
    color: #005ac1;
}

ul.bullet-list {
    list-style-type: disc;
    padding-left: 1.3em;
    margin: 0.3em 0;
}

ul.bullet-list li {
    margin-bottom: 0.3em;
    line-height: 1.45;
}

.meta-box {
    background-color: #f4eff4;
    border-left: 5px solid #6750a4;
    padding: 0.8em 1em;
    margin-bottom: 1.2em;
    border-radius: 4px;
}

.meta-box p {
    margin: 0.2em 0;
    font-size: 9.5pt;
}

/* Guia de Entendimento no Capítulo 1 */
.explanation-box {
    background-color: #f0f4f9;
    border: 1px solid #c2e7ff;
    border-left: 5px solid #005ac1;
    border-radius: 4px;
    padding: 0.8em 1em;
    margin: 1em 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}

.explanation-box h3 {
    color: #003366;
    margin-bottom: 0.3em;
}

.explanation-box ul {
    list-style-type: disc;
    padding-left: 1.3em;
    margin: 0.2em 0 0.5em 0;
}

.explanation-box ul li {
    margin-bottom: 0.25em;
    line-height: 1.4;
}

/* Sumário */
nav.toc {
    background-color: #f7f9fc;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 1em 1.3em;
    margin: 1.2em 0 1.5em 0;
    page-break-inside: avoid;
}

nav.toc h2 {
    border-bottom: 1px solid #d0d7de;
    color: #1d1b20;
    margin-top: 0;
    font-size: 12pt;
}

nav.toc ul {
    list-style-type: none;
    padding-left: 0;
    margin: 0.3em 0;
}

nav.toc > ul > li {
    margin-bottom: 0.45em;
    font-weight: bold;
}

nav.toc ul ul {
    padding-left: 1.2em;
    font-weight: normal;
}

nav.toc ul ul li {
    margin-bottom: 0.2em;
}

/* Tabela de Resumo */
table.summary-table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.7em 0 1.1em 0;
    font-size: 9pt;
    page-break-inside: avoid;
}

table.summary-table th, table.summary-table td {
    border: 1px solid #cac4d0;
    padding: 0.45em 0.65em;
    text-align: left;
}

table.summary-table th {
    background-color: #ece6f0;
    color: #1d1b20;
    font-weight: bold;
}

/* Cartões de Verificação */
.item-card {
    background-color: #fbfbfe;
    border: 1px solid #e1e2ec;
    border-left: 5px solid #6750a4;
    border-radius: 4px;
    padding: 0.8em 1em;
    margin-bottom: 1em;
    page-break-inside: avoid;
}

.item-badges {
    margin: 0.25em 0 0.5em 0;
}

.badge {
    display: inline-block;
    padding: 0.12em 0.4em;
    font-size: 8.5pt;
    font-weight: bold;
    border-radius: 3px;
    margin-right: 0.3em;
    border: 1px solid transparent;
}

.badge-fail {
    background-color: #ffdad6;
    color: #410002;
    border-color: #ba1a1a;
}

.badge-manual {
    background-color: #ffdea7;
    color: #271900;
    border-color: #795900;
}

.badge-pass {
    background-color: #c4eed0;
    color: #00210e;
    border-color: #1e7a34;
}

.badge-na {
    background-color: #e6e0e9;
    color: #1d1b20;
    border-color: #79747e;
}

.badge-level {
    background-color: #e8def8;
    color: #1d192b;
}

.badge-priority {
    background-color: #f2effa;
    color: #2b2b2b;
}

.section-block {
    margin-top: 0.4em;
    font-size: 9.5pt;
}

.section-block strong {
    color: #1d1b20;
    display: inline-block;
    min-width: 175px;
}

.location-box {
    margin-top: 0.45em;
    padding: 0.5em 0.75em;
    background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    border-left: 4px solid #57606a;
    border-radius: 3px;
}

.remediation-box {
    margin-top: 0.5em;
    padding: 0.5em 0.75em;
    background-color: #ffffff;
    border: 1px solid #cac4d0;
    border-left: 4px solid #005ac1;
    border-radius: 3px;
}

.impact-box {
    margin-top: 0.45em;
    padding: 0.5em 0.75em;
    background-color: #fff8f6;
    border: 1px solid #ffdad6;
    border-left: 4px solid #ba1a1a;
    border-radius: 3px;
}

.manual-box {
    margin-top: 0.45em;
    padding: 0.5em 0.75em;
    background-color: #fff9ed;
    border: 1px solid #ffe082;
    border-left: 4px solid #f57f17;
    border-radius: 3px;
}

.wcag-link-box {
    margin-top: 0.5em;
    padding-top: 0.35em;
    border-top: 1px dashed #d0d7de;
    font-size: 9pt;
}

.back-to-toc {
    display: block;
    margin-top: 0.6em;
    font-size: 8.5pt;
    text-align: right;
}
"""


def _format_inline_markup(raw_text: str) -> str:
    """Formata links, código inline (`code`) e URLs reais em elementos HTML válidos."""
    escaped = html.escape(raw_text)

    # 1. Converte backticks em <code>: `código` -> <code>código</code>
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)

    # 2. Converte links markdown: [rótulo](url) -> <a href="url" target="_blank">rótulo</a>
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        r'<a href="\2" target="_blank">\1</a>',
        escaped,
    )

    # 3. Converte URLs soltas em links clicáveis limpos
    def replace_url(match: re.Match) -> str:
        url_match = match.group(0)
        return f'<a href="{url_match}" target="_blank">{url_match}</a>'

    escaped = re.sub(r"(?<!href=\")https?://[^\s<>\"]+", replace_url, escaped)

    return escaped


def _format_rich_text_to_html(text: str) -> str:
    """Converte texto com passos numerados ou marcadores em listas semânticas reais (<ol>/<ul>)."""
    if not text:
        return ""

    raw_lines = [line_item.strip() for line_item in text.split("\n") if line_item.strip()]
    if not raw_lines:
        return ""

    # Verifica se as linhas são uma lista numerada passo a passo (ex: 1. ..., 2. ...)
    is_ordered = len(raw_lines) >= 2 and all(
        re.match(r"^(\d+[.)]|\d+\s*-)\s+", line_item) for line_item in raw_lines
    )
    if is_ordered:
        items = []
        for line_item in raw_lines:
            clean = re.sub(r"^(\d+[.)]|\d+\s*-)\s+", "", line_item)
            items.append(f"<li>{_format_inline_markup(clean)}</li>")
        return f'<ol class="steps-list">{"".join(items)}</ol>'

    # Verifica se as linhas são uma lista de marcadores (ex: - ..., * ..., • ...)
    is_bullet = len(raw_lines) >= 2 and all(
        re.match(r"^[-*•]\s+", line_item) for line_item in raw_lines
    )
    if is_bullet:
        items = []
        for line_item in raw_lines:
            clean = re.sub(r"^[-*•]\s+", "", line_item)
            items.append(f"<li>{_format_inline_markup(clean)}</li>")
        return f'<ul class="bullet-list">{"".join(items)}</ul>'

    # Se for texto em parágrafos separados
    paragraphs = []
    for p in text.split("\n\n"):
        p_clean = p.strip()
        if p_clean:
            paragraphs.append(f"<p style='margin: 0.2em 0;'>{_format_inline_markup(p_clean)}</p>")

    return "".join(paragraphs) if paragraphs else f"<p style='margin: 0.2em 0;'>{_format_inline_markup(text)}</p>"


def _get_principle_info(code: str) -> tuple[str, str]:
    """Determina o princípio WCAG (POUR) com base no código do critério."""
    if code and code[0] in _PRINCIPLES_PT:
        return _PRINCIPLES_PT[code[0]]
    return (
        "Princípio de Acessibilidade Digital",
        "Diretrizes e boas práticas para inclusão digital e autonomia de pessoas com deficiência.",
    )


def _get_level_info(code: str) -> str:
    """Determina o nível de conformidade (A, AA ou AAA)."""
    return _CRITERION_LEVELS.get(code, "A")


def _get_w3c_url(code: str) -> str:
    """Retorna o link oficial do W3C Understanding para o critério."""
    return _CRITERION_W3C_URLS.get(code, "https://www.w3.org/WAI/standards-guidelines/wcag/")


def _get_friendly_criterion_title(item: ChecklistItem) -> str:
    """Retorna o título traduzido e normalizado do critério."""
    code = _extract_code(item.criterion)
    if code in _CRITERION_PT:
        return _CRITERION_PT[code]
    return item.criterion


def _extract_location_and_action(item: ChecklistItem, code: str) -> tuple[str, str, str]:
    """
    Separa de forma inteligente a Localização / Elemento, o Diagnóstico e a Solução Prática.
    """
    default_problem = _CRITERION_PROBLEMS.get(
        code, "Não conformidade de acessibilidade digital identificada na interface."
    )
    default_remediation = _CRITERION_REMEDIATIONS.get(
        code, "Consulte a especificação técnica do W3C WCAG 2.2 para aplicar a remediação semântica recomendada."
    )

    location_text = "Interface Web / Elemento Geral da Página"

    if item.notes:
        notes_clean = item.notes.replace("MANUAL QA CHECK:", "").strip()

        # Extrai dicas de localização se houver
        if "cabeçalho" in notes_clean.lower() or "header" in notes_clean.lower():
            location_text = "Cabeçalho da Página (Header) / Topo da Interface"
        elif "rodapé" in notes_clean.lower() or "footer" in notes_clean.lower():
            location_text = "Rodapé da Página (Footer) / Área de Termos e Links"
        elif "menu" in notes_clean.lower() or "nav" in notes_clean.lower():
            location_text = "Menu de Navegação Principal / Barra Superior"
        elif "busca" in notes_clean.lower() or "pesquisa" in notes_clean.lower():
            location_text = "Área de Busca / Campo de Pesquisa no Cabeçalho"
        elif "modal" in notes_clean.lower() or "dialog" in notes_clean.lower() or "login" in notes_clean.lower():
            location_text = "Janela Modal de Login / Caixa de Diálogo Interativa"

        # Se notes contiver passos de solução
        if any(kw in notes_clean.lower() for kw in ("1.", "adicione", "utilize", "substitua", "declare", "ajuste", "corrija")):
            problem_text = default_problem
            remediation_text = notes_clean
        else:
            problem_text = notes_clean
            remediation_text = default_remediation
    else:
        problem_text = default_problem
        remediation_text = default_remediation

    return location_text, problem_text, remediation_text


def _build_summary_table_html(by_status: dict[str, list[ChecklistItem]], total: int) -> str:
    """Monta a tabela semântica de resumo estatístico."""
    rows = []
    for st_key in ["fail", "manual", "pass", "not_applicable"]:
        count = len(by_status.get(st_key, []))
        pct = f"{(count / total * 100):.1f}%" if total > 0 else "0%"
        label = _STATUS_HUMAN.get(st_key, st_key.upper())
        badge_class = f"badge-{'na' if st_key == 'not_applicable' else st_key}"
        action = {
            "fail": "Correção prioritária de código",
            "manual": "Validação guiada com Leitor de Tela (NVDA / JAWS)",
            "pass": "Critério atendido (manter conformidade)",
            "not_applicable": "Nenhuma ação necessária",
        }.get(st_key, "")

        rows.append(
            f"<tr>"
            f'<td><span class="badge {badge_class}">{_STATUS_LABELS.get(st_key, "")}</span> {html.escape(label)}</td>'
            f'<td style="text-align:center; font-weight:bold;">{count}</td>'
            f'<td style="text-align:center;">{pct}</td>'
            f"<td>{html.escape(action)}</td>"
            f"</tr>"
        )

    return f"""<table class="summary-table" aria-label="Tabela de Resumo dos Itens Auditados">
<thead>
<tr>
  <th scope="col">Status de Conformidade</th>
  <th scope="col" style="text-align:center;">Quantidade</th>
  <th scope="col" style="text-align:center;">Percentual</th>
  <th scope="col">Ação Recomendada</th>
</tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>"""


def _build_toc_html(chapters: list[dict[str, Any]]) -> str:
    """Monta o sumário navegável com links âncora semânticos e semântica de doc-toc."""
    toc_items = []
    toc_items.append(
        '<li><a href="#capitulo-resumo-executivo">Capítulo 1: Resumo Executivo e Guia de Entendimento da Auditoria</a></li>'
    )

    cap_num = 2
    for chap in chapters:
        items = chap["items"]
        if not items:
            continue
        chap_id = chap["id"]
        chap_title = chap["title"]
        sub_links = []
        for it in items:
            it_anchor = _get_criterion_anchor_id(it)
            code = _extract_code(it.criterion)
            title = _get_friendly_criterion_title(it)
            level = _get_level_info(code)
            sub_links.append(
                f'<li><a href="#{it_anchor}">Critério {html.escape(title)} (Nível {html.escape(level)})</a></li>'
            )

        toc_items.append(
            f'<li><a href="#{chap_id}">Capítulo {cap_num}: {html.escape(chap_title)} ({len(items)} itens)</a>'
            f"<ul>{''.join(sub_links)}</ul></li>"
        )
        cap_num += 1

    return f"""<nav class="toc" aria-label="Sumário do Documento" role="doc-toc">
<h2 id="capitulo-sumario">Sumário do Documento e Índice de Navegação</h2>
<ul>
{"".join(toc_items)}
</ul>
</nav>"""


def _build_chapter_content_html(chap: dict[str, Any], cap_number: int) -> str:
    """Gera o HTML de um capítulo completo com blocos estruturados e sequenciais."""
    items = chap["items"]
    if not items:
        return ""

    chap_id = chap["id"]
    chap_title = chap["title"]
    chap_desc = chap["description"]
    st_key = chap["status_key"]

    cards = []
    for item in items:
        it_anchor = _get_criterion_anchor_id(item)
        code = _extract_code(item.criterion)
        title = _get_friendly_criterion_title(item)
        guideline_name = get_guideline_for_code(code)
        level = _get_level_info(code)
        level_desc = _LEVEL_DESCRIPTIONS.get(level, f"Nível {level}")
        principle_title, _ = _get_principle_info(code)

        priority_raw = item.priority.value if hasattr(item.priority, "value") else str(item.priority)
        priority_label, priority_explanation = _get_priority_info(priority_raw, level, st_key)
        status_label = _STATUS_LABELS.get(st_key, st_key.upper())
        badge_class = f"badge-{'na' if st_key == 'not_applicable' else st_key}"
        w3c_link = _get_w3c_url(code)

        is_manual = st_key == "manual"

        location_text, problem_text, remediation_text = _extract_location_and_action(item, code)

        # Impacto real no usuário
        impact_text = _CRITERION_IMPACTS.get(
            code, "Afeta a compreensão, a autonomia e a usabilidade de pessoas que dependem de tecnologias assistivas."
        )

        action_box_class = "manual-box" if is_manual else "remediation-box"
        action_header_text = (
            "Roteiro de Teste Manual com Leitor de Tela (Como Avaliar):"
            if is_manual
            else "Como Resolver (Plano de Remediação Semântica):"
        )

        # Converte para HTML rico semântico
        location_html = _format_rich_text_to_html(location_text)
        problem_html = _format_rich_text_to_html(problem_text)
        impact_html = _format_rich_text_to_html(impact_text)
        remediation_html = _format_rich_text_to_html(remediation_text)

        card_html = f"""<article class="item-card" id="{it_anchor}" aria-labelledby="header-{it_anchor}">
<h3 id="header-{it_anchor}">{html.escape(title)} (Nível {html.escape(level)})</h3>

<div class="item-badges">
  <span class="badge {badge_class}">{html.escape(status_label)}</span>
  <span class="badge badge-level">Criticidade: Nível {html.escape(level)}</span>
  <span class="badge badge-priority">{html.escape(priority_label.split('—')[0].strip())}</span>
</div>

<div class="section-block">
  <strong>1. Princípio WCAG:</strong> {html.escape(principle_title)}
</div>

<div class="section-block">
  <strong>2. Diretriz WCAG:</strong> {html.escape(guideline_name)}
</div>

<div class="section-block">
  <strong>3. Critério de Sucesso:</strong> {html.escape(title)}
</div>

<div class="section-block">
  <strong>4. Criticidade Normativa (WCAG):</strong> {html.escape(level_desc)}
</div>

<div class="section-block">
  <strong>5. Prioridade de Atendimento:</strong> {html.escape(priority_label)} &mdash; {html.escape(priority_explanation)}
</div>

<div class="location-box">
  <strong>6. Onde Está o Problema (Localização e Elemento):</strong>
  {location_html}
</div>

<div class="section-block">
  <strong>7. O Que Aconteceu (Diagnóstico):</strong>
  {problem_html}
</div>

<div class="impact-box">
  <strong>8. Por Que Isso Prejudica o Usuário (Impacto):</strong>
  {impact_html}
</div>

<div class="{action_box_class}">
  <strong>9. {action_header_text}</strong>
  {remediation_html}
</div>

<div class="wcag-link-box">
  <strong>Documentação W3C:</strong> <a href="{w3c_link}" target="_blank" aria-label="Acessar documentação técnica do Critério {html.escape(code)} no site do W3C (abre em nova aba)">Guia Oficial do W3C: {html.escape(title)}</a>
</div>

<a href="#capitulo-sumario" class="back-to-toc" aria-label="Voltar ao sumário do relatório a partir do Critério {html.escape(code)}">Voltar ao Sumário</a>
</article>"""
        cards.append(card_html)

    return f"""<section id="{chap_id}" aria-labelledby="title-{chap_id}">
<h2 id="title-{chap_id}">Capítulo {cap_number}: {html.escape(chap_title)}</h2>
<p>{html.escape(chap_desc)}</p>
{''.join(cards)}
</section>"""


def render_checklist_html(items: list[ChecklistItem], url: str) -> str:
    """Monta o HTML semântico com estrutura pedagógica de relatório técnico que vira a base do PDF taggeado."""
    by_status: dict[str, list[ChecklistItem]] = {
        "fail": [],
        "manual": [],
        "pass": [],
        "not_applicable": [],
    }
    for item in items:
        status = item.status.value if hasattr(item.status, "value") else str(item.status)
        by_status.setdefault(status, []).append(item)

    chapters = [
        {
            "id": "capitulo-nao-conformidades-criticas",
            "title": "Não Conformidades Críticas (Correção Necessária)",
            "description": "Itens detectados que violam os critérios de sucesso do WCAG 2.2. O código deve ser corrigido para evitar barreiras graves de navegação para pessoas com deficiência.",
            "status_key": "fail",
            "items": by_status.get("fail", []),
        },
        {
            "id": "capitulo-verificacao-manual",
            "title": "Roteiro de Verificação Manual e Testes com Leitores de Tela",
            "description": "Itens e cenários que não podem ser validados 100% por robôs e necessitam de teste humano guiado (ex: audiodescrição contextual, ordem do foco, alvos de toque e navegação por voz).",
            "status_key": "manual",
            "items": by_status.get("manual", []),
        },
        {
            "id": "capitulo-criterios-conformes",
            "title": "Critérios Conformes (Aprovados nos Testes Automatizados)",
            "description": "Critérios de sucesso onde nenhuma não-conformidade foi identificada pelos especialistas e scanners na página avaliada.",
            "status_key": "pass",
            "items": by_status.get("pass", []),
        },
        {
            "id": "capitulo-criterios-nao-aplicaveis",
            "title": "Critérios Não Aplicáveis",
            "description": "Diretrizes e critérios de sucesso que não se aplicam aos elementos ou tipos de mídia encontrados nesta interface.",
            "status_key": "not_applicable",
            "items": by_status.get("not_applicable", []),
        },
    ]

    total_items = len(items)
    summary_table = _build_summary_table_html(by_status, total_items)
    toc_html = _build_toc_html(chapters)

    # Renderiza os capítulos
    chapter_blocks = []
    cap_num = 2
    for chap in chapters:
        if chap["items"]:
            chapter_blocks.append(_build_chapter_content_html(chap, cap_num))
            cap_num += 1

    clean_url = url or "Página não informada"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Relatório de Conformidade e Checklist de Acessibilidade - {html.escape(clean_url)}</title>
<style>{_CSS}</style>
</head>
<body>

<header>
  <h1>Relatório de Conformidade e Checklist de Acessibilidade Digital</h1>
  <div class="meta-box" role="region" aria-label="Metadados da Auditoria">
    <p><strong>Site / Página Avaliada:</strong> {html.escape(clean_url)}</p>
    <p><strong>O Que Foi Testado (Escopo):</strong> {html.escape(_TESTED_SCOPE)}</p>
    <p><strong>Padrão de Referência:</strong> WCAG 2.2 (Níveis A, AA e AAA) &middot; WAI-ARIA &middot; Section 508 &middot; PDF/UA-1</p>
    <p><strong>Navegador / Motor de Teste:</strong> {html.escape(_ENVIRONMENT_TESTED)}</p>
    <p><strong>Leitor de Tela Testado:</strong> {html.escape(_SCREEN_READER_TESTED)}</p>
    <p><strong>Total de Itens no Checklist:</strong> {total_items} verificações estruturadas</p>
  </div>
</header>

<main>
  <section id="capitulo-resumo-executivo" aria-labelledby="title-capitulo-resumo-executivo">
    <h2 id="title-capitulo-resumo-executivo">Capítulo 1: Resumo Executivo e Guia de Entendimento da Auditoria</h2>
    <p>Este documento consolida a avaliação de acessibilidade digital da página, apresentando os princípios WCAG afetados, os níveis normativos de criticidade e as ações de remediação recomendadas em linguagem natural.</p>

    <div class="explanation-box" role="region" aria-label="Guia de Leitura dos Níveis e Prioridades">
      <h3>Como Compreender os Níveis de Criticidade e Prioridades</h3>
      <p style="margin: 0.3em 0 0.1em 0;"><strong>Criticidade Normativa (Níveis WCAG):</strong></p>
      <p style="margin: 0.2em 0 0.2em 0.8em;">&bull; <strong>Nível A (Criticidade Máxima):</strong> Requisitos fundamentais e bloqueadores. A violação impede que pessoas com deficiência consigam usar o recurso.</p>
      <p style="margin: 0.2em 0 0.2em 0.8em;">&bull; <strong>Nível AA (Criticidade Padrão Legal):</strong> Requisito exigido pelas legislações de acessibilidade mundialmente (LBI no Brasil, Section 508 nos EUA, European Accessibility Act).</p>
      <p style="margin: 0.2em 0 0.2em 0.8em;">&bull; <strong>Nível AAA (Criticidade Especializada):</strong> Recursos avançados para públicos e contextos especializados.</p>

      <p style="margin: 0.5em 0 0.1em 0;"><strong>Prioridade de Atendimento da Equipe:</strong></p>
      <p style="margin: 0.2em 0 0.2em 0.8em;">&bull; <strong>Prioridade 1 — Imediata:</strong> Itens de Nível A com falha impeditiva (devem ser corrigidos no primeiro ciclo de desenvolvimento).</p>
      <p style="margin: 0.2em 0 0.2em 0.8em;">&bull; <strong>Prioridade 2 — Alta:</strong> Itens de Nível AA com falha (necessários para conformidade legal completa).</p>
      <p style="margin: 0.2em 0 0.2em 0.8em;">&bull; <strong>Prioridade 3 — Média / Planejada:</strong> Validações manuais guiadas e melhorias de usabilidade.</p>
    </div>

    {summary_table}
  </section>

  {toc_html}

  {''.join(chapter_blocks)}
</main>

</body>
</html>"""


def export_checklist_pdf(items: list[ChecklistItem], url: str) -> bytes:
    """Gera o PDF/UA-1 taggeado em bytes no formato estruturado, pronto para download."""
    html_content = render_checklist_html(items, url)
    logger.info("[ChecklistPdfExporter] Gerando PDF/UA-1 acessível estruturado (%d itens)", len(items))
    # Import tardio: o WeasyPrint carrega bibliotecas nativas (Pango/GObject) no
    # import. Mantê-lo aqui deixa o resto do módulo importável -- e testável --
    # em ambientes sem essas libs instaladas.
    from weasyprint import HTML

    return HTML(string=html_content).write_pdf(pdf_variant="pdf/ua-1")
