from backend.src.security.pii_guard import contains_pii, redact_pii


class TestContainsPii:
    def test_detects_ssn(self):
        assert contains_pii("SSN: 123-45-6789") is True

    def test_detects_cpf(self):
        assert contains_pii("CPF: 123.456.789-09") is True

    def test_detects_email(self):
        assert contains_pii("Contact: user@example.com") is True

    def test_clean_text_returns_false(self):
        assert contains_pii("The page has no alt text.") is False

    def test_empty_string_returns_false(self):
        assert contains_pii("") is False


class TestRedactPii:
    def test_redacts_email(self):
        result = redact_pii("Email: user@example.com here")
        assert "user@example.com" not in result
        assert "[REDACTED]" in result

    def test_redacts_cpf(self):
        result = redact_pii("CPF: 123.456.789-09")
        assert "123.456.789-09" not in result

    def test_clean_text_unchanged(self):
        text = "No personal data here."
        assert redact_pii(text) == text

    def test_multiple_pii_all_redacted(self):
        text = "Email: a@b.com SSN: 123-45-6789"
        result = redact_pii(text)
        assert "a@b.com" not in result
        assert "123-45-6789" not in result
