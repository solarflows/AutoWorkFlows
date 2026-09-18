#!/usr/bin/env python3
"""Fetch and safely extract AutoWorkflows OpenWrt build logs for diagnostics.

Read-only towards GitHub: only `gh repo view`, `gh run list`, `gh run view`,
`gh api` GET requests and `gh run download` are used. Local writes are
confined to `<repo>/.diagnostics/openwrt-build/<case-id>/`.

Subcommands:
    list       List recent workflow runs (failed ones by default).
    artifacts  List artifacts of one run (name, size, expired).
    fetch      Download selected artifacts (or the failed-step job log) into a case.
    extract    Safely extract a locally downloaded zip/tar into a case directory.

Extraction guards (Windows-safe, see docs/openwrt-build-pitfalls.md):
    - never follow or create symlinks/hardlinks,
    - skip every path containing a `build_dir` component,
    - reject absolute paths, drive letters and `..` traversal,
    - stop when the total extracted size exceeds --max-mb.

The command surface is intentionally one script with fixed subcommands so that
VS Code terminal auto-approve can allowlist a single stable prefix. See
`references/auto-approve.md` in the skill directory.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, NoReturn

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
DIAGNOSTICS_ROOT = REPO_ROOT / ".diagnostics" / "openwrt-build"
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
FAILED_CONCLUSIONS = {"failure", "timed_out", "startup_failure", "cancelled"}
LOG_ARTIFACT_SUFFIX = "-build-log"
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
SKIP_PATH_PARTS = {"build_dir"}
RUN_LIST_FIELDS = "databaseId,displayTitle,conclusion,status,event,headBranch,workflowName,createdAt,url"
DEFAULT_LIMIT = 20
MAX_LIMIT = 200
MAX_ARTIFACT_PAGES = 10
DEFAULT_MAX_MB = 2048
CHUNK_BYTES = 1 << 20
REMOTE_URL_PATTERN = re.compile(r"github\.com[:/]([^/\s]+)/([^\s/]+?)(?:\.git)?/*$", re.IGNORECASE)


class CliError(Exception):
    """Bounded, user-facing failure."""


def fail(message: str) -> NoReturn:
    raise CliError(message)


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def limit_int(value: str) -> int:
    number = positive_int(value)
    if number > MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"limit must be <= {MAX_LIMIT} to keep output bounded")
    return number


def non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
    if number < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return number


def ensure_repo_root() -> None:
    if not (REPO_ROOT / ".github" / "skills" / "openwrt-build-diagnostics").is_dir():
        fail(f"skill scripts are not located inside an AutoWorkflows checkout: {SCRIPT_DIR}")


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def truncate(text: str, length: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1] + "…"


def bounded_error(process: subprocess.CompletedProcess[str], limit: int = 400) -> str:
    raw = (process.stderr or "").strip() or (process.stdout or "").strip() or f"exit code {process.returncode}"
    return raw if len(raw) <= limit else raw[:limit] + "…"


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    gh = shutil.which("gh")
    if gh is None:
        fail("gh CLI not found in PATH; install it from https://cli.github.com and run `gh auth login`")
    return subprocess.run(
        [gh, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def require_gh_auth() -> None:
    process = run_gh(["auth", "status"])
    if process.returncode != 0:
        fail("gh is not authenticated; run `gh auth login` and retry")


def parse_remote(url: str) -> str | None:
    match = REMOTE_URL_PATTERN.search(url.strip())
    if not match:
        return None
    owner, name = match.group(1), match.group(2)
    if name.endswith(".git"):
        name = name[: -len(".git")]
    return f"{owner}/{name}"


def resolve_repo(explicit: str | None) -> str:
    if explicit:
        return explicit
    git = shutil.which("git")
    if git is not None:
        process = subprocess.run(
            [git, "-C", str(REPO_ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if process.returncode == 0:
            repo = parse_remote(process.stdout)
            if repo:
                return repo
    process = run_gh(["repo", "view", "--json", "nameWithOwner"])
    if process.returncode == 0:
        try:
            return str(json.loads(process.stdout)["nameWithOwner"])
        except (ValueError, KeyError):
            pass
    fail("cannot resolve the repository; run `gh auth login` or pass --repo OWNER/REPO")


def load_json(stdout: str, context: str) -> dict:
    try:
        return json.loads(stdout)
    except ValueError as error:
        raise CliError(f"unexpected JSON from gh while reading {context}: {error}") from None


def fetch_run(repo: str, run_id: int) -> dict:
    process = run_gh(["api", f"repos/{repo}/actions/runs/{run_id}"])
    if process.returncode != 0:
        fail(f"cannot read run {run_id} in {repo}: {bounded_error(process)}")
    return load_json(process.stdout, f"run {run_id}")


def fetch_artifacts(repo: str, run_id: int) -> list[dict]:
    artifacts: list[dict] = []
    for page in range(1, MAX_ARTIFACT_PAGES + 1):
        process = run_gh(["api", f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100&page={page}"])
        if process.returncode != 0:
            fail(f"cannot list artifacts of run {run_id}: {bounded_error(process)}")
        payload = load_json(process.stdout, f"artifacts of run {run_id}")
        batch = payload.get("artifacts") or []
        artifacts.extend(batch)
        if not batch or len(artifacts) >= int(payload.get("total_count") or 0):
            break
    return artifacts


def resolve_case_dir(case: str) -> Path:
    if not CASE_ID_PATTERN.match(case):
        fail(f"invalid case id {case!r}; use letters, digits, dot, underscore or dash (max 63 chars, alnum first)")
    ensure_repo_root()
    case_dir = DIAGNOSTICS_ROOT / case
    try:
        case_dir.resolve().relative_to(DIAGNOSTICS_ROOT.resolve())
    except ValueError:
        fail(f"case directory escapes {DIAGNOSTICS_ROOT}")
    return case_dir


def prepare_case_dir(case: str, *, force: bool) -> Path:
    case_dir = resolve_case_dir(case)
    if case_dir.exists():
        if not case_dir.is_dir():
            fail(f"{case_dir} exists and is not a directory")
        if any(case_dir.iterdir()) and not force:
            fail(f"case directory {case_dir} already contains data; pick another --case or pass --force to overlay")
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def default_case_for_run(run_id: int) -> str:
    return f"run-{run_id}"


def default_case_for_archive(name: str) -> str | None:
    lowered = name.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if lowered.endswith(suffix):
            stem = name[: -len(suffix)]
            break
    else:
        stem = name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return sanitized[:63] if sanitized and CASE_ID_PATTERN.match(sanitized) else None


def human_size(value: object) -> str:
    try:
        size = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "?"
    if size >= 1 << 30:
        return f"{size / (1 << 30):.2f} GB"
    if size >= 1 << 20:
        return f"{size / (1 << 20):.1f} MB"
    return f"{size} B"


def directory_size(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_parts(name: str) -> list[str] | None:
    candidate = name.replace("\\", "/").strip()
    if not candidate or "\x00" in candidate:
        return None
    if candidate.startswith("/") or candidate.startswith("//"):
        return None
    pure = PurePosixPath(candidate)
    parts = [part for part in pure.parts if part not in ("", ".")]
    if not parts:
        return None
    for part in parts:
        if part == ".." or re.match(r"^[A-Za-z]:$", part):
            return None
    return parts


def new_counts() -> dict[str, int]:
    return {
        "extracted": 0,
        "dirs": 0,
        "skipped_symlink": 0,
        "skipped_build_dir": 0,
        "skipped_unsafe": 0,
        "skipped_other": 0,
        "bytes": 0,
        "truncated": 0,
    }


def budget_exceeded(counts: dict[str, int], declared_size: int, max_bytes: int | None) -> bool:
    return max_bytes is not None and counts["bytes"] + declared_size > max_bytes


def extract_archive(archive: Path, destination: Path, max_bytes: int | None) -> dict[str, int]:
    if archive.name.lower().endswith(".zip"):
        return extract_zip(archive, destination, max_bytes)
    return extract_tar(archive, destination, max_bytes)


def extract_zip(archive: Path, destination: Path, max_bytes: int | None) -> dict[str, int]:
    counts = new_counts()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                parts = safe_parts(info.filename)
                if parts is None:
                    counts["skipped_unsafe"] += 1
                    continue
                if stat.S_ISLNK(info.external_attr >> 16):
                    counts["skipped_symlink"] += 1
                    continue
                if info.is_dir():
                    destination.joinpath(*parts).mkdir(parents=True, exist_ok=True)
                    counts["dirs"] += 1
                    continue
                if any(part.lower() in SKIP_PATH_PARTS for part in parts):
                    counts["skipped_build_dir"] += 1
                    continue
                if budget_exceeded(counts, info.file_size, max_bytes):
                    counts["truncated"] = 1
                    break
                target = destination.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, CHUNK_BYTES)
                counts["extracted"] += 1
                counts["bytes"] += info.file_size
    except (zipfile.BadZipFile, OSError) as error:
        raise CliError(f"cannot extract {archive}: {error}") from None
    return counts


def extract_tar(archive: Path, destination: Path, max_bytes: int | None) -> dict[str, int]:
    counts = new_counts()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(archive, "r:*") as bundle:
            for member in bundle:
                parts = safe_parts(member.name)
                if parts is None:
                    counts["skipped_unsafe"] += 1
                    continue
                if member.issym() or member.islnk():
                    counts["skipped_symlink"] += 1
                    continue
                if member.isdir():
                    destination.joinpath(*parts).mkdir(parents=True, exist_ok=True)
                    counts["dirs"] += 1
                    continue
                if not member.isreg():
                    counts["skipped_other"] += 1
                    continue
                if any(part.lower() in SKIP_PATH_PARTS for part in parts):
                    counts["skipped_build_dir"] += 1
                    continue
                if budget_exceeded(counts, member.size, max_bytes):
                    counts["truncated"] = 1
                    break
                source = bundle.extractfile(member)
                if source is None:
                    counts["skipped_other"] += 1
                    continue
                target = destination.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, CHUNK_BYTES)
                counts["extracted"] += 1
                counts["bytes"] += member.size
    except (tarfile.TarError, OSError) as error:
        raise CliError(f"cannot extract {archive}: {error}") from None
    return counts


def find_nested_archives(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if ".extracted" in parts or any(part.startswith(".staging-") for part in parts):
            continue
        if path.name.lower().endswith(ARCHIVE_SUFFIXES):
            yield path


def merge_tree(source: Path, target: Path) -> None:
    """Move every entry of `source` into `target`, overwriting existing files."""
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            merge_tree(child, destination)
        else:
            if destination.exists():
                destination.unlink()
            shutil.move(str(child), str(destination))


def extraction_note(counts: dict[str, int]) -> str:
    note = (
        f"{counts['extracted']} files ({human_size(counts['bytes'])})"
        f", skipped {counts['skipped_symlink']} symlink"
        f" / {counts['skipped_build_dir']} build_dir"
        f" / {counts['skipped_unsafe']} unsafe"
    )
    if counts["truncated"]:
        note += "; TRUNCATED at --max-mb limit"
    return note


def job_log_path(case_dir: Path, run_id: int) -> Path:
    return case_dir / "job-logs" / f"run-{run_id}-failed-steps.log"


def next_step_hint(case: str) -> str:
    return (
        "Next: python .github/skills/openwrt-build-diagnostics/scripts/"
        f"analyze_build_logs.py .diagnostics/openwrt-build/{case}"
    )


def cmd_list(args: argparse.Namespace) -> int:
    require_gh_auth()
    repo = resolve_repo(args.repo)
    process = run_gh(["run", "list", "--repo", repo, "--limit", str(args.limit), "--json", RUN_LIST_FIELDS])
    if process.returncode != 0:
        fail(f"cannot list runs in {repo}: {bounded_error(process)}")
    runs = load_json(process.stdout, "run list")
    if not isinstance(runs, list):
        fail("unexpected run list payload from gh")
    if not args.all:
        runs = [run for run in runs if (run.get("conclusion") or "") in FAILED_CONCLUSIONS]
    scope = "all conclusions" if args.all else "failed/cancelled only"
    if not runs:
        print(f"No matching workflow runs in {repo} ({scope}); try --all or a larger --limit.")
        return 0
    print(f"Recent runs in {repo} ({scope}):")
    for run in runs:
        state = run.get("conclusion") or run.get("status") or "?"
        print(f"- {run.get('databaseId')}  [{state}]  {run.get('workflowName')}  @{run.get('headBranch')}  {run.get('createdAt')}")
        print(f"    {truncate(str(run.get('displayTitle') or ''), 80)}")
        print(f"    {run.get('url')}")
    print()
    print(
        "Select one run (never assume the latest failure is the target), then run: "
        "python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py "
        "artifacts --run-id <id>"
    )
    return 0


def cmd_artifacts(args: argparse.Namespace) -> int:
    require_gh_auth()
    repo = resolve_repo(args.repo)
    run = fetch_run(repo, args.run_id)
    artifacts = fetch_artifacts(repo, args.run_id)
    print(
        f"Run {args.run_id} in {repo}: {truncate(str(run.get('display_title') or ''), 80)}"
        f"  [{run.get('conclusion') or run.get('status')}]"
    )
    if not artifacts:
        print("No artifacts attached to this run.")
        print(
            "Use the failed-step job log instead: "
            "python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py "
            f"fetch --run-id {args.run_id}"
        )
        return 0
    width = max(len(str(artifact.get("name"))) for artifact in artifacts)
    print(f"{'name'.ljust(width)}  {'size'.rjust(10)}  expired")
    for artifact in artifacts:
        name = str(artifact.get("name"))
        print(f"{name.ljust(width)}  {human_size(artifact.get('size_in_bytes')).rjust(10)}  {bool(artifact.get('expired'))}")
    print()
    print(
        "Download the evidence you need, for example: "
        "python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py "
        f"fetch --run-id {args.run_id} --artifact <name>"
    )
    return 0


def select_artifacts(args: argparse.Namespace, artifacts: list[dict]) -> tuple[list[dict], list[str]]:
    available = [artifact for artifact in artifacts if not artifact.get("expired")]
    expired = [str(artifact.get("name")) for artifact in artifacts if artifact.get("expired")]
    all_names = {str(artifact.get("name")) for artifact in artifacts}

    if args.artifact:
        unknown = [name for name in args.artifact if name not in all_names]
        if unknown:
            known = ", ".join(sorted(all_names)) or "(none)"
            fail(f"unknown artifact(s): {', '.join(unknown)}; available: {known}")
        selected = [artifact for artifact in available if str(artifact.get("name")) in set(args.artifact)]
        skipped = [name for name in args.artifact if name in expired]
        return selected, skipped
    if args.pattern:
        selected = [
            artifact
            for artifact in available
            if any(fnmatch.fnmatch(str(artifact.get("name")), pattern) for pattern in args.pattern)
        ]
        return selected, []
    if args.all_artifacts:
        return available, expired
    selected = [artifact for artifact in available if str(artifact.get("name")).endswith(LOG_ARTIFACT_SUFFIX)]
    return selected, [name for name in expired if name.endswith(LOG_ARTIFACT_SUFFIX)]


def cmd_fetch(args: argparse.Namespace) -> int:
    if args.job_log and args.no_job_log:
        fail("--job-log and --no-job-log are mutually exclusive")
    require_gh_auth()
    repo = resolve_repo(args.repo)
    run = fetch_run(repo, args.run_id)
    case = args.case or default_case_for_run(args.run_id)
    case_dir = prepare_case_dir(case, force=args.force)
    artifacts = fetch_artifacts(repo, args.run_id)
    selected, skipped_expired = select_artifacts(args, artifacts)

    print(
        f"Run {args.run_id} in {repo}: {truncate(str(run.get('display_title') or ''), 80)}"
        f"  [{run.get('conclusion') or run.get('status')}]"
    )
    if skipped_expired:
        print(f"  note: skipped expired artifact(s): {', '.join(skipped_expired)}")
    if not selected:
        if args.no_job_log:
            print("  note: no artifact selected and --no-job-log was given")
        elif artifacts:
            print("  note: no artifact matched the selection; using the failed-step job log instead")
        else:
            print("  note: this run has no artifacts; using the failed-step job log")

    download_dir = case_dir / "artifacts"
    downloaded: list[str] = []
    failures: list[tuple[str, str]] = []
    for artifact in selected:
        name = str(artifact.get("name"))
        target = download_dir / name
        if target.exists():
            # `gh run download` refuses to overwrite existing files, so refresh
            # through a unique staging directory and merge afterwards.
            download_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
            staging = Path(tempfile.mkdtemp(prefix=f".staging-{safe_name}-", dir=download_dir))
        else:
            staging = target
        process = run_gh(
            ["run", "download", str(args.run_id), "--repo", repo, "--name", name, "--dir", str(staging)]
        )
        if process.returncode == 0:
            if staging != target:
                merge_tree(staging, target)
                shutil.rmtree(staging, ignore_errors=True)
            downloaded.append(name)
            print(f"  downloaded {name} -> {display_path(target)}")
        else:
            failures.append((name, bounded_error(process)))
            print(f"  FAILED {name}: {bounded_error(process, 200)}")
            if staging != target:
                shutil.rmtree(staging, ignore_errors=True)

    saved_job_log: Path | None = None
    want_job_log = args.job_log or (not downloaded and not args.no_job_log)
    if want_job_log:
        process = run_gh(["run", "view", str(args.run_id), "--repo", repo, "--log-failed"])
        if process.returncode == 0 and process.stdout.strip():
            saved_job_log = job_log_path(case_dir, args.run_id)
            saved_job_log.parent.mkdir(parents=True, exist_ok=True)
            saved_job_log.write_text(process.stdout, encoding="utf-8")
            print(f"  saved failed-step job log -> {display_path(saved_job_log)}")
        elif process.returncode == 0:
            print("  note: gh returned no failed-step log output")
        else:
            print(f"  warning: cannot fetch failed-step job log: {bounded_error(process)}")

    extraction: list[dict] = []
    if args.extract_nested:
        max_bytes = args.max_mb * (1 << 20) if args.max_mb > 0 else None
        for name in downloaded:
            for archive in find_nested_archives(download_dir / name):
                destination = archive.parent / (archive.name + ".extracted")
                if destination.exists():
                    print(f"  note: skip existing extraction {display_path(destination)}")
                    continue
                try:
                    counts = extract_archive(archive, destination, max_bytes)
                except CliError as error:
                    extraction.append({"archive": display_path(archive), "error": str(error)})
                    print(f"  warning: {error}")
                    continue
                extraction.append({"archive": display_path(archive), "destination": display_path(destination), **counts})
                print(f"  extracted {archive.name}: {extraction_note(counts)}")

    payload = {
        "schema": 1,
        "generated_at": now_iso(),
        "repo": repo,
        "case": case,
        "run": {
            key: run.get(key)
            for key in ("id", "name", "display_title", "html_url", "conclusion", "status", "head_branch", "created_at", "event")
        },
        "selection": {
            "artifacts": args.artifact or [],
            "patterns": args.pattern or [],
            "all_artifacts": bool(args.all_artifacts),
            "job_log_requested": bool(args.job_log),
        },
        "artifacts": [
            {"name": name, "downloaded": True, "bytes_on_disk": directory_size(download_dir / name)}
            for name in downloaded
        ]
        + [{"name": name, "downloaded": False, "error": error} for name, error in failures],
        "job_log": display_path(saved_job_log) if saved_job_log else None,
        "nested_extraction": extraction,
    }
    (case_dir / "fetch.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"Case: {display_path(case_dir)}")
    if failures:
        print(f"WARNING: {len(failures)} artifact(s) failed to download")
    if not downloaded and saved_job_log is None:
        if failures:
            print("No new evidence was retrieved; see the download errors above.")
        else:
            print("No evidence was retrieved; verify the run id or place logs manually and use `extract`.")
        return 1
    print(next_step_hint(case))
    return 1 if failures else 0


def cmd_extract(args: argparse.Namespace) -> int:
    archive = Path(args.archive).expanduser()
    if not archive.is_file():
        fail(f"archive does not exist: {archive}")
    if not archive.name.lower().endswith(ARCHIVE_SUFFIXES):
        fail(f"unsupported archive type: {archive.name}; supported: {', '.join(ARCHIVE_SUFFIXES)}")
    case = args.case or default_case_for_archive(archive.name)
    if not case:
        fail("cannot derive a case id from the archive name; pass --case")
    case_dir = prepare_case_dir(case, force=args.force)
    max_bytes = args.max_mb * (1 << 20) if args.max_mb > 0 else None
    counts = extract_archive(archive, case_dir, max_bytes)
    payload = {
        "schema": 1,
        "generated_at": now_iso(),
        "archive": display_path(archive.resolve()),
        "case": case,
        "counts": counts,
    }
    (case_dir / "extract.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Extracted {archive.name}: {extraction_note(counts)}")
    print()
    print(f"Case: {display_path(case_dir)}")
    print(next_step_hint(case))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list recent workflow runs (failed ones by default)")
    list_parser.add_argument("--repo", help="OWNER/REPO; defaults to the origin remote of this checkout")
    list_parser.add_argument("--limit", type=limit_int, default=DEFAULT_LIMIT, help=f"max runs to inspect (default {DEFAULT_LIMIT})")
    list_parser.add_argument("--all", action="store_true", help="include successful runs")
    list_parser.set_defaults(func=cmd_list)

    artifacts_parser = subparsers.add_parser("artifacts", help="list artifacts of one run")
    artifacts_parser.add_argument("--run-id", type=positive_int, required=True, help="workflow run id")
    artifacts_parser.add_argument("--repo", help="OWNER/REPO; defaults to the origin remote of this checkout")
    artifacts_parser.set_defaults(func=cmd_artifacts)

    fetch_parser = subparsers.add_parser("fetch", help="download artifacts or the failed-step job log into a case")
    fetch_parser.add_argument("--run-id", type=positive_int, required=True, help="workflow run id")
    fetch_parser.add_argument("--case", help="case id under .diagnostics/openwrt-build/ (default run-<id>)")
    fetch_parser.add_argument("--artifact", action="append", metavar="NAME", help="artifact name to download (repeatable)")
    fetch_parser.add_argument("--pattern", action="append", metavar="GLOB", help="artifact name glob (repeatable)")
    fetch_parser.add_argument("--all-artifacts", action="store_true", help="download every non-expired artifact")
    fetch_parser.add_argument("--extract-nested", action="store_true", help="also extract zip/tar files found inside artifacts")
    fetch_parser.add_argument("--job-log", action="store_true", help="also save the failed-step job log")
    fetch_parser.add_argument("--no-job-log", action="store_true", help="never save the failed-step job log")
    fetch_parser.add_argument("--force", action="store_true", help="overlay an existing non-empty case directory")
    fetch_parser.add_argument("--max-mb", type=non_negative_int, default=DEFAULT_MAX_MB, help=f"extraction budget in MB, 0 = unlimited (default {DEFAULT_MAX_MB})")
    fetch_parser.add_argument("--repo", help="OWNER/REPO; defaults to the origin remote of this checkout")
    fetch_parser.set_defaults(func=cmd_fetch)

    extract_parser = subparsers.add_parser("extract", help="safely extract a local zip/tar into a case directory")
    extract_parser.add_argument("--archive", required=True, help="path to a local .zip/.tar.* downloaded by the user")
    extract_parser.add_argument("--case", help="case id under .diagnostics/openwrt-build/ (default from archive name)")
    extract_parser.add_argument("--force", action="store_true", help="overlay an existing non-empty case directory")
    extract_parser.add_argument("--max-mb", type=non_negative_int, default=DEFAULT_MAX_MB, help=f"extraction budget in MB, 0 = unlimited (default {DEFAULT_MAX_MB})")
    extract_parser.set_defaults(func=cmd_extract)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except CliError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
