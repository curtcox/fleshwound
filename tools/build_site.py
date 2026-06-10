#!/usr/bin/env python3
"""Static-site generator for the fleshwound developer Pages site.

Aggregates CI artifacts (ruff / mypy / pytest JUnit / coverage), computes
git-based code metrics, renders project Markdown, and emits a self-contained
HTML site. Designed to never fail the build: missing or malformed inputs render
as "unavailable" rather than raising.

Usage:
    python tools/build_site.py --reports reports --out site --api api

The output directory is deleted and recreated on each run.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Optional rendering deps (present in the `site` extra). Guarded so the metrics
# path still works without them.
try:
    import markdown as _markdown
except Exception:  # pragma: no cover - exercised only when dep is absent
    _markdown = None

try:
    from pygments.formatters import HtmlFormatter as _PygmentsHtmlFormatter
except Exception:  # pragma: no cover
    _PygmentsHtmlFormatter = None

REPO_ROOT = Path(__file__).resolve().parent.parent

# Narrative docs published under guide/.
GUIDE_DOCS = ["README.md", "docs/history/rlm_design_conversation.md", "fleshwound/kinds/program_writer_prompt.md"]

NAV = [
    ("Home", "index.html"),
    ("CI", "ci/index.html"),
    ("Metrics", "metrics.html"),
    ("API", "api/index.html"),
]


# --------------------------------------------------------------------------- #
# HTML scaffolding
# --------------------------------------------------------------------------- #
def page(title: str, body: str, prefix: str) -> str:
    """Wrap ``body`` in the shared layout. ``prefix`` is the relative path back
    to the site root (e.g. "" for root pages, "../" for one-deep pages)."""
    nav = " ".join(
        f'<a href="{prefix}{href}">{html.escape(label)}</a>' for label, href in NAV
    )
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · fleshwound</title>
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="stylesheet" href="{prefix}assets/pygments.css">
</head>
<body>
<header class="site-header">
  <a class="brand" href="{prefix}index.html">fleshwound</a>
  <nav>{nav}</nav>
</header>
<main>
<h1>{html.escape(title)}</h1>
{body}
</main>
<footer class="site-footer">Generated {built}</footer>
</body>
</html>
"""


def chip(label: str, status: str, href: Optional[str] = None, extra: str = "") -> str:
    """A coloured status pill. ``status`` is pass/fail/missing."""
    text = html.escape(label)
    if extra:
        text += f' <span class="chip-extra">{html.escape(extra)}</span>'
    inner = f'<span class="chip chip-{status}">{text}</span>'
    return f'<a class="chip-link" href="{href}">{inner}</a>' if href else inner


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


# --------------------------------------------------------------------------- #
# Input collection
# --------------------------------------------------------------------------- #
def read_rc(reports: Path, name: str) -> Optional[int]:
    """Read an exit code recorded by the workflow at reports/<name>.rc."""
    f = reports / f"{name}.rc"
    if not f.exists():
        return None
    try:
        return int(f.read_text().strip())
    except (ValueError, OSError):
        return None


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def load_ruff(reports: Path) -> Optional[list]:
    return load_json(reports / "ruff.json")


def load_mypy(reports: Path) -> Optional[list]:
    """mypy --output=json emits one JSON object per line."""
    f = reports / "mypy.json"
    if not f.exists():
        return None
    items = []
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def load_junit(reports: Path) -> Optional[dict]:
    f = reports / "junit.xml"
    if not f.exists():
        return None
    try:
        root = ET.parse(f).getroot()
    except ET.ParseError:
        return None
    cases = []
    for case in root.iter("testcase"):
        status = "passed"
        message = ""
        for child in case:
            tag = child.tag.lower()
            if tag in ("failure", "error", "skipped"):
                status = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                message = child.get("message", "") or (child.text or "")
                break
        cases.append(
            {
                "name": case.get("name", ""),
                "classname": case.get("classname", ""),
                "time": case.get("time", ""),
                "status": status,
                "message": message,
            }
        )
    counts = Counter(c["status"] for c in cases)
    return {"cases": cases, "counts": counts}


