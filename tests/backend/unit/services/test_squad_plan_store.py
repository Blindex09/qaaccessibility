"""Quadro da squad persistido por conversa.

Antes desta camada o plano nascia e morria no mesmo turno: nenhum estado
sobrevivia à mensagem, então o "quadro" era um retrato descartável. Estes
testes fixam o isolamento por sessão (duas conversas nunca se misturam) e a
sobrevivência em disco.
"""

import json

import pytest

from backend.src.services import squad_plan_store


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    # O store escreve em tempfile.gettempdir(); redireciona para o tmp do teste
    # para nao sujar a maquina nem depender de estado entre execucoes.
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    squad_plan_store._sessions.clear()
    yield
    squad_plan_store._sessions.clear()


def _quadro(objetivo: str) -> dict:
    return {"objective": objetivo, "tasks": [{"id": "product-scope", "status": "done"}], "decisions": []}


def test_salva_e_carrega_o_quadro_da_mesma_conversa():
    squad_plan_store.save_squad_plan(_quadro("auditar a home"), session_id="conversa-a")
    assert squad_plan_store.load_squad_plan("conversa-a")["objective"] == "auditar a home"


def test_conversas_diferentes_nunca_compartilham_quadro():
    squad_plan_store.save_squad_plan(_quadro("auditar a home"), session_id="conversa-a")
    squad_plan_store.save_squad_plan(_quadro("auditar o checkout"), session_id="conversa-b")

    assert squad_plan_store.load_squad_plan("conversa-a")["objective"] == "auditar a home"
    assert squad_plan_store.load_squad_plan("conversa-b")["objective"] == "auditar o checkout"


def test_quadro_sobrevive_a_perda_do_cache_em_memoria():
    """Reinício do backend não pode apagar o ciclo em andamento."""
    squad_plan_store.save_squad_plan(_quadro("auditar a home"), session_id="conversa-a")
    squad_plan_store._sessions.clear()

    assert squad_plan_store.load_squad_plan("conversa-a")["objective"] == "auditar a home"


def test_conversa_sem_quadro_devolve_none():
    assert squad_plan_store.load_squad_plan("conversa-nova") is None


def test_limpar_encerra_o_ciclo_em_memoria_e_em_disco():
    squad_plan_store.save_squad_plan(_quadro("auditar"), session_id="conversa-a")
    squad_plan_store.clear_squad_plan("conversa-a")

    assert squad_plan_store.load_squad_plan("conversa-a") is None


def test_arquivo_corrompido_degrada_para_replanejar_em_vez_de_estourar():
    squad_plan_store.save_squad_plan(_quadro("auditar"), session_id="conversa-a")
    squad_plan_store._sessions.clear()
    with open(squad_plan_store.get_plan_filepath("conversa-a"), "w", encoding="utf-8") as f:
        f.write("{ nao e json")

    assert squad_plan_store.load_squad_plan("conversa-a") is None


def test_conteudo_nao_dict_e_recusado():
    squad_plan_store._sessions.clear()
    with open(squad_plan_store.get_plan_filepath("conversa-a"), "w", encoding="utf-8") as f:
        json.dump(["nao", "e", "um", "quadro"], f)

    assert squad_plan_store.load_squad_plan("conversa-a") is None
