#!/usr/bin/env python3
"""run_scout.py — Orchestrator for the discover tool.

Runs all enabled scout scripts in parallel, collects results, feeds them to
merge_and_rank.py, and outputs the digest.

Modes:
    --once   Human-triggered: print digest to stdout (+ optional --output path)
    --cron   Scheduled: write JSON to LITKIT_OUTPUT dir + log
    --query  On-demand single query: search all scouts with a keyword override

Exit codes:
    0 — success
    1 — >= 3 scouts failed

Usage:
    python3 run_scout.py --once
    python3 run_scout.py --once --query "place cells navigation" --output /tmp/digest.md
    python3 run_scout.py --cron
    python3 run_scout.py --test     # use dummy data from all scouts
"""

import json
import sys
import subprocess
import tempfile
import os
import shlex
import argparse
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import LITKIT_CONFIG, LITKIT_OUTPUT

SCRIPTS_DIR = Path(__file__).parent

SCOUTS = [
    "scout_pubmed.py",
    "scout_biorxiv.py",
    "scout_arxiv.py",
    "scout_semantic.py",
    "scout_rss.py",
]


def load_config() -> dict:
    import json as _json
    return _json.loads(LITKIT_CONFIG.read_text())


def setup_logging(cron_mode: bool) -> None:
    if cron_mode:
        LITKIT_OUTPUT.mkdir(parents=True, exist_ok=True)
        log_path = LITKIT_OUTPUT / "scout.log"
        logging.basicConfig(
            filename=str(log_path),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )
    else:
        logging.basicConfig(
            stream=sys.stderr,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )


def run_scout(scout_script: str, timeout_s: int, extra_args: list[str] | None = None) -> tuple[str, list[dict] | None]:
    """Run a single scout script, return (name, papers_list or None on failure)."""
    cmd = [sys.executable, str(SCRIPTS_DIR / scout_script)] + (extra_args or [])
    source_name = scout_script.replace(".py", "")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode != 0:
            logging.error(f"{source_name} exited {result.returncode}: {result.stderr.strip()[:200]}")
            return source_name, None

        stdout = result.stdout.strip()
        if not stdout:
            logging.warning(f"{source_name} produced no output.")
            return source_name, []

        papers = json.loads(stdout)
        logging.info(f"{source_name}: {len(papers)} papers")
        return source_name, papers

    except subprocess.TimeoutExpired:
        logging.error(f"{source_name} timed out after {timeout_s}s.")
        return source_name, None
    except json.JSONDecodeError as exc:
        logging.error(f"{source_name} JSON decode error: {exc}")
        return source_name, None
    except Exception as exc:
        logging.error(f"{source_name} unexpected error: {exc}")
        return source_name, None


def run_all_scouts(
    timeout_s: int,
    extra_args: list[str] | None = None,
) -> tuple[dict, int]:
    """Run all scouts in parallel. Returns (results_dict, failure_count)."""
    results: dict[str, list[dict] | None] = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(run_scout, scout, timeout_s, extra_args): scout
            for scout in SCOUTS
        }
        for future in as_completed(futures, timeout=timeout_s + 10):
            scout = futures[future]
            try:
                name, papers = future.result()
                results[name] = papers
            except Exception as exc:
                name = scout.replace(".py", "")
                logging.error(f"{name} future error: {exc}")
                results[name] = None

    failures = [name for name, papers in results.items() if papers is None]
    successes = [name for name, papers in results.items() if papers is not None]

    logging.info(f"Scouts completed: {len(successes)} OK, {len(failures)} failed")
    if failures:
        logging.warning(f"Failed scouts: {', '.join(failures)}")

    return results, len(failures)


