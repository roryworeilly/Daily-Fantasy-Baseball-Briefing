"""Load briefing CSS/JS from res/ (edit those files directly)."""
from __future__ import annotations

from pathlib import Path

# src/fdb/assets.py → project root is two levels up from package dir
_ROOT = Path(__file__).resolve().parent.parent.parent
_CSS_PATH = _ROOT / "res" / "briefing.css"
_JS_PATH = _ROOT / "res" / "briefing.js"


def _read(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    try:
        s = path.read_text(encoding="utf-8")
        return s if s.strip() else fallback
    except OSError:
        return fallback


def reload_css_js() -> tuple[str, str]:
    """Re-read disk; used if you regenerate assets."""
    fb_css = (
        "/* missing res/briefing.css — run: .venv/bin/python "
        ".build/extract_ui_assets.py */\n"
    )
    fb_js = "/* missing res/briefing.js */\n"
    return _read(_CSS_PATH, fb_css), _read(_JS_PATH, fb_js)


CSS, JS = reload_css_js()
