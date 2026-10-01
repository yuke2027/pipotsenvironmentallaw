"""Discover and register one CJK-capable font for PDF and chart rendering.

The resolver always returns a status object rather than silently falling back to
an arbitrary font.  HTML remains usable when no suitable font is installed,
while PDF and chart exporters can reject rendering with the explicit
``CHINESE_FONT_UNAVAILABLE`` reason.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform as platform_module
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from matplotlib import font_manager, rcParams
from matplotlib.font_manager import FontProperties
from matplotlib.ft2font import FT2Font
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

if TYPE_CHECKING:
    from .config import Settings


_LOGGER = logging.getLogger(__name__)
_CJK_SAMPLE_CODEPOINTS = (ord("中"), ord("文"), ord("测"))


@dataclass(frozen=True)
class ChineseFontStatus:
    """The selected font and its renderers, or a clear unavailable result."""

    available: bool
    path: Path | None
    family: str | None
    reportlab_font_name: str | None
    matplotlib_font: FontProperties | None
    reason: str | None = None

    @classmethod
    def unavailable(cls, reason: str) -> "ChineseFontStatus":
        """Return the status consumed by exporters when no font can be used."""
        return cls(
            available=False,
            path=None,
            family=None,
            reportlab_font_name=None,
            matplotlib_font=None,
            reason=reason,
        )


class ChineseFontResolver:
    """Resolve the first configured CJK-capable font and register its file path.

    Explicit ``CHINESE_FONT_PATH`` takes precedence when it is an existing font
    containing CJK sample glyphs.  Otherwise the resolver uses
    :func:`matplotlib.font_manager.findSystemFonts` in the platform font
    directories and chooses the first configured family that is available.
    """

    def __init__(
        self,
        candidates: Sequence[str],
        *,
        explicit_path: Path | str | None = None,
        platform_name: str | None = None,
        environment: dict[str, str] | None = None,
        font_finder: Callable[[Sequence[Path]], Iterable[Path | str]] | None = None,
        file_exists: Callable[[Path], bool] | None = None,
        glyph_checker: Callable[[Path], bool] | None = None,
        family_name_getter: Callable[[Path], str] | None = None,
        reportlab_registrar: Callable[[str, Path], None] | None = None,
        matplotlib_registrar: Callable[[Path], FontProperties] | None = None,
    ) -> None:
        if not candidates:
            raise ValueError("font candidates must not be empty")

        self._candidates = tuple(candidate.strip() for candidate in candidates if candidate.strip())
        if not self._candidates:
            raise ValueError("font candidates must contain at least one non-empty family")

        self._environment = environment if environment is not None else os.environ
        configured_path = explicit_path if explicit_path is not None else self._environment.get(
            "CHINESE_FONT_PATH"
        )
        self._explicit_path = Path(configured_path).expanduser() if configured_path else None
        self._platform_name = (platform_name or platform_module.system()).casefold()
        self._font_finder = font_finder or self._find_system_fonts
        self._file_exists = file_exists or (lambda path: path.is_file())
        self._glyph_checker = glyph_checker or self._has_cjk_glyphs
        self._family_name_getter = family_name_getter or self._font_family
        self._reportlab_registrar = reportlab_registrar or self._register_reportlab
        self._matplotlib_registrar = matplotlib_registrar or self._register_matplotlib

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ChineseFontResolver":
        """Build a resolver from the sole application configuration source."""
        return cls(settings.font_candidates, explicit_path=settings.chinese_font_path)

    def resolve(self) -> ChineseFontStatus:
        """Resolve and register a single font file for ReportLab and matplotlib."""
        if self._explicit_path is not None:
            explicit = self._usable_font(self._explicit_path)
            if explicit is not None:
                return self._register(explicit)
            _LOGGER.warning("CHINESE_FONT_EXPLICIT_PATH_UNUSABLE", extra={"path": str(self._explicit_path)})

        try:
            font_paths = sorted(
                {Path(value).expanduser() for value in self._font_finder(self.system_font_directories())},
                key=lambda value: str(value).casefold(),
            )
        except Exception as error:  # pragma: no cover - defensive integration boundary
            _LOGGER.warning("CHINESE_FONT_SCAN_FAILED", exc_info=error)
            return ChineseFontStatus.unavailable("CHINESE_FONT_UNAVAILABLE")

        fonts_by_family: dict[str, list[Path]] = {}
        for path in font_paths:
            usable = self._usable_font(path)
            if usable is None:
                continue
            try:
                family = self._family_name_getter(usable).strip()
            except Exception:  # pragma: no cover - malformed font metadata boundary
                continue
            if family:
                fonts_by_family.setdefault(self._normalise_family(family), []).append(usable)

        for candidate in self._candidates:
            candidate_fonts = fonts_by_family.get(self._normalise_family(candidate), [])
            if candidate_fonts:
                return self._register(candidate_fonts[0])

        _LOGGER.warning(
            "CHINESE_FONT_UNAVAILABLE",
            extra={"candidates": self._candidates, "platform": self._platform_name},
        )
        return ChineseFontStatus.unavailable("CHINESE_FONT_UNAVAILABLE")

    def system_font_directories(self) -> tuple[Path, ...]:
        """Return the platform-specific font directories passed to matplotlib."""
        if self._platform_name.startswith("win"):
            return (Path(self._environment.get("WINDIR", r"C:\\Windows")) / "Fonts",)
        if self._platform_name == "linux":
            return (Path("/usr/share/fonts"), Path("/usr/local/share/fonts"))
        return ()

    def _register(self, path: Path) -> ChineseFontStatus:
        try:
            family = self._family_name_getter(path).strip()
            reportlab_font_name = self._reportlab_font_name(path)
            self._reportlab_registrar(reportlab_font_name, path)
            matplotlib_font = self._matplotlib_registrar(path)
        except Exception as error:
            _LOGGER.warning("CHINESE_FONT_REGISTRATION_FAILED", extra={"path": str(path)}, exc_info=error)
            return ChineseFontStatus.unavailable("CHINESE_FONT_UNAVAILABLE")

        _LOGGER.info(
            "CHINESE_FONT_SELECTED",
            extra={"font_family": family, "font_path": str(path)},
        )
        return ChineseFontStatus(
            available=True,
            path=path,
            family=family,
            reportlab_font_name=reportlab_font_name,
            matplotlib_font=matplotlib_font,
        )

    def _usable_font(self, path: Path) -> Path | None:
        if not self._file_exists(path):
            return None
        try:
            return path if self._glyph_checker(path) else None
        except Exception:  # pragma: no cover - malformed font parsing boundary
            return None

    @staticmethod
    def _normalise_family(family: str) -> str:
        return " ".join(family.casefold().split())

    @staticmethod
    def _reportlab_font_name(path: Path) -> str:
        digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
        return f"ChineseFont-{digest}"

    @staticmethod
    def _has_cjk_glyphs(path: Path) -> bool:
        charmap = FT2Font(str(path)).get_charmap()
        return all(codepoint in charmap for codepoint in _CJK_SAMPLE_CODEPOINTS)

    @staticmethod
    def _font_family(path: Path) -> str:
        return FontProperties(fname=str(path)).get_name()

    @staticmethod
    def _find_system_fonts(directories: Sequence[Path]) -> Iterable[str]:
        font_paths = [str(directory) for directory in directories]
        return font_manager.findSystemFonts(fontpaths=font_paths or None)

    @staticmethod
    def _register_reportlab(font_name: str, path: Path) -> None:
        pdfmetrics.registerFont(TTFont(font_name, str(path)))

    @staticmethod
    def _register_matplotlib(path: Path) -> FontProperties:
        font_manager.fontManager.addfont(str(path))
        properties = FontProperties(fname=str(path))
        rcParams["font.sans-serif"] = [properties.get_name()]
        rcParams["axes.unicode_minus"] = False
        return properties
