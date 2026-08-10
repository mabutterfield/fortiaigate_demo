#!/usr/bin/env python3
"""Validate current Markdown links, filenames, and release vocabulary."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)\n]+)\)")
REFERENCE_LINK_PATTERN = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
LOWER_KEBAB_MARKDOWN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
CURRENT_VOCABULARY_EXCLUSIONS = (
    "docs/historical/",
    "archived_scenarios/",
)
CURRENT_VOCABULARY_FILES_EXCLUDED = {"CHANGELOG.md"}
FILENAME_EXCEPTIONS = {
    "docs/FortiAIGate-initial-config.MD",
}
FORBIDDEN_CURRENT_PATTERNS = {
    "numbered development phase": re.compile(r"\bphase(?:\s*|[-_])\d+\b", re.IGNORECASE),
    "retired demo-letter slot": re.compile(r"\bdemo-[a-z]\b", re.IGNORECASE),
    "retired Detect Only label": re.compile(r"\bdetect[_ -]?only\b", re.IGNORECASE),
    "retired Backend Only label": re.compile(r"\bbackend only\b", re.IGNORECASE),
    "retired Advanced-mode label": re.compile(r"\badvanced (?:mode|ui)\b", re.IGNORECASE),
}


def tracked_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def tracked_markdown(paths: list[Path]) -> list[Path]:
    return sorted(
        path
        for path in paths
        if path.suffix.lower() == ".md" and (REPO_ROOT / path).is_file()
    )


def link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


def github_slug(value: str) -> str:
    value = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("`", "").strip().lower()
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r"\s+", "-", value)


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_PATTERN.match(line)
        if not match:
            continue
        base = github_slug(match.group(1))
        occurrence = counts.get(base, 0)
        counts[base] = occurrence + 1
        anchors.add(base if occurrence == 0 else f"{base}-{occurrence}")
    return anchors


def normalized_repo_target(source: Path, target: str) -> Path | None:
    target_path = Path(unquote(target))
    if target_path.is_absolute():
        return None
    source_parent = source.parent
    normalized = Path(os.path.normpath(str(source_parent / target_path)))
    try:
        normalized.relative_to(Path("."))
    except ValueError:
        return None
    return normalized


def validate_links(markdown_paths: list[Path], tracked: set[str]) -> list[str]:
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    for relative_source in markdown_paths:
        if relative_source.as_posix().startswith("docs/historical/"):
            continue
        source = REPO_ROOT / relative_source
        text = source.read_text(encoding="utf-8")
        raw_targets = [*MARKDOWN_LINK_PATTERN.findall(text), *REFERENCE_LINK_PATTERN.findall(text)]
        for raw_target in raw_targets:
            target = link_target(raw_target)
            if not target or target.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            path_part, separator, fragment = target.partition("#")
            relative_target = normalized_repo_target(
                relative_source,
                path_part or relative_source.name,
            )
            if relative_target is None:
                errors.append(f"{relative_source}: link escapes repository: {target}")
                continue
            absolute_target = REPO_ROOT / relative_target
            if not absolute_target.exists():
                errors.append(f"{relative_source}: missing link target: {target}")
                continue
            if absolute_target.is_file() and relative_target.as_posix() not in tracked:
                errors.append(
                    f"{relative_source}: link target is not tracked or has incorrect case: {target}"
                )
                continue
            if separator and fragment and absolute_target.suffix.lower() == ".md":
                anchors = anchor_cache.setdefault(
                    absolute_target,
                    markdown_anchors(absolute_target),
                )
                expected_anchor = unquote(fragment).lower()
                if expected_anchor not in anchors:
                    errors.append(
                        f"{relative_source}: missing anchor #{fragment} in {relative_target}"
                    )
    return errors


def validate_doc_filenames(markdown_paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in markdown_paths:
        if not path.parts or path.parts[0] != "docs":
            continue
        if path.as_posix() in FILENAME_EXCEPTIONS or path.name == "README.md":
            continue
        if not LOWER_KEBAB_MARKDOWN.fullmatch(path.name):
            errors.append(f"{path}: documentation filename must be lowercase kebab-case")
    return errors


def validate_current_vocabulary(markdown_paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in markdown_paths:
        path_text = path.as_posix()
        if path_text in CURRENT_VOCABULARY_FILES_EXCLUDED:
            continue
        if any(path_text.startswith(prefix) for prefix in CURRENT_VOCABULARY_EXCLUSIONS):
            continue
        for line_number, line in enumerate(
            (REPO_ROOT / path).read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            for label, pattern in FORBIDDEN_CURRENT_PATTERNS.items():
                if pattern.search(line):
                    errors.append(f"{path}:{line_number}: {label}: {line.strip()}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check tracked Markdown links, current documentation filenames, and release vocabulary."
    )
    return parser.parse_args()


def main() -> int:
    parse_args()
    paths = tracked_paths()
    markdown_paths = tracked_markdown(paths)
    tracked = {path.as_posix() for path in paths}
    errors = [
        *validate_links(markdown_paths, tracked),
        *validate_doc_filenames(markdown_paths),
        *validate_current_vocabulary(markdown_paths),
    ]
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        print(f"Documentation quality failed with {len(errors)} issue(s).")
        return 1
    print(
        f"PASS: {len(markdown_paths)} tracked Markdown files have valid local links, "
        "filenames, and current vocabulary."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
