"""Regressao: reanalisar o mesmo ZIP nao pode devolver MENOS problemas.

Bug real medido em 2026-08-30 com um ZIP de 2 paginas: a primeira analise
devolveu 17 issues e a releitura do cache devolveu 12. Os 5 que sumiram eram os
que `_map_issues_to_files` nao conseguiu atribuir a um arquivo -- best-effort,
so marca quando localiza o trecho dentro do arquivo. O cache guardava, por
arquivo, apenas os issues cujo `url` batia com aquele nome, entao esses cinco
nao eram gravados em lugar nenhum e desapareciam calados na segunda leitura.
"""

import io
import zipfile
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.src.main import app

client = TestClient(app)

_HTML_A = "<html><body><img src='a.png'></body></html>"
_HTML_B = "<html><body><table><tr><td>x</td></tr></table></body></html>"


def _zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", _HTML_A)
        z.writestr("sobre.html", _HTML_B)
    buf.seek(0)
    return buf


def _resposta_da_analise():
    """Dois issues localizaveis (um por arquivo) e um que nao casa com nenhum."""
    return {
        "agent": "orchestrator",
        "success": True,
        "data": {
            "issues": [
                {
                    "id": "i1",
                    "guideline": "WCAG 2.2",
                    "criterion": "1.1.1",
                    "severity": "critical",
                    "element": "<img src='a.png'>",
                    "description": "sem alt",
                    "suggestion": "add alt",
                },
                {
                    "id": "i2",
                    "guideline": "WCAG 2.2",
                    "criterion": "1.3.1",
                    "severity": "high",
                    "element": "<table>",
                    "description": "sem th",
                    "suggestion": "add th",
                },
                {
                    "id": "i3",
                    "guideline": "WCAG 2.2",
                    "criterion": "4.1.1",
                    "severity": "medium",
                    "element": "algo que nao existe em arquivo nenhum",
                    "description": "issue sem arquivo atribuido",
                    "suggestion": "rever",
                },
            ]
        },
    }


def _analisar(cache_dir):
    with (
        patch("backend.src.routes.analyze.orchestrate", new_callable=AsyncMock) as mock,
        patch("backend.src.routes.analyze._get_cache_path", return_value=str(cache_dir / "cache.json")),
    ):
        mock.return_value = _resposta_da_analise()
        resp = client.post("/analyze/project/zip", files={"file": ("p.zip", _zip_bytes(), "application/zip")})
        return resp, mock


class TestCacheDeProjetoZip:
    def test_releitura_do_cache_devolve_a_mesma_quantidade(self, tmp_path):
        primeira, mock1 = _analisar(tmp_path)
        assert primeira.status_code == 200
        n1 = len(primeira.json()["data"]["issues"])
        assert mock1.call_count == 1, "primeira analise deveria rodar o pipeline"

        segunda, mock2 = _analisar(tmp_path)
        assert segunda.status_code == 200
        n2 = len(segunda.json()["data"]["issues"])
        assert mock2.call_count == 0, "segunda leitura deveria vir toda do cache"

        assert n2 == n1, f"a releitura do cache perdeu issues: {n1} -> {n2}"

    def test_issue_sem_arquivo_sobrevive_ao_cache(self, tmp_path):
        _analisar(tmp_path)
        segunda, _ = _analisar(tmp_path)
        ids = {i["id"] for i in segunda.json()["data"]["issues"]}
        assert "i3" in ids, "o issue sem arquivo atribuido sumiu na releitura"

    def test_mudar_um_arquivo_invalida_o_balde_sem_arquivo(self, tmp_path):
        """Sem saber a que arquivo pertenciam, so da para reaproveita-los quando
        NADA mudou -- reaproveitar apos uma edicao seria reportar problema velho."""
        _analisar(tmp_path)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("index.html", _HTML_A.replace("a.png", "novo.png"))
            z.writestr("sobre.html", _HTML_B)
        buf.seek(0)

        with (
            patch("backend.src.routes.analyze.orchestrate", new_callable=AsyncMock) as mock,
            patch("backend.src.routes.analyze._get_cache_path", return_value=str(tmp_path / "cache.json")),
        ):
            mock.return_value = _resposta_da_analise()
            resp = client.post("/analyze/project/zip", files={"file": ("p.zip", buf, "application/zip")})

        assert resp.status_code == 200
        assert mock.call_count == 1, "arquivo alterado deveria disparar nova analise"