def load_coverage(reports: Path) -> Optional[dict]:
    return load_json(reports / "coverage.json")


# --------------------------------------------------------------------------- #
# Status resolution
# --------------------------------------------------------------------------- #
def resolve_status(rc: Optional[int], inferred: str) -> str:
    if rc is not None:
        return "pass" if rc == 0 else "fail"
    return inferred


# --------------------------------------------------------------------------- #
# CI pages
# --------------------------------------------------------------------------- #
def render_ci(reports: Path, out: Path) -> dict[str, dict]:
    """Render ci/index, ci/lint, ci/types, ci/tests, ci/coverage.
    Returns a dict of {section: {status, summary, href}} for the home page."""
    ci_dir = out / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)

    ruff = load_ruff(reports)
    mypy = load_mypy(reports)
    junit = load_junit(reports)
    cov = load_coverage(reports)

    results: dict[str, dict] = {}

    # --- Compilation -------------------------------------------------------- #
    compile_rc = read_rc(reports, "compile")
    compile_status = resolve_status(compile_rc, "missing" if compile_rc is None else "pass")
    compile_log = reports / "compile.txt"
    log_text = compile_log.read_text() if compile_log.exists() else ""
    compile_summary = {"pass": "byte-compiled OK", "fail": "syntax errors"}.get(
        compile_status, "no report"
    )
    results["Compilation"] = {
        "status": compile_status,
        "summary": compile_summary,
        "href": "ci/index.html",
    }

    # --- Lint --------------------------------------------------------------- #
    lint_rc = read_rc(reports, "lint")
    if ruff is None:
        lint_status, lint_summary = resolve_status(lint_rc, "missing"), "no report"
    else:
        lint_status = resolve_status(lint_rc, "pass" if not ruff else "fail")
        lint_summary = f"{len(ruff)} finding(s)"
    results["Lint (ruff)"] = {"status": lint_status, "summary": lint_summary, "href": "ci/lint.html"}
    (ci_dir / "lint.html").write_text(render_lint_page(ruff, lint_status))

    # --- Static analysis ---------------------------------------------------- #
    types_rc = read_rc(reports, "types")
    if mypy is None:
        types_status, types_summary = resolve_status(types_rc, "missing"), "no report"
        type_errors = []
    else:
        type_errors = [m for m in mypy if m.get("severity") == "error"]
        types_status = resolve_status(types_rc, "pass" if not type_errors else "fail")
        types_summary = f"{len(type_errors)} error(s)"
    results["Types (mypy)"] = {"status": types_status, "summary": types_summary, "href": "ci/types.html"}
    (ci_dir / "types.html").write_text(render_types_page(mypy, types_status))

    # --- Tests -------------------------------------------------------------- #
    tests_rc = read_rc(reports, "tests")
    if junit is None:
        tests_status, tests_summary = resolve_status(tests_rc, "missing"), "no report"
    else:
        c = junit["counts"]
        bad = c.get("failed", 0) + c.get("error", 0)
        tests_status = resolve_status(tests_rc, "pass" if bad == 0 else "fail")
        total = sum(c.values())
        tests_summary = f"{c.get('passed', 0)}/{total} passed"
    results["Tests"] = {"status": tests_status, "summary": tests_summary, "href": "ci/tests.html"}
    (ci_dir / "tests.html").write_text(render_tests_page(junit, tests_status))

    # --- Coverage ----------------------------------------------------------- #
    if cov is None:
        cov_status, cov_summary = "missing", "no report"
    else:
        pct = cov.get("totals", {}).get("percent_covered", 0.0)
        cov_status = "pass" if pct else "missing"
        cov_summary = f"{pct:.0f}%"
    results["Coverage"] = {"status": cov_status, "summary": cov_summary, "href": "ci/coverage.html"}
    (ci_dir / "coverage.html").write_text(render_coverage_page(cov))

    # --- Dashboard ---------------------------------------------------------- #
    (ci_dir / "index.html").write_text(render_ci_dashboard(results, log_text))
    return results


