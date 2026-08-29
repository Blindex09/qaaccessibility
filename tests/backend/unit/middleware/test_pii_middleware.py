import json

from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.src.middleware.pii_middleware import PIIRedactionMiddleware


def _build_app(handler, path="/x"):
    app = Starlette(routes=[Route(path, handler)])
    app.add_middleware(PIIRedactionMiddleware)
    return TestClient(app)


class TestPIIRedactionMiddleware:
    def test_json_response_with_email_gets_redacted(self):
        # Regression test: the actual redaction-triggered branches (JSON-success path
        # and the str-chunk decode path) had zero test coverage -- this proves the
        # feature really redacts, not just that the detector function exists.
        async def handler(request):
            return JSONResponse({"message": "Contact me at user@example.com please"})

        client = _build_app(handler)
        resp = client.get("/x")
        assert resp.status_code == 200
        data = resp.json()
        assert "user@example.com" not in data["message"]
        assert "[REDACTED]" in data["message"]

    def test_json_response_with_cpf_in_nested_structure_gets_redacted(self):
        async def handler(request):
            return JSONResponse({"nested": {"items": [{"note": "CPF: 123.456.789-01"}]}})

        client = _build_app(handler)
        resp = client.get("/x")
        data = resp.json()
        assert "123.456.789-01" not in json.dumps(data)
        assert "[REDACTED]" in data["nested"]["items"][0]["note"]

    def test_json_response_without_pii_passes_through_unchanged(self):
        async def handler(request):
            return JSONResponse({"message": "No secrets here"})

        client = _build_app(handler)
        resp = client.get("/x")
        assert resp.json() == {"message": "No secrets here"}

    def test_non_json_response_is_never_scanned(self):
        # Documents the known, real gap found in audit: text/html (and any non-JSON
        # response, e.g. routes/preview.py) is skipped entirely by this middleware.
        async def handler(request):
            return PlainTextResponse(
                "Contact user@example.com", media_type="text/html"
            )

        client = _build_app(handler)
        resp = client.get("/x")
        assert "user@example.com" in resp.text

    def test_malformed_json_falls_back_to_raw_text_redaction(self):
        # Exercises the fallback branch (json.JSONDecodeError) by returning a body
        # that declares application/json but is not valid JSON.
        async def handler(request):
            from starlette.responses import Response
            return Response(
                content="not actually json but has user@example.com in it",
                media_type="application/json",
            )

        client = _build_app(handler)
        resp = client.get("/x")
        assert "user@example.com" not in resp.text
        assert "[REDACTED]" in resp.text
