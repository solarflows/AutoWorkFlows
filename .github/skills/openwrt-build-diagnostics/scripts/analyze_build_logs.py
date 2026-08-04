#!/usr/bin/env python3
"""Extract bounded, deterministic evidence from OpenWrt build logs."""

from __future__ import annotations

import argparse
import codecs
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Iterable


ERROR_PATTERN = re.compile(
    r"(?:\bERROR\b|\bError\s+\d+\b|failed to build|cannot stat|No such file or directory|Traceback)",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(r"^time:\s*([^#\s]+)#([0-9.]+)#([0-9.]+)#([0-9.]+)\s*$")
SIGNATURES = {
    "generic_environment_leak": (
        re.compile(r"continue configure in default builddir\s+[\"']?\./[^\s\"']+", re.IGNORECASE),
        re.compile(r"--enable-builddir=[^\s\"']+", re.IGNORECASE),
    ),
    "libffi_missing_fficonfig": (
        re.compile(r"cannot stat .*fficonfig\.h", re.IGNORECASE),
    ),
    "ccache_wrapper": (
        re.compile(r"\bccache_(?:cc|cxx)\b|\bccache\s+(?:gcc|g\+\+|clang|clang\+\+)\b", re.IGNORECASE),
    ),
    "github_needs_skip": (
        re.compile(r"skipped.*needs|needs.*skipped", re.IGNORECASE),
    ),
}
TEXT_SUFFIXES = {".log", ".txt", ".out"}
MAX_EVIDENCE_PER_FILE = 12
TAIL_LINES = 20
MAX_SUMMARY_SOURCES = 10
MAX_SUMMARY_EVIDENCE_FILES = 12
MAX_SUMMARY_EVIDENCE_PER_FILE = 4
MAX_SUMMARY_EVIDENCE_LENGTH = 300


@dataclass
class FileFinding:
    path: str
    kind: str
    size_bytes: int
    encoding: str
    line_count: int
    duration_seconds: float | None
    has_terminal_time: bool
    evidence: list[str]
    signatures: list[str]
    tail: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Extracted log directory or build log file")
    parser.add_argument("--output", type=Path, help="Report directory; defaults to <input>/report")
    return parser.parse_args()


def detect_encoding(path: Path) -> str:
    with path.open("rb") as stream:
        prefix = stream.read(4)
    if prefix.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if prefix.startswith(codecs.BOM_UTF32_LE) or prefix.startswith(codecs.BOM_UTF32_BE):
        return "utf-32"
    if prefix.startswith(codecs.BOM_UTF16_LE) or prefix.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    return "utf-8"


def candidate_files(root: Path, output: Path) -> Iterable[Path]:
    paths = [root] if root.is_file() else root.rglob("*")
    for path in paths:
        if not path.is_file() or output in path.parents:
            continue
        lower_name = path.name.lower()
        if lower_name in {"error.txt", "compile.txt"} or path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def classify(path: Path) -> str:
    lower_name = path.name.lower()
    if lower_name == "error.txt":
        return "error-index"
    if lower_name == "compile.txt":
        return "compile-log"
    return "build-log"


def relative_path(path: Path, root: Path) -> str:
    base = root.parent if root.is_file() else root
    return path.relative_to(base).as_posix()


def analyze_file(path: Path, root: Path) -> FileFinding:
    encoding = detect_encoding(path)
    evidence: list[str] = []
    signatures: set[str] = set()
    tail: deque[str] = deque(maxlen=TAIL_LINES)
    line_count = 0
    last_nonempty = ""
    duration_seconds = None

    with path.open("r", encoding=encoding, errors="replace", newline=None) as stream:
        for raw_line in stream:
            line_count += 1
            line = raw_line.rstrip("\r\n")
            if line.strip():
                last_nonempty = line.strip()
                tail.append(line)
            if ERROR_PATTERN.search(line) and len(evidence) < MAX_EVIDENCE_PER_FILE:
                evidence.append(f"L{line_count}: {line.strip()[:500]}")
            for name, patterns in SIGNATURES.items():
                if any(pattern.search(line) for pattern in patterns):
                    signatures.add(name)
                    if len(evidence) < MAX_EVIDENCE_PER_FILE:
                        marker = f"L{line_count}: {line.strip()[:500]}"
                        if marker not in evidence:
                            evidence.append(marker)

    time_match = TIME_PATTERN.match(last_nonempty)
    if time_match:
        duration_seconds = sum(float(time_match.group(index)) for index in range(2, 5))

    return FileFinding(
        path=relative_path(path, root),
        kind=classify(path),
        size_bytes=path.stat().st_size,
        encoding=encoding,
        line_count=line_count,
        duration_seconds=duration_seconds,
        has_terminal_time=time_match is not None,
        evidence=evidence,
        signatures=sorted(signatures),
        tail=list(tail),
    )


def logical_compile_path(path: str) -> str:
    parts = Path(path).parts
    if parts and parts[0].lower() in {"logs", "logs.1"}:
        parts = parts[1:]
    return Path(*parts).as_posix()


def find_retry_pairs(findings: list[FileFinding]) -> list[dict[str, object]]:
    first_pass: dict[str, FileFinding] = {}
    retries: dict[str, FileFinding] = {}
    for finding in findings:
        if finding.kind != "compile-log":
            continue
        normalized = logical_compile_path(finding.path)
        first_component = Path(finding.path).parts[0].lower()
        if first_component == "logs.1":
            first_pass[normalized] = finding
        elif first_component == "logs":
            retries[normalized] = finding

    pairs = []
    for normalized in sorted(first_pass.keys() & retries.keys()):
        original = first_pass[normalized]
        retry = retries[normalized]
        ratio = retry.size_bytes / original.size_bytes if original.size_bytes else None
        pairs.append(
            {
                "logical_path": normalized,
                "first_pass": original.path,
                "retry": retry.path,
                "first_pass_bytes": original.size_bytes,
                "retry_bytes": retry.size_bytes,
                "retry_size_ratio": round(ratio, 4) if ratio is not None else None,
                "possible_stamp_skip": ratio is not None and ratio < 0.15,
            }
        )
    return pairs


def hypotheses(findings: list[FileFinding], pairs: list[dict[str, object]]) -> list[dict[str, object]]:
    signature_sources: dict[str, list[str]] = {}
    for finding in findings:
        for signature in finding.signatures:
            signature_sources.setdefault(signature, []).append(finding.path)

    results = []
    if "generic_environment_leak" in signature_sources and "libffi_missing_fficonfig" in signature_sources:
        results.append(
            {
                "id": "libffi-target-environment-leak",
                "confidence": "high",
                "summary": "A generic TARGET-like environment value changed libffi's Autoconf build directory, leaving fficonfig.h outside the path expected by InstallDev.",
                "sources": sorted(set(signature_sources["generic_environment_leak"] + signature_sources["libffi_missing_fficonfig"])),
            }
        )
    elif "libffi_missing_fficonfig" in signature_sources:
        results.append(
            {
                "id": "libffi-fficonfig-path-mismatch",
                "confidence": "medium",
                "summary": "libffi InstallDev expected fficonfig.h in a directory where it was not generated; inspect first-pass configure output and inherited environment variables.",
                "sources": signature_sources["libffi_missing_fficonfig"],
            }
        )
    if any(pair["possible_stamp_skip"] for pair in pairs):
        results.append(
            {
                "id": "stamp-skipped-retry",
                "confidence": "medium",
                "summary": "At least one retry log is much smaller than its first-pass log; diagnose logs.1 before treating retry output as the original failure.",
                "sources": [pair["logical_path"] for pair in pairs if pair["possible_stamp_skip"]],
            }
        )
    if "ccache_wrapper" in signature_sources:
        results.append(
            {
                "id": "ccache-wrapper-present",
                "confidence": "low",
                "summary": "ccache wrapper use is present. This is contextual evidence, not proof that ccache caused the failure.",
                "sources": signature_sources["ccache_wrapper"],
            }
        )
    return results


def format_bounded_sources(sources: list[str]) -> str:
    visible = sources[:MAX_SUMMARY_SOURCES]
    rendered = ", ".join(f"`{source}`" for source in visible)
    omitted = len(sources) - len(visible)
    if omitted:
        rendered += f"; {omitted} more in `analysis.json`"
    return rendered


def write_reports(input_path: Path, output: Path, findings: list[FileFinding]) -> None:
    pairs = find_retry_pairs(findings)
    inferred = hypotheses(findings, pairs)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path.resolve()),
        "summary": {
            "files": len(findings),
            "error_indexes": sum(item.kind == "error-index" for item in findings),
            "compile_logs": sum(item.kind == "compile-log" for item in findings),
            "empty_files": sum(item.size_bytes == 0 for item in findings),
            "compile_logs_without_terminal_time": sum(
                item.kind == "compile-log" and not item.has_terminal_time for item in findings
            ),
        },
        "hypotheses": inferred,
        "retry_pairs": pairs,
        "files": [asdict(item) for item in findings],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# OpenWrt Build Log Analysis",
        "",
        f"- Input: `{input_path.resolve()}`",
        f"- Files analyzed: {payload['summary']['files']}",
        f"- Error indexes: {payload['summary']['error_indexes']}",
        f"- Compile logs: {payload['summary']['compile_logs']}",
        f"- Empty files: {payload['summary']['empty_files']}",
        f"- Compile logs without terminal `time:`: {payload['summary']['compile_logs_without_terminal_time']}",
        "",
        "## Hypotheses",
        "",
    ]
    if inferred:
        for item in inferred:
            sources = format_bounded_sources(item["sources"])
            lines.extend([f"### {item['id']} ({item['confidence']})", "", str(item["summary"]), "", f"Sources: {sources}", ""])
    else:
        lines.extend(["No known signature was strong enough to infer a hypothesis.", ""])

    lines.extend(["## Evidence", ""])
    evidence_findings = [item for item in findings if item.evidence]
    if evidence_findings:
        for finding in evidence_findings[:MAX_SUMMARY_EVIDENCE_FILES]:
            lines.append(f"### `{finding.path}`")
            lines.append("")
            lines.extend(
                f"- {entry[:MAX_SUMMARY_EVIDENCE_LENGTH]}"
                for entry in finding.evidence[:MAX_SUMMARY_EVIDENCE_PER_FILE]
            )
            omitted_entries = len(finding.evidence) - MAX_SUMMARY_EVIDENCE_PER_FILE
            if omitted_entries > 0:
                lines.append(f"- {omitted_entries} more entries in `analysis.json`")
            lines.append("")
        omitted = len(evidence_findings) - MAX_SUMMARY_EVIDENCE_FILES
        if omitted > 0:
            lines.extend([f"Evidence from {omitted} additional files is available in `analysis.json`.", ""])
    else:
        lines.extend(["No error-pattern evidence was extracted.", ""])

    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"ERROR: input does not exist: {input_path}", file=sys.stderr)
        return 2

    output = (args.output or ((input_path if input_path.is_dir() else input_path.parent) / "report")).resolve()
    try:
        findings = [analyze_file(path, input_path) for path in candidate_files(input_path, output) if path.stat().st_size > 0]
        if not findings:
            print(f"ERROR: no non-empty error.txt, compile.txt, .log, .txt, or .out input found under {input_path}", file=sys.stderr)
            return 2
        write_reports(input_path, output, findings)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: analysis failed: {error}", file=sys.stderr)
        return 1

    print(f"Analyzed {len(findings)} files. Reports: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())