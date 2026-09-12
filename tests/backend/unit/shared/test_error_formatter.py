"""Testes unitários do formatador de erros amigáveis de IA."""

from backend.src.services.error_formatter import format_human_friendly_error as format_services_error
from backend.src.shared.error_formatter import format_human_friendly_error


def test_format_402_credit_error():
    err = "Error code: 402 - {'error': 'this model uses extra usage only and your extra usage balance is empty'}"
    out = format_human_friendly_error(err)
    assert "saldo de créditos" in out
    assert "Configurações" in out


def test_format_401_invalid_key():
    err = "Error code: 401 - Invalid API Key provided"
    out = format_human_friendly_error(err)
    assert "chave de API" in out
    assert "Configurações" in out


def test_format_429_rate_limit():
    err = "Error code: 429 - Rate limit exceeded"
    out = format_human_friendly_error(err)
    expected = (
        "Desculpe, ocorreu um erro: O limite de requisições por minuto (Rate Limit) ou cota semanal foi atingido no provedor de IA.\n"
        "Como resolver:\n"
        "1. Aguarde alguns segundos e tente enviar sua mensagem novamente.\n"
        "2. Ou selecione outro Provedor nas Configurações para continuar imediatamente sem aguardar."
    )
    assert out == expected


def test_format_429_weekly_usage_limit():
    err = "you have reached your weekly usage limit for this model"
    out = format_human_friendly_error(err)
    assert "cota semanal foi atingido" in out
    assert "Desculpe, ocorreu um erro" in out


def test_format_services_error_formatter_import_reexport():
    err = "429 quota exceeded"
    out = format_services_error(err)
    assert "Rate Limit" in out


def test_format_403_forbidden():
    err = "Error code: 403 - Permission denied for model"
    out = format_human_friendly_error(err)
    assert "Acesso negado" in out


def test_format_404_model_not_found():
    err = "Error code: 404 - Model 'gpt-custom' not found"
    out = format_human_friendly_error(err)
    assert "não foi encontrado" in out


def test_format_500_server_error():
    err = "Error code: 503 - Service Unavailable"
    out = format_human_friendly_error(err)
    assert "sobrecarregado ou indisponível" in out


def test_format_network_timeout():
    err = "httpx.ConnectTimeout: Connection refused"
    out = format_human_friendly_error(err)
    assert "provedor de IA" in out
    assert "Ollama" in out


def test_format_browserless_error_does_not_expose_raw_details():
    raw = (
        "BrowserType.connect_over_cdp: Invalid URL\n"
        "Call log: retrieving websocket url from secret-token-value"
    )
    out = format_human_friendly_error(raw)
    assert "mecanismo interno de navegação" in out
    assert "connect_over_cdp" not in out
    assert "secret-token-value" not in out
    assert "Call log" not in out


def test_format_unknown_error_does_not_return_technical_detail():
    raw = "Traceback (most recent call last): RuntimeError: internal secret"
    out = format_human_friendly_error(raw)
    assert "Não foi possível concluir esta etapa" in out
    assert "Traceback" not in out
    assert "internal secret" not in out

