import pytest

from backend.src.services.local_project_guard import (
    accessibility_scope_denial_message,
    is_accessibility_project_dir,
)


class TestIsAccessibilityProjectDir:
    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Users\felipe\projetos\meu-projeto-acessibilidade",
            r"C:\dev\accessibility-app",
            r"C:\dev\a11y-widgets",
            "/home/user/projects/acessivel",
            r"C:\Users\felipe\Documents\clientes\loja-acessibilidade",
            "acess-checker",
        ],
    )
    def test_recognizes_accessibility_named_paths(self, path):
        assert is_accessibility_project_dir(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Users\felipe\projetos\loja-online",
            r"C:\dev\my-react-app",
            "/home/user/projects/dashboard",
            r"C:\Users\felipe\Documents\banco",
            "",
        ],
    )
    def test_rejects_unrelated_paths(self, path):
        assert is_accessibility_project_dir(path) is False

    def test_case_insensitive(self):
        assert is_accessibility_project_dir(r"C:\Dev\ACESSIBILIDADE-App") is True

    def test_ancestral_nao_libera_mais_o_filho(self):
        r"""Comportamento INVERTIDO deliberadamente em 2026-08-31, a pedido do usuario.

        Este teste afirmava que `C:\Acessibilidade\clientes\loja-x` era
        permitido, porque o guarda casava contra qualquer segmento do caminho.
        Medido na pratica, isso abria um buraco largo: qualquer ancestral --
        pasta de usuario, workspace, rotulo de drive -- com "access" no nome
        liberava TODO projeto abaixo dele para ESCRITA EM DISCO. Um caso real:
        `...\claude\C--qaaccessibility\...\projeto-comum` passava.

        O criterio passou a ser o nome da propria pasta apontada. Custo
        assumido: quem trabalha sob uma raiz de acessibilidade precisa apontar
        para a raiz ou renomear a subpasta -- uma recusa, nao um disco aberto.
        """
        assert is_accessibility_project_dir(r"C:\Acessibilidade\clientes\loja-x") is False
        assert is_accessibility_project_dir(r"C:\Acessibilidade") is True


class TestAccessibilityScopeDenialMessage:
    def test_message_mentions_the_path(self):
        msg = accessibility_scope_denial_message(r"C:\dev\loja-online")
        assert "loja-online" in msg

    def test_message_is_friendly_not_a_stack_trace(self):
        msg = accessibility_scope_denial_message(r"C:\dev\loja-online")
        assert "Traceback" not in msg
        assert "acessibilidade" in msg.lower()


class TestGrafiaEnEPt:
    """Regressao: a grafia INGLESA `access` nao era aceita.

    A lista de marcadores tinha "acess" (PT, 1 c) mas nao "access" (EN, 2 c),
    e "acess" NAO e substring de "access". Consequencia: um diretorio chamado
    `ACCESS-portal` ou `access-audit` era RECUSADO, embora seja exatamente o
    nome que um usuario anglofono daria a um projeto de acessibilidade. O
    criterio e o NOME do diretorio, entao ele precisa cobrir as duas grafias
    que as pessoas de fato usam.
    """

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\x\ACCESS-portal",
            r"C:\dev\access-audit",
            r"C:\dev\accessible-shop",
            r"C:\dev\accessibility-audit",
        ],
    )
    def test_grafia_inglesa_e_aceita(self, path):
        assert is_accessibility_project_dir(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\projetos\meu-site-acessibilidade",
            r"C:\projetos\loja-acessivel",
            r"C:\dev\acess-checker",
        ],
    )
    def test_grafia_portuguesa_continua_aceita(self, path):
        assert is_accessibility_project_dir(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\projetos\loja-virtual",
            r"C:\dev\ecommerce",
            r"C:\Windows\System32",
            r"C:\Users\ana\Documents",
        ],
    )
    def test_a_fronteira_continua_fechada(self, path):
        """Ampliar a grafia nao pode virar "permite qualquer coisa"."""
        assert is_accessibility_project_dir(path) is False


class TestEscopoRestritoAoNomeDaPasta:
    r"""Regressao: um diretorio ANCESTRAL nao pode liberar tudo abaixo dele.

    Ate 2026-08-31 o guarda casava contra qualquer segmento do caminho. Medido:
    `...\claude\C--qaaccessibility\...\projeto-comum` passava por causa do
    segmento `C--qaaccessibility`, e o mesmo valeria para
    `C:\Users\accessibility-team\projetos\loja-de-sapatos` -- pasta de
    usuario, workspace ou rotulo de drive com "access" no nome liberavam TODO
    projeto abaixo. Num guarda de blast radius para escrita em disco, o modo de
    falha caro e liberar demais.
    """

    def test_ancestral_de_acessibilidade_nao_libera_o_filho(self):
        assert not is_accessibility_project_dir(r"C:\Users\accessibility-team\projetos\loja-de-sapatos")
        assert not is_accessibility_project_dir(r"C:\dev\a11y\workspace\sistema-financeiro")

    def test_caso_real_que_invalidou_um_teste_meu(self):
        caminho = r"C:\Users\olive\AppData\Local\Temp\claude\C--qaaccessibility\sessao\projeto-comum"
        assert not is_accessibility_project_dir(caminho)

    def test_nome_da_pasta_apontada_continua_valendo(self):
        assert is_accessibility_project_dir(r"C:\projetos\loja-acessibilidade")
        assert is_accessibility_project_dir(r"C:\projetos\ACCESS-portal")
        assert is_accessibility_project_dir(r"C:\projetos\meu-a11y-audit")

    def test_barra_final_nao_atrapalha(self):
        assert is_accessibility_project_dir("C:/projetos/accessibility-suite/")
        assert is_accessibility_project_dir(r"C:\projetos\loja-acessibilidade\\")

    def test_monorepo_precisa_apontar_para_a_raiz(self):
        """Custo assumido da restricao: o subpacote e barrado, a raiz passa."""
        assert is_accessibility_project_dir(r"C:\dev\accessibility-suite")
        assert not is_accessibility_project_dir(r"C:\dev\accessibility-suite\packages\web")

    def test_mensagem_de_recusa_fala_da_propria_pasta(self):
        msg = accessibility_scope_denial_message(r"C:\projetos\loja")
        assert "própria pasta" in msg
