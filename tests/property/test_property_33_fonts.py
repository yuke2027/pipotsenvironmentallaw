"""Property 33: Chinese font fallback chooses the earliest usable file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st
from matplotlib.font_manager import FontProperties

from app.core.fonts import ChineseFontResolver

FAMILIES = (
    "Noto Sans CJK SC",
    "Microsoft YaHei",
    "SimHei",
    "WenQuanYi Zen Hei",
)


@dataclass(frozen=True)
class VirtualFont:
    path: Path
    family: str
    exists: bool
    has_cjk: bool


def _normalise(family: str) -> str:
    return " ".join(family.casefold().split())


def _expected_font(candidates: tuple[str, ...], fonts: tuple[VirtualFont, ...]) -> VirtualFont | None:
    grouped: dict[str, list[VirtualFont]] = {}
    usable = sorted(
        (font for font in fonts if font.exists and font.has_cjk),
        key=lambda font: str(font.path).casefold(),
    )
    for font in usable:
        grouped.setdefault(_normalise(font.family), []).append(font)
    for candidate in candidates:
        matches = grouped.get(_normalise(candidate), [])
        if matches:
            return matches[0]
    return None


@st.composite
def font_scenarios(draw: st.DrawFn) -> tuple[tuple[str, ...], tuple[VirtualFont, ...]]:
    candidates = tuple(draw(st.lists(st.sampled_from(FAMILIES), min_size=1, max_size=4)))
    if draw(st.booleans()):
        candidates = tuple(candidate.casefold() for candidate in candidates)
    fonts: list[VirtualFont] = []
    for index, family in enumerate(FAMILIES):
        for copy in range(draw(st.integers(min_value=0, max_value=2))):
            fonts.append(
                VirtualFont(
                    path=Path(f"/virtual/font-{index}-{copy}.ttf"),
                    family=family,
                    exists=draw(st.booleans()),
                    has_cjk=draw(st.booleans()),
                )
            )
    return candidates, tuple(fonts)


@given(scenario=font_scenarios())
@pytest.mark.property
def test_property_33_chinese_font_fallback_is_deterministic(
    scenario: tuple[tuple[str, ...], tuple[VirtualFont, ...]],
) -> None:
    """The first available CJK font is shared by PDF and charts; none means no file.

    **Property 33：中文字体确定性回退**
    **Validates: Requirements 11.6, 12.6, 14.3, 14.4**
    """
    candidates, fonts = scenario
    by_path = {font.path: font for font in fonts}
    reportlab_paths: list[Path] = []
    matplotlib_paths: list[Path] = []

    with TemporaryDirectory() as raw_directory:
        output = Path(raw_directory)

        def register_reportlab(_name: str, path: Path) -> None:
            reportlab_paths.append(path)
            (output / "report.pdf").write_text("乱码", encoding="utf-8")

        def register_matplotlib(path: Path) -> FontProperties:
            matplotlib_paths.append(path)
            (output / "chart.png").write_bytes(b"garbled")
            return FontProperties()

        resolver = ChineseFontResolver(
            candidates,
            explicit_path=None,
            platform_name="Linux",
            environment={},
            font_finder=lambda _directories: [font.path for font in fonts],
            file_exists=lambda path: by_path[path].exists,
            glyph_checker=lambda path: by_path[path].has_cjk,
            family_name_getter=lambda path: by_path[path].family,
            reportlab_registrar=register_reportlab,
            matplotlib_registrar=register_matplotlib,
        )
        status = resolver.resolve()
        expected = _expected_font(candidates, fonts)

        if expected is None:
            assert status.available is False
            assert status.reason == "CHINESE_FONT_UNAVAILABLE"
            assert status.path is None
            assert reportlab_paths == []
            assert matplotlib_paths == []
            assert list(output.iterdir()) == []
            return

        assert status.available is True
        assert status.path == expected.path
        assert status.family == expected.family
        assert reportlab_paths == [expected.path]
        assert matplotlib_paths == [expected.path]
