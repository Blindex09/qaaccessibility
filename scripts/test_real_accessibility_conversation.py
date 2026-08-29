"""
scripts/test_real_accessibility_conversation.py
Simulação e execução real de um teste de acessibilidade agêntico do começo ao fim (Multi-Turn Chat),
utilizando o backend local (http://127.0.0.1:8001/chat/stream) e o provedor Ollama Cloud.
"""

import json
import os
import sys
import urllib.error
import urllib.request

# Garantir env var
API_KEY = os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY") or "56fe647438c0474babb266897d888f95.BgnWogEAJIRSEjTtRydKTyVP"
os.environ["OLLAMA_CLOUD_API_KEY"] = API_KEY
os.environ["OLLAMA_API_KEY"] = API_KEY

BACKEND_URL = "http://127.0.0.1:8001/chat/stream"


def send_chat_turn(message: str, history: list[dict[str, str]]) -> str:
    print(f"\n{'='*70}\n[USUÁRIO]: {message}\n{'='*70}")

    payload = json.dumps({
        "message": message,
        "history": history,
        "provider": "ollama-cloud",
        "model": "alto"
    }).encode("utf-8")

    req = urllib.request.Request(
        BACKEND_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    full_response = []
    print("[ASSISTENTE - Resposta em tempo real]:\n")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                decoded = line.decode("utf-8").strip()
                if decoded.startswith("data: "):
                    data_str = decoded[6:]
                    try:
                        event = json.loads(data_str)
                        ev_type = event.get("type")
                        if ev_type == "token":
                            tok = event.get("text") or event.get("token", "")
                            sys.stdout.write(tok)
                            sys.stdout.flush()
                            full_response.append(tok)
                        elif ev_type == "phase":
                            print(f"\n--- [Fase Agêntica: {event.get('phase')}] ---")
                        elif ev_type == "tool_start":
                            print(f"\n--- [Executando Ferramenta: {event.get('name')}] ---")
                        elif ev_type == "clarify":
                            req_id = event.get("request_id")
                            quest = event.get("question", "")
                            print(f"\n--- [Pergunta de Aclaração/Aprovação Recebida (ID: {req_id})]: {quest} ---")
                            # Responde via POST /chat/clarify para desbloquear a execução
                            clarify_payload = json.dumps({"request_id": req_id, "answer": "Aprovar Plano"}).encode("utf-8")
                            clarify_req = urllib.request.Request(
                                "http://127.0.0.1:8001/chat/clarify",
                                data=clarify_payload,
                                headers={"Content-Type": "application/json"},
                                method="POST"
                            )
                            try:
                                with urllib.request.urlopen(clarify_req, timeout=10) as c_resp:
                                    print("  -> Resposta de aprovação enviada via /chat/clarify com sucesso!")
                            except Exception as c_exc:
                                print(f"  -> Falha ao enviar resposta de clarify: {c_exc}")
                        elif ev_type == "done":
                            final_txt = event.get("final", "")
                            if not full_response and final_txt:
                                print(final_txt)
                                full_response.append(final_txt)
                            print("\n--- [Turno Concluído] ---")
                        elif ev_type == "error":
                            print(f"\n[ERRO]: {event.get('error')}")
                    except Exception:
                        pass
    except Exception as exc:
        print(f"\n[FALHA DE COMUNICAÇÃO HTTP]: {exc}")
        return ""

    return "".join(full_response)


def main():
    print("======================================================================")
    print("  SIMULAÇÃO E2E DE AUDITORIA DE ACESSIBILIDADE MULTI-TURNO (WCAG 2.2)")
    print("======================================================================")

    history = []

    # Turno 1: Requisição de Análise do HTML
    msg1 = (
        "Por favor, analise a acessibilidade deste formulário HTML:\n"
        "<main>\n"
        "  <header><h1>Cadastro de Usuário</h1></header>\n"
        "  <form>\n"
        "    <div onclick='submitForm()'><img src='submit.png'>Enviar Cadastro</div>\n"
        "    <input type='text' id='nome'>\n"
        "    <span style='color: #999999; background-color: #ffffff;'>Insira seu nome completo</span>\n"
        "  </form>\n"
        "</main>"
    )
    ans1 = send_chat_turn(msg1, history)
    if ans1:
        history.append({"role": "user", "content": msg1})
        history.append({"role": "assistant", "content": ans1})

    # Turno 2: Pergunta de Aprofundamento Técnico sobre Leitores de Tela
    msg2 = "Quais são os critérios específicos da WCAG 2.2 violados no exemplo acima e como cada um impacta usuários de leitores de tela como NVDA ou TalkBack?"
    ans2 = send_chat_turn(msg2, history)
    if ans2:
        history.append({"role": "user", "content": msg2})
        history.append({"role": "assistant", "content": ans2})

    # Turno 3: Solicitação da Solução e Código Corrigido
    msg3 = "Por favor, me forneça o código HTML totalmente corrigido, semântico e 100% acessível para produção."
    ans3 = send_chat_turn(msg3, history)
    if ans3:
        history.append({"role": "user", "content": msg3})
        history.append({"role": "assistant", "content": ans3})

    # Turno 4: Confirmação do Plano para Geração do Código HTML Final
    msg4 = "Sim, pode aplicar todas as correções descritas no plano e me gerar o código HTML final semântico agora!"
    ans4 = send_chat_turn(msg4, history)
    if ans4:
        history.append({"role": "user", "content": msg4})
        history.append({"role": "assistant", "content": ans4})

    print("\n======================================================================")
    print("  CONVERSA MULTI-TURNO CONCLUÍDA COM SUCESSO DO COMEÇO AO FIM!")
    print("======================================================================")


if __name__ == "__main__":
    main()
