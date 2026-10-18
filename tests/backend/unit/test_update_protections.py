"""A proteção por provedor e por módulo não pode ficar para trás: a suíte reprova se a fonte (evidencias.json) e os arquivos
gerados (matriz, fichas, READMEs) divergem, ou se um provedor testado não tem ficha, contrato e notas."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "update_protections.py"
spec = importlib.util.spec_from_file_location("update_protections", SCRIPT)
protections = importlib.util.module_from_spec(spec)
sys.modules["update_protections"] = protections
spec.loader.exec_module(protections)


def sample() -> dict:
    return {
        "modulos": {
            "m1": {"titulo": "Conversa", "readme": "x.md", "testes_automaticos": ["tests/backend/unit/test_update_protections.py"]},
            "m2": {"titulo": "URL", "readme": "y.md", "testes_automaticos": ["tests/backend/unit/test_update_protections.py"]},
        },
        "provedores": {
            "a": {
                "nome": "Provedor A", "ficha": "a.md", "contrato": None, "contrato_pendente": "falta cota",
                "modulos": {
                    "m1": {"estado": "PROVADO", "data": "2026-10-08", "nota": "funcionou"},
                    "m2": {"estado": "NÃO TESTADO", "data": None, "nota": ""},
                },
                "cenarios": {},
            },
        },
    }


def test_repository_protections_are_up_to_date_with_the_single_source():
    data = protections.load()
    assert protections.render(data, write=False) == [], "rode: scripts/update_protections.py render"
    assert protections.problems(data) == []


def test_matrix_shows_state_and_date_for_every_provider_and_module():
    table = protections.matrix(sample())
    assert "| Provedor A |" in table
    assert "1 Conversa | PROVADO (08/10) |" in table
    assert "2 URL | NÃO TESTADO |" in table


def test_a_tested_module_without_note_or_date_is_reported():
    data = sample()
    data["provedores"]["a"]["modulos"]["m1"].update(nota="", data=None)
    assert any("sem data ou sem nota" in problem for problem in protections.problems(data))


def test_a_provider_with_a_tested_module_needs_a_ficha_and_a_contract_or_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(protections, "PROVIDERS_DIR", tmp_path)
    data = sample()
    assert any("sem ficha" in problem for problem in protections.problems(data))
    (tmp_path / "a.md").write_text("# Ficha\n" + protections.TODO + ": preencher\n", encoding="utf-8")
    assert any("A PREENCHER" in problem for problem in protections.problems(data))
    (tmp_path / "a.md").write_text("# Ficha completa\n", encoding="utf-8")
    assert protections.problems(data) == []
    data["provedores"]["a"]["contrato_pendente"] = ""
    assert any("sem contrato real gravado" in problem for problem in protections.problems(data))


def test_a_stub_ficha_is_flagged_until_it_is_filled_in():
    assert protections.TODO in protections.stub({"nome": "Provedor Novo"})


@pytest.mark.parametrize("day,expected", [("2026-10-09", "09/10/2026"), (None, "sem data")])
def test_dates_are_shown_in_brazilian_format(day, expected):
    assert protections.br(day) == expected


class TestRegistroDeModulos:
    """Regra 15: cada módulo registra seus testes automáticos e a tag do último estado provado."""

    def test_modulo_sem_testes_registrados_reprova(self):
        data = sample()
        del data["modulos"]["m1"]["testes_automaticos"]
        assert any("m1: sem testes automáticos" in p for p in protections.registry_problems(data))

    def test_teste_registrado_que_nao_existe_reprova(self):
        data = sample()
        data["modulos"]["m2"]["testes_automaticos"] = ["tests/backend/unit/nao_existe.py"]
        assert any("não existe" in p for p in protections.registry_problems(data))

    def test_tag_e_commit_precisam_vir_juntos_e_bater(self):
        data = sample()
        data["modulos"]["m1"]["tag_ultimo_estado_provado"] = "modulo-1-x"
        assert any("precisam vir juntos" in p for p in protections.registry_problems(data))
        data["modulos"]["m1"]["commit_ultimo_estado_provado"] = "abc1234"
        assert any("não existe ou não aponta" in p for p in protections.registry_problems(data, tags={}))
        assert protections.registry_problems(data, tags={"modulo-1-x": "abc1234ffffffff"}) == []

    def test_registro_real_do_projeto_esta_em_dia(self):
        data = protections.load()
        assert protections.registry_problems(data, tags=protections.local_tags() or None) == []
