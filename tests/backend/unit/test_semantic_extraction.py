"""
Unit tests for _extract_semantic_html() in routes/analyze.py.

Validates that the extractor correctly produces the three structured sections
needed by all 16 specialist agents:
  [PAGE CONTEXT] — html lang, title, meta tags
  [STYLES]       — embedded CSS blocks
  [ELEMENTS]     — a11y-relevant elements from the full DOM
"""

from backend.src.routes.analyze import _extract_semantic_html


class TestPageContext:
    """[PAGE CONTEXT] section must capture head-level a11y attributes."""

    def test_html_lang_extracted(self) -> None:
        html = '<html lang="pt-BR"><head></head><body><p>Test</p></body></html>'
        result = _extract_semantic_html(html)
        assert 'lang="pt-BR"' in result

    def test_html_lang_missing_shows_empty(self) -> None:
        html = "<html><head></head><body><p>Test</p></body></html>"
        result = _extract_semantic_html(html)
        assert '<html lang="">' in result

    def test_title_extracted(self) -> None:
        html = "<html><head><title>Minha Página</title></head><body><main></main></body></html>"
        result = _extract_semantic_html(html)
        assert "<title>Minha Página</title>" in result

    def test_empty_title_detected(self) -> None:
        html = "<html><head><title></title></head><body></body></html>"
        result = _extract_semantic_html(html)
        assert "<title></title>" in result

    def test_meta_viewport_extracted(self) -> None:
        html = (
            "<html><head>"
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            "</head><body></body></html>"
        )
        result = _extract_semantic_html(html)
        assert "viewport" in result
        assert "width=device-width" in result

    def test_page_context_section_header_present(self) -> None:
        html = '<html lang="en"><head><title>Test</title></head><body></body></html>'
        result = _extract_semantic_html(html)
        assert "<!-- [PAGE CONTEXT] -->" in result


class TestStylesSection:
    """[STYLES] section must capture embedded CSS for css_analyzer."""

    def test_embedded_style_block_captured(self) -> None:
        html = (
            "<html><head>"
            "<style>button { outline: none; color: #fff; background: #fff; }</style>"
            "</head><body><button>Click</button></body></html>"
        )
        result = _extract_semantic_html(html)
        assert "<!-- [STYLES] -->" in result
        assert "outline: none" in result

    def test_no_styles_section_absent(self) -> None:
        html = "<html><head></head><body><p>Hello</p></body></html>"
        result = _extract_semantic_html(html)
        assert "<!-- [STYLES] -->" not in result

    def test_script_tags_not_in_output(self) -> None:
        """Scripts are stripped — ajax_dynamic reads inline event handlers instead."""
        html = (
            "<html><head></head><body>"
            "<script>fetch('/api').then(r => r.json())</script>"
            '<button onclick="loadData()">Load</button>'
            "</body></html>"
        )
        result = _extract_semantic_html(html)
        assert "fetch('/api')" not in result  # script stripped
        assert "loadData" in result  # inline handler preserved on element


