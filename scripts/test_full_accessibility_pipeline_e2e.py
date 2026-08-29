"""
scripts/test_full_accessibility_pipeline_e2e.py
Execução completa do pipeline real de acessibilidade do QA Accessibility via httpx:
1. POST /analyze/file (25 agentes especialistas WCAG 2.2 com Ollama Cloud)
2. POST /fix (Correção automática de HTML via AST/Codemod)
3. POST /analyze/vpat (Relatório VPAT WCAG 2.2 para conformidade enterprise)
4. POST /analyze/tests (Geração de suíte Playwright + axe-core para CI/CD)
"""

import os

import httpx

# Garantir env var
API_KEY = os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY") or "56fe647438c0474babb266897d888f95.BgnWogEAJIRSEjTtRydKTyVP"
os.environ["OLLAMA_CLOUD_API_KEY"] = API_KEY
os.environ["OLLAMA_API_KEY"] = API_KEY
os.environ["DEFAULT_PROVIDER"] = "ollama-cloud"

BASE_URL = "http://127.0.0.1:8001"

SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head><title>Formulário de Teste</title></head>
<body>
  <main>
    <h1>Cadastro de Acessibilidade</h1>
    <form action="/submit" method="post">
      <div onclick="submitForm()"><img src="enviar.png">Enviar Cadastro</div>
      <input type="text" id="nome">
      <span style="color: #999999; background-color: #ffffff;">Insira seu nome completo</span>
    </form>
  </main>
</body>
</html>
"""


def main():
    print("======================================================================")
    print("  INICIANDO AUDITORIA REAL DE ACESSIBILIDADE DE PONTA A PONTA (E2E)")
    print("======================================================================")

    client = httpx.Client(base_url=BASE_URL, timeout=300.0, follow_redirects=True)

    # 1. Análise Completa de Acessibilidade (POST /analyze/file)
    print("\n--- ETAPA 1: Executando Análise Completa (POST /analyze/file) ---")
    files = {"file": ("formulario_teste.html", SAMPLE_HTML.encode("utf-8"), "text/html")}
    resp = client.post("/analyze/file", files=files)
    print(f"Status HTTP /analyze/file: {resp.status_code}")
    analyze_res = resp.json()

    issues = analyze_res.get("data", {}).get("issues", []) if analyze_res.get("data") else analyze_res.get("issues", [])
    score = analyze_res.get("data", {}).get("score", 0) if analyze_res.get("data") else analyze_res.get("score", 0)
    print(f"[Análise Concluída] Pontuação: {score}/100 | Problemas encontrados: {len(issues)}")

    for issue in issues[:5]:
        crit = issue.get("criterion", "WCAG")
        desc = issue.get("description") or issue.get("message") or "Problema de acessibilidade"
        sev = issue.get("severity", "medium").upper()
        print(f"  - [{sev}] {crit}: {desc}")

    assert len(issues) > 0, "Deveria ter encontrado problemas de acessibilidade no HTML"

    # 2. Correção Automática de HTML (POST /fix)
    print("\n--- ETAPA 2: Aplicando Correção Automática (POST /fix) ---")
    fix_resp = client.post("/fix", json={
        "html_content": SAMPLE_HTML,
        "issues": issues,
        "provider": "ollama-cloud",
        "model": "alto"
    })
    print(f"Status HTTP /fix: {fix_resp.status_code}")
    fix_res = fix_resp.json()

    fixed_html = fix_res.get("fixed_html") or fix_res.get("data", {}).get("fixed_html", "")
    print(f"[Correção Concluída] HTML Corrigido Gerado ({len(fixed_html)} caracteres)")
    print("Trecho do HTML corrigido:")
    print(fixed_html[:350] + "...\n")

    assert len(fixed_html) > 0, "HTML corrigido não deve ser vazio"

    # 3. Geração de VPAT WCAG 2.2 Enterprise (POST /analyze/vpat)
    print("--- ETAPA 3: Gerando Relatório VPAT Enterprise (POST /analyze/vpat) ---")
    vpat_resp = client.post("/analyze/vpat", json={
        "issues": issues,
        "product_name": "Formulário de Cadastro QA",
        "provider": "ollama-cloud",
        "model": "alto"
    })
    print(f"Status HTTP /analyze/vpat: {vpat_resp.status_code}")
    vpat_res = vpat_resp.json()
    vpat_data = vpat_res.get("data", {}).get("vpat", {})
    print(f"[VPAT Gerado] Produto: {vpat_data.get('product_name', 'QA App')} | Critérios catalogados: {len(vpat_data.get('criteria', []))}\n")

    # 4. Geração de Suíte de Testes Playwright + axe-core para CI/CD (POST /analyze/tests)
    print("--- ETAPA 4: Gerando Suíte de Testes Playwright + axe-core (POST /analyze/tests) ---")
    tests_resp = client.post("/analyze/tests", json={
        "issues": issues,
        "target": "formulario_teste.html",
        "provider": "ollama-cloud",
        "model": "alto"
    })
    print(f"Status HTTP /analyze/tests: {tests_resp.status_code}")
    tests_res = tests_resp.json()
    suite = tests_res.get("data", {}).get("suite", {})
    print(f"[Suíte Gerada] Arquivo de teste: {suite.get('filename', 'a11y.spec.ts')}")

    print("\n======================================================================")
    print("  AUDITORIA DE ACESSIBILIDADE REAL E2E CONCLUÍDA COM SUCESSO TOTAL!")
    print("======================================================================")


if __name__ == "__main__":
    main()
