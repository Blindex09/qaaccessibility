import json

import pytest

from backend.src.services.a11y_domain_tools import (
    A11Y_TOOLSET,
    compute_contrast,
    contrast_ratio,
    parse_color,
    register_a11y_tools,
)


class TestParseColor:
    def test_hex_short(self) -> None:
        assert parse_color("#fff") == (255, 255, 255)
        assert parse_color("#000") == (0, 0, 0)

    def test_hex_long(self) -> None:
        assert parse_color("#777777") == (119, 119, 119)
        assert parse_color("#1A2B3C") == (26, 43, 60)

    def test_rgb_and_rgba(self) -> None:
        assert parse_color("rgb(119,119,119)") == (119, 119, 119)
        assert parse_color("rgba(0, 0, 0, 0.5)") == (0, 0, 0)

    def test_named(self) -> None:
        assert parse_color("white") == (255, 255, 255)
        assert parse_color("BLACK") == (0, 0, 0)

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_color("not-a-color")
        with pytest.raises(ValueError):
            parse_color("#12")


class TestContrastRatio:
    def test_black_on_white_is_max(self) -> None:
        assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0

    def test_same_color_is_one(self) -> None:
        assert round(contrast_ratio("#123456", "#123456"), 1) == 1.0


class TestComputeContrastTool:
    def test_missing_args_returns_error(self) -> None:
        out = json.loads(compute_contrast({}))
        assert "error" in out

    def test_invalid_color_returns_error(self) -> None:
        out = json.loads(compute_contrast({"foreground": "invalid", "background": "#fff"}))
        assert "error" in out

    def test_valid_contrast_payload(self) -> None:
        out = json.loads(compute_contrast({"foreground": "#000", "background": "#fff"}))
        assert out["ratio"] == 21.0
        assert out["passes_aa_normal"] is True
        assert out["passes_aaa_normal"] is True

    def test_register_a11y_tools_executes(self) -> None:
        register_a11y_tools()
        assert A11Y_TOOLSET == "a11y_tools"
