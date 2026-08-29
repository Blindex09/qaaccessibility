import logging
import os

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Guarda de escopo pra execucao de comando/edicao de arquivo em diretorios
# LOCAIS do usuario (fora do sandbox do proprio backend).
#
# Pedido explicito do usuario (2026-08-11): a IA pode ler/corrigir projetos
# locais e executar Cypress/Playwright locais, mas SOMENTE dentro de um
# diretorio de projeto de acessibilidade -- identificado pelo NOME do
# diretorio (ou de algum segmento do caminho), nunca por confiar cegamente
# no que o usuario pede. Se o caminho nao tiver essa evidencia no nome, a
# resposta e uma recusa amigavel, mesmo que o usuario insista ou peca
# qualquer coisa fora de teste/correcao de acessibilidade (Cypress, Selenium,
# Playwright, ou os proprios arquivos do projeto de acessibilidade).
#
# Isso NAO e uma blacklist de conteudo/intencao (proibido pelas regras do
# projeto) -- e uma fronteira estrutural sobre ONDE no disco a IA pode agir,
# igual a um usuario Unix so poder escrever no proprio $HOME. A decisao de O
# QUE fazer dentro desse escopo continua livre (nunca palavra-chave
# bloqueando resposta da IA).
# ─────────────────────────────────────────────────────────────────────────────

_ACCESSIBILITY_MARKERS = ("acessibilidade", "acessivel", "acess", "accessibility", "a11y")


def is_accessibility_project_dir(path: str) -> bool:
    """True se algum segmento do caminho (case-insensitive) indicar que o
    diretorio e um projeto de acessibilidade. Unico criterio pelo qual a IA
    tem permissao pra editar arquivos ou rodar Cypress/Playwright locais num
    diretorio do usuario."""
    if not path:
        return False
    normalized = path.replace("\\", "/").lower()
    segments = [s for s in normalized.split("/") if s]
    return any(marker in segment for segment in segments for marker in _ACCESSIBILITY_MARKERS)


def accessibility_scope_denial_message(path: str) -> str:
    """Mensagem amigavel de recusa quando o diretorio esta fora do escopo
    permitido -- devolvida como resultado da tool, nunca uma excecao."""
    display_path = os.path.normpath(path) if path else "(vazio)"
    return (
        f"Não posso executar comandos ou editar arquivos em '{display_path}': "
        "esta ferramenta só age em diretórios de projeto de acessibilidade "
        "(o nome da pasta -- ou de algum nível do caminho -- precisa indicar isso, "
        "ex.: 'acessibilidade', 'accessibility', 'a11y'). "
        "Para testar ou corrigir esse projeto, renomeie a pasta (ou aponte para "
        "uma pasta cujo nome já deixe isso claro) e tente de novo."
    )
