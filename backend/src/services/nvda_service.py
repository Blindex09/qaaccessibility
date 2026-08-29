"""
nvda_service.py
Módulo de integração com a API oficial do leitor de tela NVDA no Windows.

Utiliza a DLL oficial nvdaControllerClient.dll via ctypes (versão 2.0).
Se a DLL não estiver presente ou o sistema não for Windows, o módulo
fornece um fallback simulado gracioso (mock), garantindo 100% de estabilidade.

Funções da DLL suportadas:
- nvdaController_testIfRunning()
- nvdaController_speakText(text)
- nvdaController_cancelSpeech()
- nvdaController_brailleMessage(text)
"""

import ctypes
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_dll_instance = None
_is_available = False


def _init_nvda_dll() -> None:
    """Tenta carregar a DLL oficial do NVDA controller no Windows."""
    global _dll_instance, _is_available
    if _dll_instance is not None or _is_available:
        return

    if sys.platform != "win32":
        logger.info("[NVDA Service] Sistema operacional não-Windows. Usando modo simulado.")
        return

    # Procura a DLL em caminhos conhecidos do projeto
    base_dir = os.path.dirname(__file__)
    possible_paths = [
        os.path.join(base_dir, "..", "resources", "nvdaControllerClient.dll"),
        os.path.join(base_dir, "..", "resources", "nvdaControllerClient64.dll"),
        "nvdaControllerClient.dll",
    ]

    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            try:
                _dll_instance = ctypes.windll.LoadLibrary(abs_path)
                res = _dll_instance.nvdaController_testIfRunning()
                _is_available = res == 0
                logger.info("[NVDA Service] DLL carregada com sucesso (%s). NVDA rodando: %s", abs_path, _is_available)
                return
            except Exception as exc:
                logger.warning("[NVDA Service] Falha ao carregar DLL em %s: %s", abs_path, exc)

    logger.info("[NVDA Service] DLL nvdaControllerClient.dll não encontrada. Modo simulado ativo.")


def is_nvda_running() -> bool:
    """Verifica se o leitor de tela NVDA está em execução."""
    _init_nvda_dll()
    if _dll_instance and hasattr(_dll_instance, "nvdaController_testIfRunning"):
        try:
            return _dll_instance.nvdaController_testIfRunning() == 0
        except Exception:
            return False
    return False


def speak_text(text: str) -> dict[str, Any]:
    """
    Envia uma instrução de texto para ser falada pelo NVDA.
    Retorna o status da operação.
    """
    _init_nvda_dll()
    if not text:
        return {"status": "error", "error": "Texto vazio."}

    if _dll_instance and is_nvda_running():
        try:
            res = _dll_instance.nvdaController_speakText(text)
            if res == 0:
                logger.info("[NVDA Service] Texto falado pelo NVDA: %s", text[:60])
                return {"status": "ok", "spoken": True, "text": text}
        except Exception as exc:
            logger.error("[NVDA Service] Erro ao enviar fala para o NVDA: %s", exc)

    # Fallback simulado se o NVDA não estiver rodando ou DLL ausente
    logger.info("[NVDA Service:Simulado] Falando texto: %s", text[:60])
    return {"status": "simulated", "spoken": False, "text": text}


def cancel_speech() -> dict[str, Any]:
    """Cancela a fala atual do NVDA."""
    _init_nvda_dll()
    if _dll_instance and is_nvda_running():
        try:
            _dll_instance.nvdaController_cancelSpeech()
            return {"status": "ok", "cancelled": True}
        except Exception as exc:
            logger.error("[NVDA Service] Erro ao cancelar fala: %s", exc)
    return {"status": "simulated", "cancelled": False}


def braille_message(text: str) -> dict[str, Any]:
    """Exibe uma mensagem na linha Braille do NVDA."""
    _init_nvda_dll()
    if _dll_instance and is_nvda_running():
        try:
            res = _dll_instance.nvdaController_brailleMessage(text)
            if res == 0:
                return {"status": "ok", "braille": True, "text": text}
        except Exception as exc:
            logger.error("[NVDA Service] Erro ao enviar Braille: %s", exc)
    return {"status": "simulated", "braille": False, "text": text}
