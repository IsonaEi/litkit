"""Wrap the manage shell tools (download/convert/audit/verify) via subprocess.

The bash scripts live in the top-level ``scripts/`` directory of the repo and
are the proven implementation of the DOI→PDF fallback chain and the Sci-Hub
opt-in gating. We shell out to them rather than reimplementing that logic, and
return structured ``{status, ...}`` dicts.

The scripts directory is located relative to this file at install/run time. If
the scripts are not found (e.g. an unusual packaging), the location can be
overridden with the ``LITKIT_SCRIPTS_DIR`` environment variable.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# src/litkit/manage/shell.py → repo root is three parents up; scripts/ sits there.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SCRIPTS_DIR = _REPO_ROOT / "scripts"


def _scripts_dir() -> Path:
    override = os.environ.get("LITKIT_SCRIPTS_DIR", "").strip()
    return Path(override) if override else _DEFAULT_SCRIPTS_DIR


def _script_path(name: str) -> Path:
    path = _scripts_dir() / name
    if not path.exists():
        raise FileNotFoundError(
            f"manage shell tool not found: {path}. "
            "Set LITKIT_SCRIPTS_DIR to the directory containing the .sh tools."
        )
    return path


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def download_paper(
    doi: str,
    dest_dir: str | None = None,
    enable_scihub: bool = False,
    filename: str | None = None,
) -> dict:
    """Download a paper PDF by DOI (or URL) into ``dest_dir`` using download.sh.

    Tries legal sources in order — direct URL, publisher patterns, EuropePMC,
    arXiv — and the Sci-Hub fallback only when ``enable_scihub`` is True (or the
    ``LITKIT_ENABLE_SCIHUB=1`` environment variable is set). Sci-Hub is OFF by
    default; the caller is responsible for legal/ethical compliance.

    Returns ``{status, doi, path, source, stdout, stderr}`` where ``status`` is
    "success" or "failure". ``path`` is the downloaded PDF (when successful) and
    ``source`` is the label of the source that served it (e.g. "Nature").
    """
    dest = dest_dir or "."
    script = _script_path("download.sh")

    cmd: list[str] = ["bash", str(script)]
    if enable_scihub:
        cmd.append("--enable-scihub")
    cmd.append(doi)
    cmd.append(dest)
    if filename:
        cmd.append(filename)

    proc = _run(cmd)
    out = proc.stdout.strip()

    if proc.returncode == 0:
        # download.sh prints: "✅ Downloaded from <source>: <path>"
        path = ""
        source = ""
        for line in out.splitlines():
            if "Downloaded from" in line and ":" in line:
                # "<emoji> Downloaded from <source>: <path>"
                after = line.split("Downloaded from", 1)[1]
                source = after.split(":", 1)[0].strip()
                path = after.split(":", 1)[1].strip()
                break
        return {
            "status": "success",
            "doi": doi,
            "path": path,
            "source": source,
            "stdout": out,
            "stderr": proc.stderr.strip(),
        }

    return {
        "status": "failure",
        "doi": doi,
        "path": None,
        "source": None,
        "stdout": out,
        "stderr": proc.stderr.strip(),
    }


def convert_to_markdown(pdf_path: str, output_path: str | None = None) -> dict:
    """Convert a PDF to markdown via convert.sh (pdftotext → markitdown fallback).

    Returns ``{status, pdf_path, path, tool, stdout, stderr}`` where ``path`` is
    the produced markdown file and ``tool`` is the converter that succeeded.
    """
    script = _script_path("convert.sh")
    cmd = ["bash", str(script), pdf_path]
    if output_path:
        cmd.append(output_path)

    proc = _run(cmd)
    out = proc.stdout.strip()

    if proc.returncode == 0:
        # "✅ Converted with <tool>: <path> (<n> bytes)"
        path = output_path or str(Path(pdf_path).with_suffix(".md"))
        tool = ""
        for line in out.splitlines():
            if "Converted with" in line:
                after = line.split("Converted with", 1)[1]
                tool = after.split(":", 1)[0].strip()
                rest = after.split(":", 1)[1].strip() if ":" in after else ""
                path = rest.split(" (", 1)[0].strip() or path
                break
        return {
            "status": "success",
            "pdf_path": pdf_path,
            "path": path,
            "tool": tool,
            "stdout": out,
            "stderr": proc.stderr.strip(),
        }

    return {
        "status": "failure",
        "pdf_path": pdf_path,
        "path": None,
        "tool": None,
        "stdout": out,
        "stderr": proc.stderr.strip(),
    }


def verify_pair(pdf_path: str, md_path: str | None = None) -> dict:
    """Verify one PDF + markdown pair via verify.sh.

    Returns ``{status, pdf_path, md_path, stdout, stderr}``.
    """
    script = _script_path("verify.sh")
    cmd = ["bash", str(script), pdf_path]
    if md_path:
        cmd.append(md_path)

    proc = _run(cmd)
    return {
        "status": "success" if proc.returncode == 0 else "failure",
        "pdf_path": pdf_path,
        "md_path": md_path,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def audit_library(references_dir: str) -> dict:
    """Audit a references/ directory via audit.sh (PDF/MD/index.json consistency).

    Returns ``{status, references_dir, report, stderr}`` where ``report`` is the
    full audit text and ``status`` is "success" (passed) or "failure" (errors).
    """
    script = _script_path("audit.sh")
    proc = _run(["bash", str(script), references_dir])
    return {
        "status": "success" if proc.returncode == 0 else "failure",
        "references_dir": references_dir,
        "report": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