def collect_and_merge(
    results: dict,
    output_dir: Path | None = None,
    test_mode: bool = False,
) -> str:
    """Write temp JSONs, run merge_and_rank, return digest."""
    all_papers_flat: list[dict] = []
    for papers in results.values():
        if papers:
            all_papers_flat.extend(papers)

    tmp_files: list[str] = []
    for name, papers in results.items():
        if papers:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=f"_{name}.json",
                prefix="scout_",
                delete=False,
            ) as f:
                json.dump(papers, f)
                tmp_files.append(f.name)

    logging.info(f"Passing {len(all_papers_flat)} papers to merge_and_rank…")

    merge_cmd = [sys.executable, str(SCRIPTS_DIR / "merge_and_rank.py")]
    if output_dir:
        merge_cmd += ["--output-dir", str(output_dir)]
    if tmp_files:
        merge_cmd += tmp_files
    else:
        merge_cmd += ["--test"]

    digest = ""
    try:
        merge_result = subprocess.run(
            merge_cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        digest = merge_result.stdout.strip()
        if merge_result.returncode != 0:
            logging.error(f"merge_and_rank error: {merge_result.stderr.strip()[:300]}")
        else:
            logging.info(f"Digest generated ({len(digest)} chars).")
    except Exception as exc:
        logging.error(f"merge_and_rank failed: {exc}")
        digest = "[ERROR] merge_and_rank failed — check logs."
    finally:
        for f in tmp_files:
            try:
                os.unlink(f)
            except Exception:
                pass

    return digest


def notify(text: str) -> None:
    """Fire an optional notification command (best-effort).

    If the ``LITKIT_NOTIFY_CMD`` environment variable is set, the digest summary
    text is passed to it as a single trailing argument. This lets you wire up any
    notifier you like (desktop notify-send, a Slack webhook script, etc.) without
    coupling the tool to a specific platform. If unset, this is a no-op.

    Example:
        export LITKIT_NOTIFY_CMD="notify-send 'Literature Scout'"
    """
    notify_cmd = os.environ.get("LITKIT_NOTIFY_CMD", "").strip()
    if not notify_cmd:
        logging.debug("LITKIT_NOTIFY_CMD not set — skipping notification.")
        return
    try:
        subprocess.run(f"{notify_cmd} {shlex.quote(text)}", shell=True,
                       capture_output=True, text=True, timeout=15)
    except Exception as exc:
        logging.warning(f"notification command failed: {exc}")


def main():
    parser = argparse.ArgumentParser(description="litkit discover orchestrator")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--once", action="store_true",
                            help="Run once, print digest to stdout")
    mode_group.add_argument("--cron", action="store_true",
                            help="Scheduled run: write JSON + log to LITKIT_OUTPUT")
    mode_group.add_argument("--test", action="store_true",
                            help="Use dummy data from all scouts (no network)")

    parser.add_argument("--query", type=str, default=None,
                        help="Override search with a custom query term (--once mode)")
    parser.add_argument("--output", type=str, default=None,
                        help="Write digest to this path instead of stdout (--once mode)")
    parser.add_argument("--sources", type=str, default=None,
                        help="Comma-separated list of sources to run (default: all)")

    args = parser.parse_args()

    # Default to --once if no mode specified
    if not args.once and not args.cron and not args.test:
        args.once = True

    cron_mode = args.cron
    setup_logging(cron_mode)

    try:
        cfg = load_config()
    except Exception as exc:
        logging.error(f"Could not load config from {LITKIT_CONFIG}: {exc}")
        sys.exit(1)

    timeout_s = cfg.get("scout_timeout_s", 60)

    logging.info(f"Starting litkit discover (mode={'cron' if cron_mode else 'once'}, timeout={timeout_s}s)")

    # Extra args for scouts (test mode, custom query)
    extra_args: list[str] = []
    if args.test:
        extra_args.append("--test")

    # Source filtering
    global SCOUTS
    if args.sources:
        source_map = {
            "pubmed": "scout_pubmed.py",
            "biorxiv": "scout_biorxiv.py",
            "arxiv": "scout_arxiv.py",
            "semantic": "scout_semantic.py",
            "semantic_scholar": "scout_semantic.py",
            "rss": "scout_rss.py",
        }
        selected = [source_map[s.strip()] for s in args.sources.split(",") if s.strip() in source_map]
        if selected:
            SCOUTS = selected

    if args.test:
        results = {s.replace(".py", ""): None for s in SCOUTS}
        # Run all with --test flag
        for scout in SCOUTS:
            name, papers = run_scout(scout, timeout_s=30, extra_args=["--test"])
            results[name] = papers
        failures = 0
    else:
        results, failures = run_all_scouts(timeout_s, extra_args)

    if failures >= 3:
        alert = (
            f"⚠️ litkit discover FAILURE — {failures}/5 scouts failed.\n"
            f"Failed: {', '.join(n for n, p in results.items() if p is None)}\n"
            "Manual investigation required."
        )
        logging.error(alert)
        if cron_mode:
            notify(alert)
        else:
            print(alert, file=sys.stderr)
        sys.exit(1)

    # Determine output dir for cron mode
    output_dir = LITKIT_OUTPUT if cron_mode else None

    digest = collect_and_merge(results, output_dir=output_dir, test_mode=args.test)

    if args.once or args.test:
        # --once: output to file or stdout
        if args.output:
            Path(args.output).write_text(digest)
            print(f"[run_scout] Digest written to {args.output}", file=sys.stderr)
        else:
            print(digest)

    if cron_mode:
        # Write digest as markdown too
        today_str = datetime.date.today().isoformat()
        digest_path = LITKIT_OUTPUT / f"digest-{today_str}.md"
        try:
            digest_path.write_text(digest)
            logging.info(f"Digest written to {digest_path}")
        except Exception as exc:
            logging.warning(f"Could not write digest file: {exc}")

        notify(f"litkit discover complete — {today_str} digest ready")
        logging.info("DONE: cron scout complete")


if __name__ == "__main__":
    main()
