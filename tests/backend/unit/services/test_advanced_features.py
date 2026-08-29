import contextlib
import io
import os
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from backend.src.routes.analyze import _get_cache_path, _load_cache, _md5, _save_cache
from backend.src.services.chat_tools import _read_epub_text, _read_pdf_text


class TestAdvancedFeatures(unittest.TestCase):
    def test_read_epub_text_basic(self):
        # Cria um arquivo EPUB em memória
        epub_data = io.BytesIO()
        with zipfile.ZipFile(epub_data, "w") as z:
            # 1. content.opf
            opf_content = """<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Livro Teste</dc:title>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""
            z.writestr("OEBPS/content.opf", opf_content)
            # 2. text/ch1.xhtml
            ch1_content = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>Capítulo Um</h1>
    <p>Olá Mundo da Acessibilidade!</p>
  </body>
</html>
"""
            z.writestr("OEBPS/text/ch1.xhtml", ch1_content)

        epub_data.seek(0)
        extracted = _read_epub_text(epub_data)
        self.assertIn("Capítulo Um", extracted)
        self.assertIn("Olá Mundo da Acessibilidade!", extracted)

    @patch("pypdf.PdfReader")
    def test_read_pdf_text_with_form_fields(self, mock_reader_class):
        # Configura o mock do PdfReader para simular campos de formulário e páginas
        mock_reader = MagicMock()
        mock_reader_class.return_value = mock_reader

        # Simula campos de formulário
        mock_reader.get_fields.return_value = {
            "nome_locador": {"/FT": "/Tx"},
            "aceito_termos": {"/FT": "/Btn"}
        }

        # Simula páginas do PDF
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Contrato de Aluguel..."
        mock_reader.pages = [mock_page]

        file_mock = MagicMock()
        file_mock.read.return_value = b"%PDF-1.4 dummy data"

        extracted = _read_pdf_text(file_mock)

        self.assertIn("Campos de Formulário Interativos Nativos", extracted)
        self.assertIn("- nome_locador (Campo de Texto)", extracted)
        self.assertIn("- aceito_termos (Caixa de Selecao/Opcao)", extracted)
        self.assertIn("Contrato de Aluguel...", extracted)

    def test_caching_helpers(self):
        # Testa o carregamento e salvamento de cache em arquivo temporário
        cache_data = {
            "file1.html": {"hash": "abc", "issues": [{"id": 1, "desc": "Erro"}]}
        }

        # Salva
        _save_cache(cache_data)

        # Carrega
        loaded = _load_cache()
        self.assertIn("file1.html", loaded)
        self.assertEqual(loaded["file1.html"]["hash"], "abc")

        # MD5 helper
        self.assertEqual(_md5("test"), "098f6bcd4621d373cade4e832627b4f6")

        # Cleanup
        with contextlib.suppress(Exception):
            os.remove(_get_cache_path())

if __name__ == "__main__":
    unittest.main()