class TestElementsSection:
    """[ELEMENTS] section must capture all a11y-relevant elements."""

    def test_images_extracted(self) -> None:
        html = '<html><body><img src="logo.png"><img src="deco.png" alt=""></body></html>'
        result = _extract_semantic_html(html)
        assert "logo.png" in result
        assert "<!-- [ELEMENTS] -->" in result

    def test_iframe_not_stripped(self) -> None:
        """iframes must be present so wcag_semantics can detect missing title attribute."""
        html = '<html><body><iframe src="video.html"></iframe></body></html>'
        result = _extract_semantic_html(html)
        assert "<iframe" in result

    def test_iframe_with_title_preserved(self) -> None:
        html = '<html><body><iframe src="x.html" title="Training video"></iframe></body></html>'
        result = _extract_semantic_html(html)
        assert 'title="Training video"' in result

    def test_lists_extracted(self) -> None:
        html = "<html><body><ul><li>Item 1</li><li>Item 2</li></ul></body></html>"
        result = _extract_semantic_html(html)
        assert "<ul" in result

    def test_ordered_list_extracted(self) -> None:
        html = "<html><body><ol><li>Step 1</li></ol></body></html>"
        result = _extract_semantic_html(html)
        assert "<ol" in result

    def test_description_list_extracted(self) -> None:
        html = "<html><body><dl><dt>Term</dt><dd>Definition</dd></dl></body></html>"
        result = _extract_semantic_html(html)
        assert "<dl" in result

    def test_video_extracted(self) -> None:
        html = '<html><body><video src="movie.mp4" controls></video></body></html>'
        result = _extract_semantic_html(html)
        assert "<video" in result

    def test_audio_extracted(self) -> None:
        html = '<html><body><audio src="track.mp3" controls></audio></body></html>'
        result = _extract_semantic_html(html)
        assert "<audio" in result

    def test_track_captions_extracted(self) -> None:
        html = '<html><body><video><track kind="captions" src="captions.vtt" srclang="en"></video></body></html>'
        result = _extract_semantic_html(html)
        assert 'kind="captions"' in result

    def test_figure_figcaption_extracted(self) -> None:
        html = "<html><body><figure><img src='chart.png'><figcaption>Sales chart</figcaption></figure></body></html>"
        result = _extract_semantic_html(html)
        assert "<figure" in result

    def test_details_summary_extracted(self) -> None:
        html = "<html><body><details><summary>FAQ</summary><p>Answer</p></details></body></html>"
        result = _extract_semantic_html(html)
        assert "<details" in result
        assert "<summary" in result

    def test_form_elements_extracted(self) -> None:
        html = (
            "<html><body><form>"
            "<fieldset><legend>Contact</legend>"
            '<label for="email">Email</label>'
            '<input type="email" id="email" name="email">'
            "</fieldset></form></body></html>"
        )
        result = _extract_semantic_html(html)
        assert "<label" in result
        assert "<input" in result
        assert "<legend" in result

    def test_table_elements_extracted(self) -> None:
        html = (
            "<html><body><table>"
            "<caption>Pricing</caption>"
            "<thead><tr><th scope='col'>Plan</th><th scope='col'>Price</th></tr></thead>"
            "<tbody><tr><td>Basic</td><td>$10</td></tr></tbody>"
            "</table></body></html>"
        )
        result = _extract_semantic_html(html)
        assert "<table" in result
        assert "<caption" in result
        assert "<th" in result

    def test_aria_live_region_extracted(self) -> None:
        html = '<html><body><div aria-live="polite" id="status"></div></body></html>'
        result = _extract_semantic_html(html)
        assert 'aria-live="polite"' in result

    def test_role_attributes_preserved(self) -> None:
        html = '<html><body><div role="dialog" aria-labelledby="title"><h2 id="title">Login</h2></div></body></html>'
        result = _extract_semantic_html(html)
        assert 'role="dialog"' in result
        assert 'aria-labelledby="title"' in result

    def test_inline_style_a11y_props_preserved(self) -> None:
        """Inline style attributes are kept for CSS accessibility checks."""
        html = '<html><body><button style="outline: none; color: red;">X</button></body></html>'
        result = _extract_semantic_html(html)
        assert "outline" in result

    def test_large_html_does_not_exceed_limit(self) -> None:
        big_html = "<html><body>" + "<img src='img.png'>" * 2000 + "</body></html>"
        result = _extract_semantic_html(big_html)
        from backend.src.routes.analyze import _MAX_HTML_FOR_LLM

        assert len(result) <= _MAX_HTML_FOR_LLM * 1.1  # allow 10% for section headers

    def test_script_tags_stripped_entirely(self) -> None:
        html = "<html><head><script>alert('xss')</script></head><body></body></html>"
        result = _extract_semantic_html(html)
        assert "alert" not in result

    def test_fallback_on_empty_html(self) -> None:
        result = _extract_semantic_html("")
        assert isinstance(result, str)

    def test_section_header_elements_present(self) -> None:
        html = (
            '<html lang="en"><head><title>Page</title>'
            "<style>body { color: #333; }</style>"
            '</head><body><nav aria-label="Main"><a href="/">Home</a></nav>'
            "<main><h1>Hello</h1></main></body></html>"
        )
        result = _extract_semantic_html(html)
        assert "<!-- [PAGE CONTEXT] -->" in result
        assert "<!-- [STYLES] -->" in result
        assert "<!-- [ELEMENTS] -->" in result

    def test_accessibility_tree_section_present_when_provided(self) -> None:
        """Achado real (Task #25, 2026-08-11): quando a árvore de acessibilidade
        REAL (motor do navegador) está disponível, ela vira uma seção nova,
        distinta de [ELEMENTS] -- não é uma estimativa da IA a partir do HTML."""
        html = '<html lang="en"><head><title>Page</title></head><body><a href="/">Home</a></body></html>'
        tree_text = '- link: "Home"\n- link: (SEM NOME ACESSÍVEL)'
        result = _extract_semantic_html(html, accessibility_tree=tree_text)
        assert "<!-- [REAL ACCESSIBILITY TREE" in result
        assert tree_text in result

    def test_accessibility_tree_section_absent_when_not_provided(self) -> None:
        """Sem árvore real disponível (upload de arquivo, sem URL/navegação),
        a seção simplesmente não aparece -- nunca inventa uma."""
        html = '<html lang="en"><head><title>Page</title></head><body><a href="/">Home</a></body></html>'
        result = _extract_semantic_html(html)
        assert "[REAL ACCESSIBILITY TREE" not in result