def render_ci_dashboard(results: dict[str, dict], compile_log: str) -> str:
    # Dashboard lives in ci/; link to sibling pages by basename.
    chips = "\n".join(
        chip(name, r["status"], href=r["href"].split("/")[-1], extra=r["summary"])
        for name, r in results.items()
    )
    body = f'<div class="chip-row">{chips}</div>'
    body += "<p>Each card reflects the most recent run on <code>main</code>. " \
            "Follow a card for full detail.</p>"
    if compile_log.strip():
        body += "<h2>Compilation log</h2><pre class='log'>" + html.escape(compile_log) + "</pre>"
    return page("CI Results", body, prefix="../")


def render_lint_page(ruff: Optional[list], status: str) -> str:
    if ruff is None:
        return page("Lint (ruff)", "<p class='muted'>No ruff report available.</p>", prefix="../")
    if not ruff:
        return page("Lint (ruff)", "<p class='ok'>No lint findings. 🎉</p>", prefix="../")
    rows = []
    for f in ruff:
        loc = f.get("location") or {}
        where = f"{f.get('filename', '')}:{loc.get('row', '')}:{loc.get('column', '')}"
        code = f.get("code") or ""
        url = f.get("url")
        code_cell = f'<a href="{html.escape(url)}">{html.escape(code)}</a>' if url else html.escape(code)
        rows.append([html.escape(where), code_cell, html.escape(f.get("message", ""))])
    body = f"<p>{len(ruff)} finding(s).</p>" + table(["Location", "Rule", "Message"], rows)
    return page("Lint (ruff)", body, prefix="../")


def render_types_page(mypy: Optional[list], status: str) -> str:
    if mypy is None:
        return page("Types (mypy)", "<p class='muted'>No mypy report available.</p>", prefix="../")
    errors = [m for m in mypy if m.get("severity") == "error"]
    if not errors:
        return page("Types (mypy)", "<p class='ok'>No type errors. 🎉</p>", prefix="../")
    rows = []
    for m in errors:
        where = f"{m.get('file', '')}:{m.get('line', '')}:{m.get('column', '')}"
        rows.append(
            [html.escape(where), html.escape(m.get("code", "") or ""), html.escape(m.get("message", ""))]
        )
    body = f"<p>{len(errors)} error(s).</p>" + table(["Location", "Code", "Message"], rows)
    return page("Types (mypy)", body, prefix="../")


def render_tests_page(junit: Optional[dict], status: str) -> str:
    if junit is None:
        return page("Tests", "<p class='muted'>No test report available.</p>", prefix="../")
    c = junit["counts"]
    total = sum(c.values())
    summary = (
        f"<p>{total} test(s): "
        f"{c.get('passed', 0)} passed, {c.get('failed', 0)} failed, "
        f"{c.get('error', 0)} error, {c.get('skipped', 0)} skipped.</p>"
    )
    rows = []
    for case in junit["cases"]:
        name = f"{case['classname']}::{case['name']}" if case["classname"] else case["name"]
        st = case["status"]
        badge = f'<span class="chip chip-{ "pass" if st=="passed" else "fail" if st in ("failed","error") else "missing" }">{st}</span>'
        time = f"{float(case['time']):.3f}s" if case["time"] else ""
        msg = html.escape(case["message"])[:300]
        rows.append([html.escape(name), badge, time, f"<span class='msg'>{msg}</span>"])
    body = summary + table(["Test", "Status", "Time", "Message"], rows)
    return page("Tests", body, prefix="../")


