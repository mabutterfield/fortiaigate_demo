#!/usr/bin/env python3
"""Append missing top-level defaults from example config files into local files."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PAIRS = [
    ("terraform/user.tfvars.example", "terraform/user.tfvars"),
    ("ansible/group_vars/user.yml.example", "ansible/group_vars/user.yml"),
]

TOP_LEVEL_PATTERNS = {
    "hcl": re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*="),
    "yaml": re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:"),
}


@dataclass(frozen=True)
class ConfigPair:
    source: Path
    target: Path


@dataclass(frozen=True)
class VarBlock:
    key: str
    start_line: int
    end_line: int
    lines: list[str]


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def detect_format(path: Path) -> str:
    name = path.name
    if name.endswith((".tfvars", ".tfvars.example")):
        return "hcl"
    if name.endswith((".yml", ".yaml", ".yml.example", ".yaml.example")):
        return "yaml"
    raise SystemExit(f"Unsupported config file type: {path}")


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"File does not exist: {path}")
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def top_level_key_indexes(lines: list[str], file_format: str) -> list[tuple[int, str]]:
    indexes: list[tuple[int, str]] = []
    pattern = TOP_LEVEL_PATTERNS[file_format]
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            indexes.append((index, match.group(1)))
    return indexes


def include_preceding_comment_lines(lines: list[str], key_index: int) -> int:
    """Include nearby comments that describe a var, but avoid file headers."""
    block_start = key_index
    cursor = key_index - 1
    while cursor >= 0:
        stripped = lines[cursor].strip()
        if stripped == "" or stripped.startswith("#"):
            block_start = cursor
            cursor -= 1
            continue
        break

    # Keep the top file banner with the file, not with the first variable.
    if cursor < 0:
        return key_index
    return block_start


def parse_var_blocks(lines: list[str], file_format: str) -> dict[str, VarBlock]:
    indexes = top_level_key_indexes(lines, file_format)
    block_starts = [include_preceding_comment_lines(lines, key_index) for key_index, _key in indexes]
    blocks: dict[str, VarBlock] = {}
    for position, (_key_index, key) in enumerate(indexes):
        block_start = block_starts[position]
        next_index = block_starts[position + 1] if position + 1 < len(block_starts) else len(lines)
        blocks[key] = VarBlock(
            key=key,
            start_line=block_start + 1,
            end_line=next_index,
            lines=lines[block_start:next_index],
        )
    return blocks


def render_missing_section(missing_blocks: list[VarBlock], source: Path) -> list[str]:
    if not missing_blocks:
        return []

    rendered: list[str] = [
        "\n",
        f"# === Synced defaults from {source.name} ===\n",
        f"# Added by scripts/sync_all_vars.py from {relative_path(source)}.\n",
        "# Existing local values above were preserved; review these defaults before deployment.\n",
    ]
    for block in missing_blocks:
        if rendered[-1].strip() != "":
            rendered.append("\n")
        rendered.extend(block.lines)
        if rendered[-1] and not rendered[-1].endswith("\n"):
            rendered[-1] += "\n"
    return rendered


def sync_missing_vars(source: Path, target: Path) -> tuple[list[str], str]:
    source_format = detect_format(source)
    target_format = detect_format(target)
    if source_format != target_format:
        raise SystemExit(f"Source/target file types do not match: {source} -> {target}")

    source_lines = read_lines(source)
    source_blocks = parse_var_blocks(source_lines, source_format)

    if target.exists():
        target_lines = read_lines(target)
    else:
        target_lines = []
    target_keys = set(parse_var_blocks(target_lines, target_format))

    missing_keys = [key for key in source_blocks if key not in target_keys]
    missing_blocks = [source_blocks[key] for key in missing_keys]
    synced_lines = target_lines + render_missing_section(missing_blocks, source)
    return missing_keys, "".join(synced_lines)


def configured_pairs(args: argparse.Namespace) -> list[ConfigPair]:
    if args.source or args.target:
        if not args.source or not args.target:
            raise SystemExit("--source and --target must be used together.")
        return [ConfigPair((REPO_ROOT / args.source).resolve(), (REPO_ROOT / args.target).resolve())]

    return [ConfigPair((REPO_ROOT / source).resolve(), (REPO_ROOT / target).resolve()) for source, target in DEFAULT_PAIRS]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append missing top-level defaults from example config files into local config files."
    )
    parser.add_argument(
        "--source",
        default="",
        help="Example file to read from. Must be used with --target. Default syncs all known local/example pairs.",
    )
    parser.add_argument(
        "--target",
        default="",
        help="Local file to update. Must be used with --source. Default syncs all known local/example pairs.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only report missing settings; exit 1 when any target is missing settings.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print unified diffs without writing changes.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the default example/local pairs and exit.",
    )
    return parser.parse_args()


def sync_pair(pair: ConfigPair, *, check: bool, dry_run: bool) -> bool:
    missing_keys, synced_content = sync_missing_vars(pair.source, pair.target)
    if not missing_keys:
        print(f"{relative_path(pair.target)} already contains all top-level settings from {relative_path(pair.source)}.")
        return False

    print(f"{relative_path(pair.target)} is missing settings from {relative_path(pair.source)}:")
    for key in missing_keys:
        print(f"- {key}")

    if check:
        return True

    current_content = pair.target.read_text(encoding="utf-8") if pair.target.exists() else ""
    if dry_run:
        diff = difflib.unified_diff(
            current_content.splitlines(keepends=True),
            synced_content.splitlines(keepends=True),
            fromfile=relative_path(pair.target),
            tofile=relative_path(pair.target) + " (synced)",
        )
        sys.stdout.writelines(diff)
        return True

    pair.target.parent.mkdir(parents=True, exist_ok=True)
    pair.target.write_text(synced_content, encoding="utf-8")
    print(f"updated: {relative_path(pair.target)}")
    return True


def main() -> None:
    args = parse_args()
    pairs = configured_pairs(args)

    if args.list:
        for pair in pairs:
            print(f"{relative_path(pair.source)} -> {relative_path(pair.target)}")
        return

    changed_or_missing = False
    for pair in pairs:
        changed_or_missing = sync_pair(pair, check=args.check, dry_run=args.dry_run) or changed_or_missing

    if args.check and changed_or_missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
