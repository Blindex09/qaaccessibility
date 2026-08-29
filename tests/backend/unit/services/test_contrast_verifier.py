from backend.src.services.contrast_verifier import extract_colors, verify_contrast_issues
from backend.src.shared.models import AccessibilityIssue, Guideline, Severity


def _issue(criterion: str, text: str, level: str | None = "AA", iid: str = "x-1") -> AccessibilityIssue:
    return AccessibilityIssue(
        id=iid,
        guideline=Guideline.WCAG_2_2,
        criterion=criterion,
        severity=Severity.HIGH,
        element="<p>",
        description=text,
        suggestion="fix it",
        level=level,
    )


class TestExtractColors:
    def test_hex_and_rgb(self) -> None:
        colors = extract_colors("color #777777 over rgb(255,255,255) background")
        assert colors == [(119, 119, 119), (255, 255, 255)]

    def test_dedup_and_short_hex(self) -> None:
        colors = extract_colors("#fff and #ffffff and #000")
        assert colors == [(255, 255, 255), (0, 0, 0)]

    def test_none(self) -> None:
        assert extract_colors("no colors here") == []


class TestVerifyContrastIssues:
    def test_real_violation_kept_and_annotated(self) -> None:
        # #777 em #fff ~ 4.48 < 4.5 -> violacao real, mantida + anotada
        issues = [_issue("1.4.3 Contrast (Minimum)", "text #777777 on #ffffff")]
        kept, removed = verify_contrast_issues(issues)
        assert removed == 0
        assert len(kept) == 1
        assert "Contraste verificado" in (kept[0].why_technical or "")

    def test_false_positive_removed(self) -> None:
        # #000 em #fff = 21 -> passa folgado, falso positivo removido
        issues = [_issue("1.4.3 Contrast (Minimum)", "text #000000 on #ffffff")]
        kept, removed = verify_contrast_issues(issues)
        assert removed == 1
        assert kept == []

    def test_non_text_contrast_threshold(self) -> None:
        # 1.4.11 usa limite 3.0; #767676 em #fff ~ 4.54 -> passa 3.0 -> removido
        issues = [_issue("1.4.11 Non-text Contrast", "border #767676 on #ffffff")]
        kept, removed = verify_contrast_issues(issues)
        assert removed == 1

    def test_three_colors_left_untouched(self) -> None:
        issues = [_issue("1.4.3 Contrast (Minimum)", "#000 #fff #777 ambiguous")]
        kept, removed = verify_contrast_issues(issues)
        assert removed == 0
        assert len(kept) == 1
        assert kept[0].why_technical is None  # não anotado (não verificavel)

    def test_non_contrast_issue_untouched(self) -> None:
        issues = [_issue("1.1.1 Non-text Content", "img #000 on #fff missing alt")]
        kept, removed = verify_contrast_issues(issues)
        assert removed == 0
        assert len(kept) == 1
        assert kept[0].why_technical is None

    def test_no_colors_untouched(self) -> None:
        issues = [_issue("1.4.3 Contrast (Minimum)", "low contrast text somewhere")]
        kept, removed = verify_contrast_issues(issues)
        assert removed == 0
        assert len(kept) == 1


class TestSourceCssPath:
    _STYLES = (
        "<!-- [STYLES] --> .muted{color:#777777;background:#ffffff;font-size:14px} "
        ".ok{color:#000000;background:#ffffff}"
    )

    def _issue_el(self, criterion: str, element: str) -> AccessibilityIssue:
        # issue SEM cores no texto, identificado pelo seletor no campo element
        return AccessibilityIssue(
            id="s-1",
            guideline=Guideline.WCAG_2_2,
            criterion=criterion,
            severity=Severity.HIGH,
            element=element,
            description="contraste insuficiente",
            suggestion="ajustar cor",
            level="AA",
        )

    def test_source_annotates_real_violation(self) -> None:
        # .muted = #777/#fff ~ 4.48 < 4.5 -> anota via CSS, não remove
        issues = [self._issue_el("1.4.3 Contrast (Minimum)", '<p class="muted">')]
        kept, removed = verify_contrast_issues(issues, source_html=self._STYLES)
        assert removed == 0
        assert "Contraste verificado (CSS)" in (kept[0].why_technical or "")

    def test_source_never_drops_even_if_passes(self) -> None:
        # .ok = #000/#fff = 21 (passa), mas caminho CSS NUNCA remove
        issues = [self._issue_el("1.4.3 Contrast (Minimum)", '<p class="ok">')]
        kept, removed = verify_contrast_issues(issues, source_html=self._STYLES)
        assert removed == 0
        assert len(kept) == 1
        assert kept[0].why_technical is None  # não anota quando passa

    def test_source_ambiguous_selector_no_annotation(self) -> None:
        # elemento casa as duas regras (.muted e .ok) -> ambiguo -> sem anotacao
        issues = [self._issue_el("1.4.3 Contrast (Minimum)", '<p class="muted ok">')]
        kept, removed = verify_contrast_issues(issues, source_html=self._STYLES)
        assert removed == 0
        assert kept[0].why_technical is None

    def test_source_no_selector_match(self) -> None:
        issues = [self._issue_el("1.4.3 Contrast (Minimum)", '<p class="other">')]
        kept, removed = verify_contrast_issues(issues, source_html=self._STYLES)
        assert removed == 0
        assert kept[0].why_technical is None


class TestComplexBackgrounds:
    def test_complex_bg_via_data_attribute_never_removed(self) -> None:
        # data-complex-bg presente -> não remove, mesmo passando (#000/#fff ratio=21)
        issue = AccessibilityIssue(
            id="x-c1",
            guideline=Guideline.WCAG_2_2,
            criterion="1.4.3 Contrast (Minimum)",
            severity=Severity.HIGH,
            element='<button class="ok" data-complex-bg="true">',
            description="text #000000 on #ffffff",
            suggestion="fix it",
            level="AA",
        )
        kept, removed = verify_contrast_issues([issue])
        assert removed == 0
        assert len(kept) == 1
        assert "Revisão manual recomendada" in (kept[0].why_technical or "")

    def test_complex_bg_via_css_gradient_never_removed(self) -> None:
        # linear-gradient na regra CSS -> não remove, mesmo passando
        issue = AccessibilityIssue(
            id="x-c2",
            guideline=Guideline.WCAG_2_2,
            criterion="1.4.3 Contrast (Minimum)",
            severity=Severity.HIGH,
            element='<p class="grad">',
            description="text #000000 on #ffffff",
            suggestion="fix it",
            level="AA",
        )
        styles = "<!-- [STYLES] --> .grad { color:#000000; background: linear-gradient(red, yellow); }"
        kept, removed = verify_contrast_issues([issue], source_html=styles)
        assert removed == 0
        assert len(kept) == 1
        assert "Revisão manual recomendada" in (kept[0].why_technical or "")

    def test_complex_bg_via_css_opacity_never_removed(self) -> None:
        # opacity na regra CSS -> não remove, mesmo passando
        issue = AccessibilityIssue(
            id="x-c3",
            guideline=Guideline.WCAG_2_2,
            criterion="1.4.3 Contrast (Minimum)",
            severity=Severity.HIGH,
            element='<span class="opaque">',
            description="text #000000 on #ffffff",
            suggestion="fix it",
            level="AA",
        )
        styles = "<!-- [STYLES] --> .opaque { color:#000000; opacity: 0.5; }"
        kept, removed = verify_contrast_issues([issue], source_html=styles)
        assert removed == 0
        assert len(kept) == 1
        assert "Revisão manual recomendada" in (kept[0].why_technical or "")
