"""Cache do consentimento do usuário pra execução de comandos LOCAIS
(instalar/rodar Cypress ou Selenium na máquina do backend), isolado por sessão.

Achado real (pedido do usuário, 2026-08-10): rodar/instalar Cypress ou
Selenium localmente exige confirmação -- mas o usuário pode escolher "só
essa vez" (pergunta de novo na próxima) ou "sempre aprovar local nesta
conversa" (não repete a pergunta de novo pro mesmo runner). Isso NÃO
substitui o cartão de aprovação humana (`requires_approval=True` em
`run_remote_test`, ver chat_tools.py) -- esse continua disparando em toda
chamada, é o freio estrutural que nunca pode ser pulado. Este store só evita
o modelo repetir a PERGUNTA via `clarify` a cada turno quando o usuário já
disse "sempre" nesta mesma conversa.
"""
import logging

from backend.src.services.session_context import resolve_session

logger = logging.getLogger(__name__)

# session -> {runner: "always"}  (ausência = precisa perguntar de novo)
_sessions: dict[str, dict[str, str]] = {}


def set_consent(runner: str, level: str, session_id: str | None = None) -> None:
    """`level` esperado: "once" (não guarda nada) ou "always" (guarda)."""
    if level != "always":
        return
    session = resolve_session(session_id)
    _sessions.setdefault(session, {})[runner] = "always"
    logger.info("[LocalExecConsentStore] Consentimento 'sempre' registrado (sessão %s, runner=%s)", session, runner)


def has_standing_consent(runner: str, session_id: str | None = None) -> bool:
    session = resolve_session(session_id)
    return _sessions.get(session, {}).get(runner) == "always"
