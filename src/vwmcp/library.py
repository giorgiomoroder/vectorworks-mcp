"""Browse Vectorworks library files on disk (no Vectorworks call needed).

Vectorworks ships its content libraries as plain .vwx files under the
application's Libraries folder (e.g. Entertainment/Lighting, Entertainment/
Rigging/Truss, Visualization/People) and keeps user libraries and favorites
under the user folder. The folder is named after the UI language
("Libraries" in English, "Bibliotheken" in German); both are searched.
macOS stores file names decomposed (NFD), so names and queries are
compared NFC-normalized ("Tür" matches either way). Listing the resources
inside a file, and importing one, happens in Vectorworks
(vwlib.library_resources / import_resource).
"""

from __future__ import annotations

import os
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from vwmcp import config

DEFAULT_APP_DIR = os.environ.get("VWMCP_APP_DIR")
# Name of the library folder per UI language (app and user folder alike).
LIBRARY_DIR_NAMES = ("Libraries", "Bibliotheken")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


@dataclass(frozen=True)
class LibraryRoot:
    kind: str  # "vectorworks" | "user"
    path: Path


def library_roots(
    vw_version: str | None = None,
    platform: str = sys.platform,
    home: Path | None = None,
    app_dir: Path | None = None,
) -> list[LibraryRoot]:
    if vw_version is None:
        vw_version = config.VW_VERSION
    home = home or Path.home()
    roots: list[LibraryRoot] = []
    if app_dir is None and DEFAULT_APP_DIR:
        app_dir = Path(DEFAULT_APP_DIR)
    if platform == "darwin":
        app_dir = app_dir or Path(f"/Applications/Vectorworks {vw_version}")
        user = home / f"Library/Application Support/Vectorworks/{vw_version}"
    elif platform == "win32":
        app_dir = app_dir or Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / f"Vectorworks {vw_version}"
        appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        user = appdata / f"Nemetschek/Vectorworks/{vw_version}"
    else:
        return roots
    for kind, base in (("vectorworks", app_dir), ("user", user)):
        for name in LIBRARY_DIR_NAMES:
            if (base / name).is_dir():
                roots.append(LibraryRoot(kind, base / name))
                break
    return roots


def find_library_files(
    query: str = "", roots: list[LibraryRoot] | None = None, limit: int = 50, **root_kwargs
) -> list[dict]:
    """Library .vwx files whose relative path contains every word of `query`."""
    roots = library_roots(**root_kwargs) if roots is None else roots
    words = [_nfc(w) for w in query.split()]
    out: list[dict] = []
    for root in roots:
        for path in sorted(root.path.rglob("*.vwx")):
            rel = path.relative_to(root.path)
            hay = _nfc(str(rel))
            if all(w in hay for w in words):
                out.append(
                    {
                        "library": root.kind,
                        "folder": str(rel.parent).replace(os.sep, "/"),
                        "name": path.stem,
                        "path": str(path),
                    }
                )
                if len(out) >= limit:
                    return out
    return out
