import pytest

from backend.src.services.local_project_guard import (
    accessibility_scope_denial_message,
    is_accessibility_project_dir,
)


class TestIsAccessibilityProjectDir:
    @pytest.mark.parametrize("path", [
        r"C:\Users\felipe\projetos\meu-projeto-acessibilidade",
        r"C:\dev\accessibility-app",
        r"C:\dev\a11y-widgets",
        "/home/user/projects/acessivel",
        r"C:\Users\felipe\Documents\Acessibilidade\loja",
        "acess-checker",
    ])
    def test_recognizes_accessibility_named_paths(self, path):
        assert is_accessibility_project_dir(path) is True

    @pytest.mark.parametrize("path", [
        r"C:\Users\felipe\projetos\loja-online",
        r"C:\dev\my-react-app",
        "/home/user/projects/dashboard",
        r"C:\Users\felipe\Documents\banco",
        "",
    ])
    def test_rejects_unrelated_paths(self, path):
        assert is_accessibility_project_dir(path) is False

    def test_case_insensitive(self):
        assert is_accessibility_project_dir(r"C:\Dev\ACESSIBILIDADE-App") is True

    def test_matches_any_path_segment_not_just_last(self):
        assert is_accessibility_project_dir(r"C:\Acessibilidade\clientes\loja-x") is True


class TestAccessibilityScopeDenialMessage:
    def test_message_mentions_the_path(self):
        msg = accessibility_scope_denial_message(r"C:\dev\loja-online")
        assert "loja-online" in msg

    def test_message_is_friendly_not_a_stack_trace(self):
        msg = accessibility_scope_denial_message(r"C:\dev\loja-online")
        assert "Traceback" not in msg
        assert "acessibilidade" in msg.lower()
