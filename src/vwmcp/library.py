"""Browse Vectorworks library files on disk (no Vectorworks call needed).

Vectorworks ships its content libraries as plain .vwx files under the
application's Libraries folder (e.g. Entertainment/Lighting, Entertainment/
Rigging/Truss, Visualization/People) and keeps user libraries and favorites
under the user folder. Listing the resources inside a file, and importing
one, happens in Vectorworks (vwlib.library_resources / import_resource).
"""

from __future__ import annotations

import os

from vwmcp import config
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_APP_DIR = os.environ.get("VWMCP_APP_DIR")


@dataclass(frozen=True)
class LibraryRoot:
    kind: str  # "vectorworks" | "user"
    path: Path


def library_roots(
    vw_version: str = config.VW_VERSION,
    platform: str = sys.platform,
    home: Path | None = None,
    app_dir: Path | None = None,
) -> list[LibraryRoot]:
    home = home or Path.home()
    roots: list[LibraryRoot] = []
    if app_dir is None and DEFAULT_APP_DIR:
        app_dir = Path(DEFAULT_APP_DIR)
    if platform == "darwin":
        app_dir = app_dir or Path(f"/Applications/Vectorworks {vw_version}")
        user = home / f"Library/Application Support/Vectorworks/{vw_version}/Libraries"
    elif platform == "win32":
        app_dir = app_dir or Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / f"Vectorworks {vw_version}"
        appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        user = appdata / f"Nemetschek/Vectorworks/{vw_version}/Libraries"
    else:
        return roots
    roots.append(LibraryRoot("vectorworks", app_dir / "Libraries"))
    roots.append(LibraryRoot("user", user))
    return [r for r in roots if r.path.is_dir()]


def find_library_files(
    query: str = "", roots: list[LibraryRoot] | None = None, limit: int = 50, **root_kwargs
) -> list[dict]:
    """Library .vwx files whose relative path contains every word of `query`."""
    roots = library_roots(**root_kwargs) if roots is None else roots
    words = [w.lower() for w in query.split()]
    out: list[dict] = []
    for root in roots:
        for path in sorted(root.path.rglob("*.vwx")):
            rel = path.relative_to(root.path)
            hay = str(rel).lower()
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
