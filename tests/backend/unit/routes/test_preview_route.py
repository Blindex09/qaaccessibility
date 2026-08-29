class TestPreviewRoute:
    def _create_session(self, client, html: str) -> str:
        resp = client.post("/preview/create", json={
            "pages": [{"title": "Home", "original_html": html, "fixed_html": html}],
        })
        assert resp.status_code == 200
        return resp.json()["session_id"]

    def test_unknown_session_returns_404(self, client):
        resp = client.get("/preview/render/does-not-exist/0")
        assert resp.status_code == 404

    def test_invalid_page_index_returns_400(self, client):
        session_id = self._create_session(client, "<html><head></head><body>ok</body></html>")
        resp = client.get(f"/preview/render/{session_id}/5")
        assert resp.status_code == 400

    def test_script_tag_is_stripped(self, client):
        # Regression test: routes/preview.py used to serve user/LLM-analyzed HTML
        # verbatim on this app's own origin, with no sanitization at all.
        malicious = "<html><head></head><body><script>alert(document.cookie)</script>Hi</body></html>"
        session_id = self._create_session(client, malicious)
        resp = client.get(f"/preview/render/{session_id}/0")
        assert resp.status_code == 200
        assert "<script>alert(document.cookie)</script>" not in resp.text
        assert "alert(document.cookie)" not in resp.text
        assert "Hi" in resp.text  # legitimate content survives

    def test_event_handler_attribute_is_stripped(self, client):
        malicious = '<html><head></head><body><img src="x.png" onerror="alert(1)"></body></html>'
        session_id = self._create_session(client, malicious)
        resp = client.get(f"/preview/render/{session_id}/0")
        assert resp.status_code == 200
        assert "onerror" not in resp.text

    def test_javascript_href_is_stripped(self, client):
        malicious = '<html><head></head><body><a href="javascript:alert(1)">click</a></body></html>'
        session_id = self._create_session(client, malicious)
        resp = client.get(f"/preview/render/{session_id}/0")
        assert resp.status_code == 200
        assert "javascript:" not in resp.text

    def test_response_has_restrictive_csp_not_overwritten_by_global_default(self, client):
        # Regression test: the global SecurityHeadersMiddleware used to unconditionally
        # overwrite response.headers["Content-Security-Policy"] on every response,
        # silently discarding any stricter CSP a route set for itself.
        session_id = self._create_session(client, "<html><head></head><body>ok</body></html>")
        resp = client.get(f"/preview/render/{session_id}/0")
        csp = resp.headers.get("content-security-policy", "")
        assert "script-src 'sha256-" in csp
        assert "object-src 'none'" in csp

    def test_accessible_highlight_style_still_injected(self, client):
        html = "<html><head></head><body><p data-a11y-fixed='true'>Fixed</p></body></html>"
        session_id = self._create_session(client, html)
        resp = client.get(f"/preview/render/{session_id}/0")
        assert resp.status_code == 200
        assert "a11y-preview-style" in resp.text

    def test_preview_render_allows_iframe_embedding(self, client):
        # Regression test: the preview endpoint must be embeddable by the frontend
        # in an iframe. The global SecurityHeadersMiddleware used to inject
        # X-Frame-Options: DENY and frame-ancestors 'none' for every route,
        # which blocked the Live Preview iframe from loading.
        html = "<html><head></head><body>ok</body></html>"
        session_id = self._create_session(client, html)
        resp = client.get(f"/preview/render/{session_id}/0")
        assert resp.status_code == 200
        assert "x-frame-options" not in (k.lower() for k in resp.headers)
        csp = resp.headers.get("content-security-policy", "")
        assert "frame-ancestors" in csp
        assert "http://localhost:19006" in csp or "http://localhost:3000" in csp
