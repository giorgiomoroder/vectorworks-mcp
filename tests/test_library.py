from pathlib import Path

from vwmcp import library


def make_tree(tmp_path):
    app = tmp_path / "Vectorworks 2026"
    for rel in [
        "Libraries/Entertainment/Lighting/Lighting Instruments Martin.vwx",
        "Libraries/Entertainment/Rigging/Truss/Truss Tomcat.vwx",
        "Libraries/Visualization/People/People Standing.vwx",
    ]:
        (app / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / rel).write_bytes(b"")
    user = tmp_path / "home/Library/Application Support/Vectorworks/2026/Libraries"
    (user / "Favorites").mkdir(parents=True)
    (user / "Favorites/My Truss.vwx").write_bytes(b"")
    return app, tmp_path / "home"


def test_roots_mac(tmp_path):
    app, home = make_tree(tmp_path)
    roots = library.library_roots("2026", platform="darwin", home=home, app_dir=app)
    assert [r.kind for r in roots] == ["vectorworks", "user"]
    assert roots[1].path == home / "Library/Application Support/Vectorworks/2026/Libraries"


def test_roots_skip_missing_dirs(tmp_path):
    roots = library.library_roots("2026", platform="darwin", home=tmp_path, app_dir=tmp_path / "nope")
    assert roots == []


def test_find_matches_every_query_word_against_relative_path(tmp_path):
    app, home = make_tree(tmp_path)
    kw = dict(vw_version="2026", platform="darwin", home=home, app_dir=app)
    truss = library.find_library_files("truss", **kw)
    assert [(t["library"], t["name"]) for t in truss] == [
        ("vectorworks", "Truss Tomcat"), ("user", "My Truss")
    ]
    assert truss[0]["folder"] == "Entertainment/Rigging/Truss"
    assert Path(truss[0]["path"]).exists()
    assert [t["name"] for t in library.find_library_files("rigging tomcat", **kw)] == ["Truss Tomcat"]
    assert len(library.find_library_files("", **kw)) == 4
    assert len(library.find_library_files("", limit=2, **kw)) == 2


def test_roots_follow_the_version(tmp_path):
    app = tmp_path / "Vectorworks 2027"
    (app / "Libraries").mkdir(parents=True)
    user = tmp_path / "home/Library/Application Support/Vectorworks/2027/Libraries"
    user.mkdir(parents=True)
    roots = library.library_roots("2027", platform="darwin", home=tmp_path / "home", app_dir=app)
    assert [r.path for r in roots] == [app / "Libraries", user]
def test_german_library_folder_and_decomposed_umlauts(tmp_path):
    import unicodedata

    app = tmp_path / "Vectorworks 2027"
    rel = unicodedata.normalize("NFD", "Bibliotheken/Gebäude/Tür (Stile)/Rahmentür.vwx")
    (app / rel).parent.mkdir(parents=True)
    (app / rel).write_bytes(b"")
    kw = dict(vw_version="2027", platform="darwin", home=tmp_path / "home", app_dir=app)
    assert [r.path.name for r in library.library_roots(**kw)] == ["Bibliotheken"]
    found = library.find_library_files("tür rahmen", **kw)
    assert [f["name"] for f in found] == [unicodedata.normalize("NFD", "Rahmentür")]


def test_default_version_follows_config(monkeypatch, tmp_path):
    import importlib
    from vwmcp import config
    monkeypatch.setenv("VWMCP_APP", "Vectorworks 2027")
    monkeypatch.delenv("VWMCP_VW_VERSION", raising=False)
    importlib.reload(config)
    try:
        user = tmp_path / "Library/Application Support/Vectorworks/2027/Bibliotheken"
        user.mkdir(parents=True)
        roots = library.library_roots(platform="darwin", home=tmp_path, app_dir=tmp_path / "none")
        assert [(r.kind, r.path) for r in roots] == [("user", user)]
    finally:
        monkeypatch.delenv("VWMCP_APP")
        importlib.reload(config)
