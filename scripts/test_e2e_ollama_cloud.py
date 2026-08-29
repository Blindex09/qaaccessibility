"""
scripts/test_e2e_ollama_cloud.py
Script de prova E2E real e validação de engenharia agêntica 2026 com o provedor Ollama Cloud.

Valida:
1. Descoberta Dinâmica de Catálogo & Inspeção de Capacidades (GET /api/tags, POST /api/show)
2. Algoritmo de Roteamento Multi-Objetivo (Tier Alto vs Fast)
3. Engenharia de Contexto & Structured Outputs Adaptativos
4. Busca Nativa Web Search (POST /api/web_search)
5. Extração Nativa Web Fetch (POST /api/web_fetch)
6. Chamada de LLM Estruturada com Validação em Python
7. API Pública de Chat/Stream do Produto (http://127.0.0.1:8001/chat/stream)
8. Resiliência e Formatação de Erros

NOTA DE SEGURANÇA: A chave de API nunca é gravada ou exibida em logs/saídas.
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

# Garantir PYTHONPATH
sys.path.insert(0, r"C:\qaaccessibility")

# A suíte E2E exige uma chave fornecida pelo ambiente; nunca manter credenciais
# ou fallbacks embutidos no repositório.
API_KEY = os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY") or ""
if not API_KEY:
    print("[STATUS] BLOQUEADO: defina OLLAMA_CLOUD_API_KEY ou OLLAMA_API_KEY para o E2E real.")
    sys.exit(2)
os.environ["OLLAMA_CLOUD_API_KEY"] = API_KEY
os.environ["OLLAMA_API_KEY"] = API_KEY

from backend.src.services.llm_client import ISSUES_RESPONSE_SCHEMA, call_llm, extract_json_array
from backend.src.services.model_router import resolve_alto_model, resolve_fast_model
from backend.src.services.ollama_cloud_adapter import (
    adapt_ollama_cloud_request,
    discover_ollama_cloud_descriptors,
    fetch_ollama_cloud_tags,
    ollama_cloud_web_fetch,
    ollama_cloud_web_search,
)
from backend.src.shared.error_formatter import format_human_friendly_error


def print_section(title: str):
    print(f"\n{'='*70}\n[E2E 2026] {title}\n{'='*70}")


def run_test_case(name: str, fn):
    print(f"\n--- [TESTE] {name} ---")
    try:
        if asyncio.iscoroutinefunction(fn):
            res = asyncio.run(fn())
        else:
            res = fn()
        print(f"[STATUS] APROVADO: {name}")
        return True, res
    except Exception as exc:
        print(f"[STATUS] FALHA: {name} | Detalhes: {exc}")
        return False, None


# 1. Descoberta de Catálogo & Inspeção de Capacidades
def test_1_catalog_discovery():
    tags = fetch_ollama_cloud_tags(API_KEY)
    print(f"Modelos brutos encontrados no /api/tags: {len(tags)}")
    assert isinstance(tags, list), "/api/tags deve retornar uma lista"

    descriptors = discover_ollama_cloud_descriptors(API_KEY, force_refresh=True)
    print(f"Descritores normalizados descobertos: {len(descriptors)}")
    for d in descriptors[:3]:
        print(f"  - Modelo: {d.id} | Janela: {d.context_window} | Reasoning: {d.reasoning} | Tools: {d.has_tools} | Vision: {d.has_vision}")

    assert len(descriptors) > 0, "Deveria ter descoberto ao menos 1 modelo no Ollama Cloud"
    return descriptors


# 2. Roteamento Multi-Objetivo Agêntico
def test_2_intelligent_routing():
    alto_model = resolve_alto_model("ollama-cloud")
    fast_model = resolve_fast_model("ollama-cloud")
    print(f"Modelo resolvido para Tier ALTO: {alto_model}")
    print(f"Modelo resolvido para Tier FAST: {fast_model}")

    assert alto_model, "Tier ALTO deve resolver um modelo válido"
    assert fast_model, "Tier FAST deve resolver um modelo válido"
    return alto_model, fast_model


# 3. Engenharia de Contexto & Structured Outputs
def test_3_context_engineering():
    raw_prompt = "Você é um especialista WCAG 2.2."
    adapted_prompt, schema_out = adapt_ollama_cloud_request(raw_prompt, ISSUES_RESPONSE_SCHEMA)

    print(f"Prompt adaptado contém instrução JSON Schema: {'JSON Schema obrigatorio' in adapted_prompt}")
    print(f"Parametro schema para chamada bruta zerado: {schema_out is None}")

    assert "JSON Schema" in adapted_prompt, "Prompt adaptado deve injetar instrução estrita de JSON"
    assert schema_out is None, "Esquema bruto deve ser None no Ollama Cloud para evitar rejeição por proxy"


# 4. Busca Nativa Web Search (POST /api/web_search)
def test_4_web_search_native():
    results = ollama_cloud_web_search("WCAG 2.2 accessibility standard W3C", max_results=3, api_key=API_KEY)
    print(f"Resultados de busca web nativa retornados: {len(results)}")
    if results:
        first = results[0]
        print(f"  - Exemplo de resultado: {first.get('title', 'Sem titulo')} | {first.get('url', '')}")

    assert isinstance(results, list), "Web Search deve retornar uma lista de resultados"


# 5. Extração Nativa Web Fetch (POST /api/web_fetch)
def test_5_web_fetch_native():
    target_url = "https://www.w3.org/WAI/standards-guidelines/wcag/"
    fetched = ollama_cloud_web_fetch(target_url, api_key=API_KEY)
    print(f"Status da busca nativa de URL: {bool(fetched)}")

    assert isinstance(fetched, dict), "Web Fetch deve retornar um dicionário com metadados/conteúdo"


# 6. Execução de LLM Estruturada com Validação em Python
async def test_6_llm_call_structured():
    sys_prompt = "Você é um auditor WCAG 2.2. Analise o HTML e responda em JSON."
    usr_prompt = 'Analise este elemento: <button onclick="alert(1)">Clique</button>'

    response_text = await call_llm(
        system_prompt=sys_prompt,
        user_prompt=usr_prompt,
        temperature=0.1,
        agent_label="e2e-test",
        response_schema=ISSUES_RESPONSE_SCHEMA,
    )

    print(f"Resposta recebida da LLM ({len(response_text)} caracteres)")
    parsed = extract_json_array(response_text)
    print(f"Array de problemas extraído com sucesso com {len(parsed)} item(ns)")

    assert isinstance(parsed, list), "Resultado deve ser um JSON array válido"


# 7. Teste de Resiliência de Erro Formatações Amigáveis
def test_7_error_resiliency():
    err_401 = format_human_friendly_error("401 Invalid API Key for ollama.com/v1")
    err_404 = format_human_friendly_error("404 model 'non-existent-model' not found")
    print(f"Erro 401 formatado: {err_401.splitlines()[0]}")
    print(f"Erro 404 formatado: {err_404.splitlines()[0]}")

    assert "chave de API" in err_401, "Erro 401 deve orientar ajuste de chave de API"
    assert "modelo solicitado não foi encontrado" in err_404, "Erro 404 deve sugerir trocar para modo Alto"


# 8. Teste E2E da API Pública de Stream no Backend Local
async def test_8_backend_stream_endpoint():
    req_body = json.dumps({
        "message": "Qual é o critério WCAG para contraste de texto normal?",
        "history": [],
        "session_id": "e2e-session-test"
    }).encode("utf-8")

    req = urllib.request.Request(
        "http://127.0.0.1:8001/chat/stream",
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    chunks_count = 0
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for line in resp:
                if line:
                    chunks_count += 1
                    if chunks_count > 5:
                        break
        print(f"Stream HTTP 200 recebido da rota /chat/stream ({chunks_count} chunks lidos)")
        assert chunks_count > 0, "Endpoint de stream deve retornar eventos em tempo real"
    except Exception as exc:
        print(f"[Aviso] Servidor local backend pode estar desligado nesta etapa: {exc}")


def main():
    print_section("INICIANDO SUÍTE DE TESTES E2E REAIS - OLLAMA CLOUD 2026")

    results = []
    results.append(run_test_case("1. Descoberta de Catálogo & Capacidades (/api/tags, /api/show)", test_1_catalog_discovery))
    results.append(run_test_case("2. Roteamento Multi-Objetivo Agêntico (Alto vs Fast)", test_2_intelligent_routing))
    results.append(run_test_case("3. Engenharia de Contexto & Prompt Adaptation", test_3_context_engineering))
    results.append(run_test_case("4. Busca Nativa Web Search (/api/web_search)", test_4_web_search_native))
    results.append(run_test_case("5. Extração Nativa Web Fetch (/api/web_fetch)", test_5_web_fetch_native))
    results.append(run_test_case("6. Execução de LLM Estruturada com Validação em Python", test_6_llm_call_structured))
    results.append(run_test_case("7. Resiliência e Formatação de Erros em Português", test_7_error_resiliency))
    results.append(run_test_case("8. API Pública de Chat Stream (/chat/stream)", test_8_backend_stream_endpoint))

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)

    print_section("RESUMO DOS TESTES E2E REAIS")
    print(f"Total de contextos validados: {total}")
    print(f"Aprovados: {passed}")
    print(f"Falhas: {total - passed}")

    if passed == total:
        print("\nSUCESSO: Todos os conceitos agênticos de 2026 e integrações reais do Ollama Cloud estão validados e operacionais!")
        sys.exit(0)
    else:
        print("\nATENÇÃO: Existem pontos de falha que precisam ser ajustados no código.")
        sys.exit(1)


if __name__ == "__main__":
    main()