def render_coverage_page(cov: Optional[dict]) -> str:
    if cov is None:
        return page("Coverage", "<p class='muted'>No coverage report available.</p>", prefix="../")
    total = cov.get("totals", {}).get("percent_covered", 0.0)
    rows = []
    for path, data in sorted(cov.get("files", {}).items()):
        s = data.get("summary", {})
        pct = s.get("percent_covered", 0.0)
        rows.append(
            [
                html.escape(path),
                f"{pct:.0f}%",
                str(s.get("num_statements", "")),
                str(s.get("missing_lines", "")),
            ]
        )
    body = f"<p class='big-stat'>{total:.0f}% overall</p>"
    body += table(["File", "Coverage", "Statements", "Missing"], rows)
    return page("Coverage", body, prefix="../")


# --------------------------------------------------------------------------- #
# Code metrics
# --------------------------------------------------------------------------- #
def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def last_changed_map() -> dict[str, str]:
    """One git pass: newest commit ISO date per tracked file path."""
    out = git("log", "--pretty=format:%cI", "--name-only", "--no-renames")
    result: dict[str, str] = {}
    current = ""
    for line in out.splitlines():
        if not line.strip():
            continue
        if line[0].isdigit() and "T" in line[:25]:  # ISO timestamp line
            current = line.strip()
        else:
            result.setdefault(line.strip(), current)
    return result


def render_metrics(out: Path) -> dict:
    files = [f for f in git("ls-files").splitlines() if f.strip()]
    changed = last_changed_map()

    by_ext: Counter = Counter()
    total_loc = 0
    rows = []
    largest: tuple[str | None, int] = (None, -1)  # (path, loc)
    for rel in sorted(files):
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        ext = path.suffix or "(none)"
        by_ext[ext] += 1
        size = path.stat().st_size
        try:
            text = path.read_text(encoding="utf-8")
            loc = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            total_loc += loc
            loc_cell = str(loc)
            if loc > largest[1]:
                largest = (rel, loc)
        except (UnicodeDecodeError, OSError):
            loc = None
            loc_cell = "—"
        when = changed.get(rel, "")[:10]
        rows.append([html.escape(rel), loc_cell, f"{size:,}", when])

    ext_rows = [[html.escape(e), str(n)] for e, n in by_ext.most_common()]
    summary = table(
        ["Metric", "Value"],
        [
            ["Tracked files", str(len(files))],
            ["Total lines of code", f"{total_loc:,}"],
            ["Largest file", f"{html.escape(largest[0] or '—')} ({largest[1]} lines)"],
            ["File types", str(len(by_ext))],
        ],
    )
    body = "<h2>Summary</h2>" + summary
    body += "<h2>Files by type</h2>" + table(["Extension", "Count"], ext_rows)
    body += "<h2>All files</h2>" + table(["File", "LOC", "Bytes", "Last changed"], rows)
    (out / "metrics.html").write_text(page("Code Metrics", body, prefix=""))
    return {
        "files": len(files),
        "loc": total_loc,
        "largest": largest,
    }


# --------------------------------------------------------------------------- #
# Markdown docs
# --------------------------------------------------------------------------- #
def render_markdown(text: str) -> str:
    if _markdown is None:
        return "<pre>" + html.escape(text) + "</pre>"
    return _markdown.markdown(
        text,
        extensions=["fenced_code", "tables", "toc", "codehilite"],
        extension_configs={"codehilite": {"guess_lang": False}},
    )


def render_doc_collection(
    sources: list[Path], out_subdir: Path, prefix: str, out_root: Path
) -> list[tuple[str, str]]:
    """Render each markdown source into out_subdir. Returns (title, href) list."""
    out_subdir.mkdir(parents=True, exist_ok=True)
    links = []
    for src in sources:
        if not src.exists():
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        title = src.stem.replace("_", " ").replace("-", " ").title()
        rendered = f'<article class="prose">{render_markdown(text)}</article>'
        (out_subdir / f"{src.stem}.html").write_text(page(title, rendered, prefix="../"))
        rel = out_subdir.relative_to(out_root).as_posix()
        links.append((title, f"{rel}/{src.stem}.html"))
    return links


