"""Regressao: Cypress local sem relatorio NAO e pagina limpa.

Medido em 2026-08-31 contra https://www.w3.org/WAI/demos/bad/before/home.html --
a pagina que o W3C publica DE PROPOSITO cheia de violacoes:

    Cypress local  -> total_violations=0, passed=True
    axe-core nuvem -> total_violations=8 (4 serious, 2 critical, 2 moderate)

O Cypress rodou (runner=cypress_local, binario instalado de verdade), nao gerou
relatorio, e o codigo interpretou a ausencia como "nenhuma violacao encontrada".
Certificar como limpa uma pagina quebrada e o pior modo de falha que uma
ferramenta de acessibilidade pode ter.

O raciocinio original tinha fundamento -- com skipFailures=true, cy.checkA11y so
chama o callback que grava o arquivo quando ha achados -- mas "sem arquivo"
tambem acontece quando nenhum spec roda, quando o --record e recusado, ou quando
a pagina nao carrega. O spec passou a gravar SEMPRE, inclusive vazio, e a
ausencia virou sinal inequivoco de falha.
"""

from backend.src.services import remote_runners


class TestSpecGravaSempre:
    def test_template_grava_relatorio_mesmo_sem_violacoes(self):
        spec = remote_runners._CYPRESS_SPEC_TEMPLATE.format(
            url="https://exemplo.com", scope="body", report_filename="r.json"
        )
        # duas gravacoes DE VERDADE: a do callback (com achados) e a rede de
        # seguranca (vazia). Linhas de comentario que citam cy.writeFile nao contam.
        chamadas = [
            linha for linha in spec.splitlines() if "cy.writeFile" in linha and not linha.strip().startswith("//")
        ]
        assert len(chamadas) == 2, f"esperava 2 gravacoes, achei {len(chamadas)}: {chamadas}"
        assert "violations: []" in spec

    def test_rede_de_seguranca_nao_sobrescreve_o_relatorio_com_achados(self):
        """flag 'wx' falha se o arquivo ja existe -- o callback tem precedencia."""
        spec = remote_runners._CYPRESS_SPEC_TEMPLATE.format(
            url="https://exemplo.com", scope="body", report_filename="r.json"
        )
        assert "'wx'" in spec

    def test_template_usa_a_url_e_o_escopo_recebidos(self):
        spec = remote_runners._CYPRESS_SPEC_TEMPLATE.format(
            url="https://exemplo.com/a", scope="main", report_filename="r.json"
        )
        assert "https://exemplo.com/a" in spec
        assert "'main'" in spec


class TestAusenciaDeRelatorioNaoViraAprovacao:
    def test_o_codigo_nao_devolve_mais_lista_vazia_por_ausencia(self):
        """A guarda que transformava ausencia em 'zero violacoes' saiu."""
        import inspect

        fonte = inspect.getsource(remote_runners._try_run_local_cypress)
        assert "rodou sem violações encontradas" not in fonte, (
            "ausencia de relatorio nao pode mais ser lida como pagina limpa"
        )
        assert "execucao falhou, NAO e pagina limpa" in fonte

    def test_extrator_de_url_do_dashboard_continua_exigindo_a_linha_real(self):
        """Passar --record nao e o mesmo que ter gravado."""
        assert remote_runners._extract_cypress_dashboard_url("nenhuma url aqui") is None
        achado = remote_runners._extract_cypress_dashboard_url(
            "Recorded Run: https://cloud.cypress.io/projects/bae1oz/runs/7."
        )
        assert achado == "https://cloud.cypress.io/projects/bae1oz/runs/7"
