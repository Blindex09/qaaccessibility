"""
Formatador de Erros Amigáveis de IA e Provedores (2026).

Converte exceções técnicas de APIs LLM (OpenAI, Anthropic, Gemini, xAI, Ollama),
erros HTTP (400, 401, 402, 403, 404, 429, 500, 502, 503, 504) e falhas de rede em
mensagens amigáveis, claras, empáticas e orientadas a ação em Português.
"""

import logging

logger = logging.getLogger(__name__)


def format_human_friendly_error(raw_error: object) -> str:
    """Converte qualquer exceção ou string de erro técnico em mensagem amigável em Português."""
    err_str = str(raw_error or "").strip()
    if not err_str:
        return "Ocorreu um erro inesperado ao se comunicar com o servidor de IA."

    err_lower = err_str.lower()

    # 402 / Quota / Balance Empty / Payment Required
    if any(k in err_lower for k in ("402", "extra usage balance is empty", "insufficient_quota", "payment required", "credit_balance_too_low")):
        msg = (
            "O saldo de créditos do provedor de IA atual se esgotou.\n\n"
            "Como resolver:\n"
            "1. Acesse as Configurações no menu e selecione outro Provedor (ex.: Gemini, OpenAI, Anthropic, xAI ou Agentic Auto).\n"
            "2. Ou recarregue seu saldo de créditos/plano no painel do provedor selecionado."
        )
        if "ollama.com/settings" in err_lower:
            msg += "\n3. Ou gerencie sua conta em https://ollama.com/settings."
        return msg

    # 401 / Invalid API Key / Unauthorized / Authentication
    if any(k in err_lower for k in ("401", "invalid api key", "unauthorized", "authentication_error", "invalid_api_key", "incorrect api key")):
        return (
            "A chave de API (API Key) do provedor selecionado é inválida ou expirou.\n\n"
            "Como resolver:\n"
            "1. Acesse as Configurações e verifique se a sua chave de API está correta.\n"
            "2. Ou troque de Provedor nas Configurações para um com chave válida."
        )

    # 429 / Rate Limit / Too Many Requests / Resource Exhausted / Weekly Usage Limit
    if any(
        k in err_lower
        for k in (
            "429",
            "rate limit",
            "too many requests",
            "rate_limit_exceeded",
            "quota exceeded",
            "resource_exhausted",
            "resource_exceeded",
            "weekly usage limit",
            "usage limit",
            "reached your weekly",
        )
    ):
        return (
            "Desculpe, ocorreu um erro: O limite de requisições por minuto (Rate Limit) ou cota semanal foi atingido no provedor de IA.\n"
            "Como resolver:\n"
            "1. Aguarde alguns segundos e tente enviar sua mensagem novamente.\n"
            "2. Ou selecione outro Provedor nas Configurações para continuar imediatamente sem aguardar."
        )

    # 403 / Forbidden / Access Denied
    if any(k in err_lower for k in ("403", "forbidden", "access denied", "permission_denied", "permission denied")):
        return (
            "Acesso negado pelo provedor de IA.\n\n"
            "Como resolver:\n"
            "1. Verifique as permissões da sua chave de API no painel do provedor.\n"
            "2. Se estiver usando um modelo restrito, troque para o modo 'Alto' ou outro Provedor nas Configurações."
        )

    # 404 / Model Not Found
    if any(k in err_lower for k in ("404", "model_not_found", "model not found", "does not exist")):
        return (
            "O modelo solicitado não foi encontrado ou não está disponível no provedor atual.\n\n"
            "Como resolver:\n"
            "1. Selecione o modo 'Alto' nas Configurações para que o sistema escolha automaticamente o modelo ativo mais recente.\n"
            "2. Ou selecione outro Provedor com suporte ao modelo desejado."
        )

    # 400 / Bad Request / Unsupported Parameter
    if any(k in err_lower for k in ("400", "bad request", "unsupported parameter", "invalid_request_error")):
        return (
            "A requisição enviada ao provedor de IA continha um parâmetro ou formato não suportado pelo modelo.\n\n"
            "Como resolver:\n"
            "1. Selecione o modo 'Alto' nas Configurações para usar os parâmetros padronizados do modelo.\n"
            "2. Se o erro persistir, tente trocar de Provedor."
        )

    # 500 / 502 / 503 / 504 / 529 / Service Unavailable / Overloaded
    if any(k in err_lower for k in ("500", "502", "503", "504", "529", "overloaded", "service unavailable", "internal server error", "bad gateway")):
        return (
            "O serviço do provedor de IA está temporariamente sobrecarregado ou indisponível.\n\n"
            "Como resolver:\n"
            "1. Troque o Provedor nas Configurações para continuar navegando sem interrupções.\n"
            "2. Ou tente novamente em alguns instantes."
        )

    # Rede / Timeout / Connection Refused
    if any(k in err_lower for k in ("connection refused", "connecterror", "connecttimeout", "readtimeout", "networkerror", "failed to connect", "socket", "timed out", "timeout")):
        return (
            "Não foi possível se conectar ao provedor de IA.\n\n"
            "Como resolver:\n"
            "1. Verifique sua conexão com a internet.\n"
            "2. Se estiver usando o Ollama local, certifique-se de que o servidor Ollama está rodando em http://localhost:11434.\n"
            "3. Caso contrário, selecione um provedor em nuvem (Gemini, OpenAI, Anthropic, xAI) nas Configurações."
        )

    # Fallback padrão amigável para outros erros
    return f"Não foi possível obter resposta do provedor de IA no momento.\nDetalhe técnico: {err_str}"

