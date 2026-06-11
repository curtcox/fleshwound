"""Site build publishes per-kind documentation for every registered catalog entry."""

from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path

import fleshwound.kinds  # noqa: F401
from fleshwound.catalog import catalog

from tools.build_site import CATALOG_DOC, parse_catalog_kind_docs

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_every_registered_kind_has_catalog_section() -> None:
    docs = parse_catalog_kind_docs(CATALOG_DOC)
    missing = sorted(set(catalog.entries) - set(docs))
    assert not missing, f"undocumented kinds in recursion-kinds-catalog.md: {missing}"


def test_site_publishes_per_kind_pages(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    out = tmp_path / "site"
    reports.mkdir()
    (reports / "compile.rc").write_text("0")
    (reports / "lint.rc").write_text("0")
    (reports / "types.rc").write_text("0")
    (reports / "tests.rc").write_text("0")
    (reports / "ruff.json").write_text("[]")
    (reports / "mypy.json").write_text("")
    (reports / "junit.xml").write_text(
        '<?xml version="1.0"?><testsuite tests="0" failures="0" errors="0" skipped="0"></testsuite>'
    )
    (reports / "coverage.json").write_text('{"totals": {"percent_covered": 0.0}, "files": {}}')

    subprocess.run(
        [sys.executable, "tools/build_site.py", "--reports", str(reports), "--out", str(out), "--api", "api"],
        cwd=REPO_ROOT,
        check=True,
    )

    index = out / "kinds" / "index.html"
    assert index.exists()

    for name in catalog.entries:
        page = out / "kinds" / f"{name}.html"
        assert page.exists(), f"missing published page for kind {name!r}"
        text = page.read_text(encoding="utf-8")
        assert html.escape(catalog.entries[name].convention) in text

    rlm_page = (out / "kinds" / "rlm_loop.html").read_text(encoding="utf-8")
    assert "Extended specification" in rlm_page
    assert "RLM Loop Kind" in rlm_page
