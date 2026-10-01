"""Tests for deterministic cross-platform Chinese font resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from matplotlib.font_manager import FontProperties

from app.core.fonts import ChineseFontResolver


@pytest.mark.unit
@pytest.mark.parametrize(
    ("platform_name", "environment", "expected_directories"),
    [
        ("Windows", {"WINDIR": r"D:\\Windows"}, (Path(r"D:\\Windows") / "Fonts",)),
        ("Linux", {}, (Path("/usr/share/fonts"), Path("/usr/local/share/fonts"))),
    ],
)
def test_resolver_scans_platform_virtual_manifest_and_honours_candidate_order(
    platform_name: str,
    environment: dict[str, str],
    expected_directories: tuple[Path, ...],
) -> None:
    """Windows and Linux scans choose the earliest configured usable family."""
    manifest = {
        Path("/virtual/yahei.ttf"): ("Microsoft YaHei", True),
        Path("/virtual/noto.ttf"): ("Noto Sans CJK SC", True),
    }
    scanned_directories: list[tuple[Path, ...]] = []
    reportlab_paths: list[Path] = []
    matplotlib_paths: list[Path] = []

    resolver = ChineseFontResolver(
        ("Noto Sans CJK SC", "Microsoft YaHei"),
        platform_name=platform_name,
        environment=environment,
        font_finder=lambda directories: scanned_directories.append(tuple(directories)) or manifest.keys(),
        file_exists=lambda path: path in manifest,
        glyph_checker=lambda path: manifest[path][1],
        family_name_getter=lambda path: manifest[path][0],
        reportlab_registrar=lambda _name, path: reportlab_paths.append(path),
        matplotlib_registrar=lambda path: matplotlib_paths.append(path) or FontProperties(),
    )

    status = resolver.resolve()

    assert scanned_directories == [expected_directories]
    assert status.available is True
    assert status.family == "Noto Sans CJK SC"
    assert status.path == Path("/virtual/noto.ttf")
    assert reportlab_paths == [status.path]
    assert matplotlib_paths == [status.path]


@pytest.mark.unit
def test_resolver_falls_back_when_preferred_family_is_missing() -> None:
    """An absent preferred font cannot prevent the configured fallback."""
    fallback = Path("/virtual/simhei.ttf")
    resolver = ChineseFontResolver(
        ("Noto Sans CJK SC", "SimHei"),
        platform_name="Linux",
        font_finder=lambda _directories: [fallback],
        file_exists=lambda path: path == fallback,
        glyph_checker=lambda _path: True,
        family_name_getter=lambda _path: "SimHei",
        reportlab_registrar=lambda _name, _path: None,
        matplotlib_registrar=lambda _path: FontProperties(),
    )

    status = resolver.resolve()

    assert status.available is True
    assert status.family == "SimHei"
    assert status.path == fallback


@pytest.mark.unit
def test_resolver_skips_fonts_without_cjk_glyphs() -> None:
    """A matching family without Chinese glyphs is never registered."""
    non_cjk = Path("/virtual/broken-noto.ttf")
    fallback = Path("/virtual/yahei.ttf")
    registered_paths: list[Path] = []
    resolver = ChineseFontResolver(
        ("Noto Sans CJK SC", "Microsoft YaHei"),
        font_finder=lambda _directories: [non_cjk, fallback],
        file_exists=lambda _path: True,
        glyph_checker=lambda path: path != non_cjk,
        family_name_getter=lambda path: "Noto Sans CJK SC" if path == non_cjk else "Microsoft YaHei",
        reportlab_registrar=lambda _name, path: registered_paths.append(path),
        matplotlib_registrar=lambda _path: FontProperties(),
    )

    status = resolver.resolve()

    assert status.available is True
    assert status.path == fallback
    assert registered_paths == [fallback]


@pytest.mark.unit
def test_resolver_reports_unavailable_when_every_font_is_invalid() -> None:
    """No output font is registered when no candidate has CJK glyph coverage."""
    unusable = Path("/virtual/not-cjk.ttf")
    registrations: list[Path] = []
    resolver = ChineseFontResolver(
        ("Noto Sans CJK SC",),
        font_finder=lambda _directories: [unusable],
        file_exists=lambda _path: True,
        glyph_checker=lambda _path: False,
        family_name_getter=lambda _path: "Noto Sans CJK SC",
        reportlab_registrar=lambda _name, path: registrations.append(path),
        matplotlib_registrar=lambda _path: FontProperties(),
    )

    status = resolver.resolve()

    assert status.available is False
    assert status.reason == "CHINESE_FONT_UNAVAILABLE"
    assert status.path is None
    assert status.family is None
    assert registrations == []
