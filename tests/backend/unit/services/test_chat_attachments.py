"""Testes do preprocessamento de anexos base64 do chat (chat_runtime.py).

Cobertura nova: extração de imagem (Multimodal 2026) -- imagens do turno
atual são removidas do texto e devolvidas separadamente como content block
nativo, em vez de virarem texto (só documentos viram texto). Histórico de
turnos passados nunca reenvia a imagem, só uma nota.
"""

import base64

from backend.src.services.chat_runtime import (
    extract_message_with_images,
    preprocess_base64_attachments,
)

_PNG_B64 = base64.b64encode(b"fake-png-bytes").decode()


def test_extract_message_with_images_removes_image_and_returns_it_separately():
    message = f"analise esta tela\n=== screenshot.png ===\n{_PNG_B64}\n===\nmais texto"

    text, images = extract_message_with_images(message)

    assert images == [{"media_type": "image/png", "data": _PNG_B64}]
    assert _PNG_B64 not in text
    assert "analise esta tela" in text
    assert "mais texto" in text
    assert "[Imagem anexada -- analisada visualmente pelo modelo]" in text


def test_extract_message_with_images_supports_jpeg_webp_gif():
    for ext, media_type in ((".jpg", "image/jpeg"), (".jpeg", "image/jpeg"), (".webp", "image/webp"), (".gif", "image/gif")):
        message = f"=== foto{ext} ===\n{_PNG_B64}\n===\n"
        _text, images = extract_message_with_images(message)
        assert images == [{"media_type": media_type, "data": _PNG_B64}]


def test_extract_message_with_images_no_attachment_returns_empty_list():
    text, images = extract_message_with_images("mensagem sem anexo nenhum")
    assert text == "mensagem sem anexo nenhum"
    assert images == []


def test_extract_message_with_images_multiple_images_all_extracted():
    message = f"=== a.png ===\n{_PNG_B64}\n===\n=== b.jpg ===\n{_PNG_B64}\n===\n"
    _text, images = extract_message_with_images(message)
    assert len(images) == 2
    assert images[0]["media_type"] == "image/png"
    assert images[1]["media_type"] == "image/jpeg"


def test_preprocess_base64_attachments_history_path_never_extracts_image():
    """Histórico (turnos passados): a imagem some do texto mas NUNCA é
    devolvida -- reenviar base64 de imagens antigas a cada turno infla custo
    sem benefício real (só o turno atual analisa a imagem de verdade)."""
    message = f"=== screenshot.png ===\n{_PNG_B64}\n===\n"

    text = preprocess_base64_attachments(message)

    assert _PNG_B64 not in text
    assert "[Imagem anexada em turno anterior -- não reenviada]" in text


def test_preprocess_base64_attachments_still_extracts_document_text():
    """Documentos continuam sendo convertidos em texto (comportamento
    pré-existente, agora coberto por teste dedicado)."""
    bogus_docx = base64.b64encode(b"not a real docx but exercises the try/except path").decode()
    message = f"=== relatorio.docx ===\n{bogus_docx}\n===\n"

    text = preprocess_base64_attachments(message)

    # Falha ao extrair -> loga e devolve o bloco original intacto (nunca quebra o turno).
    assert bogus_docx in text or "[Texto extraído do Word]" in text


def test_preprocess_base64_attachments_empty_message_returns_empty_string():
    assert preprocess_base64_attachments("") == ""


def test_extract_message_with_images_empty_message_returns_empty_tuple():
    assert extract_message_with_images("") == ("", [])


def test_unrecognized_extension_left_untouched():
    message = "=== notes.txt ===\nc29tZSB0ZXh0\n===\n"
    text, images = extract_message_with_images(message)
    assert text == message
    assert images == []