# --------------------------------------------------------------------------- #
# API reference (copy pdoc output)
# --------------------------------------------------------------------------- #
def copy_api(api_src: Path, out: Path) -> bool:
    if not api_src.exists() or not api_src.is_dir():
        return False
    dest = out / "api"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(api_src, dest)
    # pdoc may emit fleshwound.html rather than index.html; normalise.
    if not (dest / "index.html").exists():
        for candidate in ("fleshwound.html", "fleshwound/index.html"):
            c = dest / candidate
            if c.exists():
                shutil.copy(c, dest / "index.html")
                break
    return (dest / "index.html").exists()


# --------------------------------------------------------------------------- #
# Home page
# --------------------------------------------------------------------------- #
def render_home(
    out: Path,
    ci: dict[str, dict],
    metrics: dict,
    spec_links: list[tuple[str, str]],
    guide_links: list[tuple[str, str]],
    has_api: bool,
) -> None:
    chips = "\n".join(
        chip(name, r["status"], href=r["href"], extra=r["summary"]) for name, r in ci.items()
    )
    body = "<p>Developer dashboard for <strong>fleshwound</strong> — recursive program-writing on Monty.</p>"
    body += '<h2>CI at a glance</h2>'
    body += f'<div class="chip-row">{chips}</div>'
    body += '<p><a href="ci/index.html">Full CI results →</a></p>'

    body += "<h2>Code metrics</h2>"
    body += (
        f"<p>{metrics['files']} tracked files · {metrics['loc']:,} lines of code · "
        f"largest: <code>{html.escape(metrics['largest'][0] or '—')}</code>. "
        f'<a href="metrics.html">Details →</a></p>'
    )

    body += "<h2>API reference</h2>"
    body += (
        '<p><a href="api/index.html">Browse the fleshwound API →</a></p>'
        if has_api
        else "<p class='muted'>API reference unavailable in this build.</p>"
    )

    def link_list(links):
        if not links:
            return "<p class='muted'>None.</p>"
        items = "".join(f'<li><a href="{href}">{html.escape(t)}</a></li>' for t, href in links)
        return f"<ul>{items}</ul>"

    body += "<h2>Specifications</h2>" + link_list(spec_links)
    body += "<h2>Guides &amp; design notes</h2>" + link_list(guide_links)

    (out / "index.html").write_text(page("Overview", body, prefix=""))


# --------------------------------------------------------------------------- #
# Assets
# --------------------------------------------------------------------------- #
def write_assets(out: Path) -> None:
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parent / "assets" / "style.css"
    if src.exists():
        shutil.copy(src, assets / "style.css")
    # Pygments stylesheet for codehilite-rendered code blocks.
    if _PygmentsHtmlFormatter is not None:
        css = _PygmentsHtmlFormatter().get_style_defs(".codehilite")
        (assets / "pygments.css").write_text(css)
    else:
        (assets / "pygments.css").write_text("/* pygments unavailable */")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports", default="reports", type=Path)
    ap.add_argument("--out", default="site", type=Path)
    ap.add_argument("--api", default="api", type=Path)
    args = ap.parse_args()

    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    write_assets(out)

    ci = render_ci(args.reports, out)
    metrics = render_metrics(out)

    spec_sources = sorted((REPO_ROOT / "docs" / "specs").glob("*.md"))
    spec_links = render_doc_collection(spec_sources, out / "docs", "../", out)

    guide_sources = [REPO_ROOT / name for name in GUIDE_DOCS]
    guide_links = render_doc_collection(guide_sources, out / "guide", "../", out)

    has_api = copy_api(args.api, out)

    render_home(out, ci, metrics, spec_links, guide_links, has_api)

    print(f"Site written to {out}/ ({metrics['files']} files, {metrics['loc']} LOC).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
