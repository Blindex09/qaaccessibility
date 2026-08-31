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
# diretorio apontado, nunca por confiar cegamente no que o usuario pede. Se o
# nome nao tiver essa evidencia, a
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

# "acess" cobre a grafia PT (acessibilidade, acessivel, acessible...) e "access"
# cobre a EN (accessibility, accessible, access-audit...). Faltava a segunda:
# ate 2026-08-30 a lista tinha "acess" mas nao "access", entao um diretorio
# chamado `ACCESS-portal` ou `accessibility-audit` era RECUSADO -- "acess"
# (1 c) nao e substring de "access" (2 c). Como o criterio e o NOME do
# diretorio, e ele que precisa cobrir as duas grafias que o usuario de fato usa.
_ACCESSIBILITY_MARKERS = ("acess", "access", "a11y")


def is_accessibility_project_dir(path: str) -> bool:
    r"""True se o NOME DO DIRETORIO APONTADO indicar um projeto de
    acessibilidade. Unico criterio pelo qual a IA tem permissao pra editar
    arquivos ou rodar Cypress/Playwright locais num diretorio do usuario.

    So o ultimo segmento conta, e essa restricao e deliberada. Ate 2026-08-31
    qualquer segmento do caminho servia, e isso abria um buraco largo: um
    diretorio ancestral -- pasta de usuario, nome de workspace, rotulo de drive
    -- com "access" no nome liberava TODO projeto abaixo dele. Concreto e
    medido: `...\claude\C--qaaccessibility\...\projeto-comum` passava pelo
    guarda por causa de `C--qaaccessibility`, e o mesmo valeria para
    `C:\Users\accessibility-team\projetos\loja-de-sapatos`.

    Num guarda de blast radius para ESCRITA EM DISCO, o modo de falha caro e
    liberar demais, nao barrar demais: quem trabalha num monorepo aponta para a
    raiz (que tem o marcador) ou renomeia a pasta, e o custo disso e uma
    mensagem de recusa -- nao um computador inteiro aberto.
    """
    if not path:
        return False
    normalized = path.replace("\\", "/").lower().rstrip("/")
    nome = normalized.rsplit("/", 1)[-1]
    return any(marker in nome for marker in _ACCESSIBILITY_MARKERS)


def accessibility_scope_denial_message(path: str) -> str:
    """Mensagem amigavel de recusa quando o diretorio esta fora do escopo
    permitido -- devolvida como resultado da tool, nunca uma excecao."""
    display_path = os.path.normpath(path) if path else "(vazio)"
    return (
        f"Não posso executar comandos ou editar arquivos em '{display_path}': "
        "esta ferramenta só age em diretórios de projeto de acessibilidade "
        "(o nome da própria pasta apontada precisa indicar isso, "
        "ex.: 'acessibilidade', 'accessibility', 'a11y'). "
        "Para testar ou corrigir esse projeto, renomeie a pasta (ou aponte para "
        "uma pasta cujo nome já deixe isso claro) e tente de novo."
    )
