"""Regressao: a squad se reune quando ha TRABALHO, nao a cada frase.

Antes o quadro era montado em todo turno. Uma pergunta conceitual -- "qual a
diferenca entre aria-label e aria-labelledby?" -- pagava Product Owner + Tech
Lead + Engineering Manager antes de ser respondida: tres chamadas de LLM para
uma sprint que nao existe. Medido em 2026-08-31 na bateria de trajetoria, onde
casos triviais levaram dezenas de segundos so de planejamento.

A fronteira segue a regra do projeto: a leitura semantica ("isto e pedido de
trabalho ou conversa?") e da IA, no clarifier; o roteamento a partir dela e
deterministico.
"""

from backend.src.services.chat_runtime import _INTENTS_DE_TRABALHO


def _convoca(snapshot=None, anexos=False, intent=None) -> bool:
    """Espelha a condicao de `stream_chat`, para fixa-la em teste."""
    return snapshot is not None or anexos or intent is None or intent in _INTENTS_DE_TRABALHO


class TestQuandoASquadEConvocada:
    def test_conversa_nao_abre_quadro(self):
        assert not _convoca(intent="chat_a11y")

    def test_pedido_de_trabalho_abre_quadro(self):
        for intent in ("analyze_url", "analyze_code", "fix_code"):
            assert _convoca(intent=intent), intent

    def test_anexo_abre_quadro_por_fato_estrutural(self):
        """Nao depende de classificacao: ha arquivo, ha trabalho."""
        assert _convoca(anexos=True, intent="chat_a11y")

    def test_quadro_existente_continua_avancando(self):
        """Depois que o trabalho comecou, a conversa segue no mesmo quadro."""
        assert _convoca(snapshot={"tasks": []}, intent="chat_a11y")

    def test_sem_intencao_conhecida_abre_o_quadro(self):
        """Clarifier indisponivel: falhar para o lado de TER plano e mais barato
        do que perder o quadro de um trabalho real."""
        assert _convoca(intent=None)

    def test_fora_de_escopo_nao_abre_quadro(self):
        assert not _convoca(intent="out_of_scope")

    def test_ambiguo_nao_abre_quadro(self):
        """Ainda nao se sabe se ha trabalho -- o clarifier vai perguntar."""
        assert not _convoca(intent="needs_clarification")

    def test_a_lista_de_trabalho_nao_inclui_conversa(self):
        assert "chat_a11y" not in _INTENTS_DE_TRABALHO
        assert "out_of_scope" not in _INTENTS_DE_TRABALHO
        assert "needs_clarification" not in _INTENTS_DE_TRABALHO

    def test_intents_de_trabalho_existem_no_prompt_do_clarifier(self):
        """Costura: o que o roteamento consome tem de ser o que o clarifier emite."""
        from backend.src.agents.clarifier.clarifier import _INTENTS_VALIDOS

        assert set(_INTENTS_VALIDOS) >= _INTENTS_DE_TRABALHO
