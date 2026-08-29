from unittest.mock import MagicMock, patch

from backend.src.services import nvda_service


def _reset_module_state():
    nvda_service._dll_instance = None
    nvda_service._is_available = False


class TestInitNvdaDll:
    def test_non_windows_platform_uses_simulated_mode(self):
        _reset_module_state()
        with patch("backend.src.services.nvda_service.sys.platform", "linux"):
            nvda_service._init_nvda_dll()
        assert nvda_service._dll_instance is None
        assert nvda_service._is_available is False

    def test_dll_load_exception_falls_back_to_simulated_mode(self):
        _reset_module_state()
        with patch("backend.src.services.nvda_service.sys.platform", "win32"), \
             patch("backend.src.services.nvda_service.os.path.exists", return_value=True), \
             patch("backend.src.services.nvda_service.ctypes.windll.LoadLibrary", side_effect=OSError("dll missing")):
            nvda_service._init_nvda_dll()
        assert nvda_service._dll_instance is None
        assert nvda_service._is_available is False

    def test_already_initialized_short_circuits(self):
        _reset_module_state()
        nvda_service._is_available = True
        with patch("backend.src.services.nvda_service.sys.platform", "win32"):
            nvda_service._init_nvda_dll()
        # retorno antecipado: _is_available continua True, nada foi reinicializado
        assert nvda_service._is_available is True
        _reset_module_state()


class TestIsNvdaRunning:
    def test_returns_false_when_dll_unavailable(self):
        _reset_module_state()
        with patch("backend.src.services.nvda_service._init_nvda_dll"):
            assert nvda_service.is_nvda_running() is False

    def test_returns_true_when_dll_reports_running(self):
        _reset_module_state()
        mock_dll = MagicMock()
        mock_dll.nvdaController_testIfRunning.return_value = 0
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"):
            assert nvda_service.is_nvda_running() is True
        _reset_module_state()

    def test_exception_calling_dll_returns_false(self):
        _reset_module_state()
        mock_dll = MagicMock()
        mock_dll.nvdaController_testIfRunning.side_effect = RuntimeError("dll error")
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"):
            assert nvda_service.is_nvda_running() is False
        _reset_module_state()


class TestSpeakText:
    def test_empty_text_returns_error_without_touching_dll(self):
        _reset_module_state()
        with patch("backend.src.services.nvda_service._init_nvda_dll"):
            result = nvda_service.speak_text("")
        assert result == {"status": "error", "error": "Texto vazio."}

    def test_dll_available_and_running_speaks_successfully(self):
        _reset_module_state()
        mock_dll = MagicMock()
        mock_dll.nvdaController_speakText.return_value = 0
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"), \
             patch("backend.src.services.nvda_service.is_nvda_running", return_value=True):
            result = nvda_service.speak_text("olá mundo")
        assert result == {"status": "ok", "spoken": True, "text": "olá mundo"}
        _reset_module_state()

    def test_dll_exception_falls_back_to_simulated(self):
        _reset_module_state()
        mock_dll = MagicMock()
        mock_dll.nvdaController_speakText.side_effect = RuntimeError("speak failed")
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"), \
             patch("backend.src.services.nvda_service.is_nvda_running", return_value=True):
            result = nvda_service.speak_text("texto")
        assert result == {"status": "simulated", "spoken": False, "text": "texto"}
        _reset_module_state()

    def test_no_dll_returns_simulated(self):
        _reset_module_state()
        with patch("backend.src.services.nvda_service._init_nvda_dll"):
            result = nvda_service.speak_text("texto")
        assert result == {"status": "simulated", "spoken": False, "text": "texto"}


class TestCancelSpeech:
    def test_dll_available_cancels_successfully(self):
        _reset_module_state()
        mock_dll = MagicMock()
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"), \
             patch("backend.src.services.nvda_service.is_nvda_running", return_value=True):
            result = nvda_service.cancel_speech()
        assert result == {"status": "ok", "cancelled": True}
        mock_dll.nvdaController_cancelSpeech.assert_called_once()
        _reset_module_state()

    def test_dll_exception_falls_back_to_simulated(self):
        _reset_module_state()
        mock_dll = MagicMock()
        mock_dll.nvdaController_cancelSpeech.side_effect = RuntimeError("cancel failed")
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"), \
             patch("backend.src.services.nvda_service.is_nvda_running", return_value=True):
            result = nvda_service.cancel_speech()
        assert result == {"status": "simulated", "cancelled": False}
        _reset_module_state()

    def test_no_dll_returns_simulated(self):
        _reset_module_state()
        with patch("backend.src.services.nvda_service._init_nvda_dll"):
            result = nvda_service.cancel_speech()
        assert result == {"status": "simulated", "cancelled": False}


class TestBrailleMessage:
    def test_dll_available_sends_braille_successfully(self):
        _reset_module_state()
        mock_dll = MagicMock()
        mock_dll.nvdaController_brailleMessage.return_value = 0
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"), \
             patch("backend.src.services.nvda_service.is_nvda_running", return_value=True):
            result = nvda_service.braille_message("mensagem")
        assert result == {"status": "ok", "braille": True, "text": "mensagem"}
        _reset_module_state()

    def test_dll_exception_falls_back_to_simulated(self):
        _reset_module_state()
        mock_dll = MagicMock()
        mock_dll.nvdaController_brailleMessage.side_effect = RuntimeError("braille failed")
        nvda_service._dll_instance = mock_dll
        with patch("backend.src.services.nvda_service._init_nvda_dll"), \
             patch("backend.src.services.nvda_service.is_nvda_running", return_value=True):
            result = nvda_service.braille_message("mensagem")
        assert result == {"status": "simulated", "braille": False, "text": "mensagem"}
        _reset_module_state()

    def test_no_dll_returns_simulated(self):
        _reset_module_state()
        with patch("backend.src.services.nvda_service._init_nvda_dll"):
            result = nvda_service.braille_message("mensagem")
        assert result == {"status": "simulated", "braille": False, "text": "mensagem"}
