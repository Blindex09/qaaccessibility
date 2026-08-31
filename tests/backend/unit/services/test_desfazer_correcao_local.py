"""Regressao: desfazer tem que devolver os ARQUIVOS, nao so os caches.

Medido em 2026-08-31, ciclo completo em disco: `fix_local_project_files`
corrigiu um index.html de 155 para 382 caracteres e `undo_last_fix` respondeu
`{"restored": true, "message": "Estado anterior à última correção restaurado."}`
-- com o arquivo do usuario ainda alterado. O checkpoint guardava apenas
`issues`, `url` e `fix_pages`.

O backup dos originais JA era feito antes de escrever (um diretorio em
`qa_accessibility_local_backups/<uuid>`), e o caminho ate era devolvido no
resultado da ferramenta. Faltava alguem guarda-lo no checkpoint: sem isso a
promessa de desfazer era falsa exatamente na unica operacao que toca o
computador do usuario.
"""

import os

from backend.src.services import fix_checkpoint_store

_ORIGINAL = "<html><body><img src=b.png></body></html>"
_CORRIGIDO = '<html lang="pt-BR"><body><img src="b.png" alt="Banner"></body></html>'


def _projeto_com_backup(tmp_path):
    projeto = tmp_path / "loja-acessibilidade"
    projeto.mkdir()
    (projeto / "index.html").write_text(_ORIGINAL, encoding="utf-8")

    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "index.html").write_text(_ORIGINAL, encoding="utf-8")

    # a correcao sobrescreve o arquivo do usuario
    (projeto / "index.html").write_text(_CORRIGIDO, encoding="utf-8")
    return projeto, backup


class TestDesfazerCorrecaoLocal:
    def teardown_method(self):
        fix_checkpoint_store.clear_checkpoint() if hasattr(fix_checkpoint_store, "clear_checkpoint") else None

    def test_arquivo_volta_ao_conteudo_original(self, tmp_path):
        projeto, backup = _projeto_com_backup(tmp_path)
        assert (projeto / "index.html").read_text(encoding="utf-8") == _CORRIGIDO

        fix_checkpoint_store.create_checkpoint(
            "Correção local de 1 arquivo(s)", project_dir=str(projeto), backup_dir=str(backup)
        )
        assert fix_checkpoint_store.restore_checkpoint() is not None

        assert (projeto / "index.html").read_text(encoding="utf-8") == _ORIGINAL

    def test_subdiretorios_sao_restaurados(self, tmp_path):
        projeto = tmp_path / "loja-acessibilidade"
        (projeto / "paginas").mkdir(parents=True)
        (projeto / "paginas" / "sobre.html").write_text(_CORRIGIDO, encoding="utf-8")
        backup = tmp_path / "backup"
        (backup / "paginas").mkdir(parents=True)
        (backup / "paginas" / "sobre.html").write_text(_ORIGINAL, encoding="utf-8")

        fix_checkpoint_store.create_checkpoint("local", project_dir=str(projeto), backup_dir=str(backup))
        fix_checkpoint_store.restore_checkpoint()

        assert (projeto / "paginas" / "sobre.html").read_text(encoding="utf-8") == _ORIGINAL

    def test_checkpoint_sem_backup_nao_toca_no_disco(self, tmp_path):
        """Correcao por ZIP nao escreve no computador: nada a restaurar ali."""
        projeto = tmp_path / "loja-acessibilidade"
        projeto.mkdir()
        alvo = projeto / "index.html"
        alvo.write_text(_CORRIGIDO, encoding="utf-8")

        fix_checkpoint_store.create_checkpoint("Correção de 1 arquivo(s)")
        fix_checkpoint_store.restore_checkpoint()

        assert alvo.read_text(encoding="utf-8") == _CORRIGIDO

    def test_backup_apagado_nao_derruba_o_desfazer(self, tmp_path):
        """Best-effort: sem o backup em disco o undo dos caches ainda vale."""
        projeto = tmp_path / "loja-acessibilidade"
        projeto.mkdir()
        (projeto / "index.html").write_text(_CORRIGIDO, encoding="utf-8")

        fix_checkpoint_store.create_checkpoint("local", project_dir=str(projeto), backup_dir=str(tmp_path / "sumiu"))
        assert fix_checkpoint_store.restore_checkpoint() is not None
        assert (projeto / "index.html").read_text(encoding="utf-8") == _CORRIGIDO

    def test_describe_menciona_o_projeto_local(self, tmp_path):
        cp = fix_checkpoint_store.create_checkpoint(
            "Correção local", project_dir=str(tmp_path / "loja-acessibilidade"), backup_dir=str(tmp_path)
        )
        assert "loja-acessibilidade" in cp.describe()
        fix_checkpoint_store.restore_checkpoint()

    def test_arquivo_novo_criado_pela_correcao_nao_e_apagado(self, tmp_path):
        """O undo repoe os originais; nao tenta adivinhar o que foi criado."""
        projeto, backup = _projeto_com_backup(tmp_path)
        extra = projeto / "novo.css"
        extra.write_text("a{}", encoding="utf-8")

        fix_checkpoint_store.create_checkpoint("local", project_dir=str(projeto), backup_dir=str(backup))
        fix_checkpoint_store.restore_checkpoint()

        assert (projeto / "index.html").read_text(encoding="utf-8") == _ORIGINAL
        assert os.path.exists(extra)
