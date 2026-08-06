#!/usr/bin/env python3
"""Manage ignored, operator-editable Phase 11 scenario installations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = REPO_ROOT / "chatbot" / "scenarios"
EXAMPLES_ROOT = SCENARIO_ROOT / "examples"
LOCAL_ROOT = SCENARIO_ROOT / "local"
STATE_PATH = LOCAL_ROOT / "installed-scenarios.json"
RAW_OUTPUT_ROOT = REPO_ROOT / "docs" / "raw-output" / "scenario-work-orders"
STATE_SCHEMA_VERSION = 1

IGNORED_PACKAGE_NAMES = {
    ".DS_Store",
    "__pycache__",
}
IGNORED_PACKAGE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".swp",
    ".swo",
}


class LocalScenarioError(RuntimeError):
    """Raised when a local scenario operation cannot be completed safely."""


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "installed_scenarios": [],
        "stale_faig_objects": [],
    }


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as json_file:
            value = json.load(json_file)
    except json.JSONDecodeError as exc:
        raise LocalScenarioError(f"Invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise LocalScenarioError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LocalScenarioError(f"Expected a JSON object in {path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as json_file:
            json.dump(value, json_file, indent=2, sort_keys=True)
            json_file.write("\n")
            json_file.flush()
            os.fsync(json_file.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    except OSError as exc:
        raise LocalScenarioError(f"Unable to write {path} atomically: {exc}") from exc
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def package_file_is_ignored(path: Path) -> bool:
    return (
        any(part in IGNORED_PACKAGE_NAMES for part in path.parts)
        or path.name.endswith("~")
        or path.suffix in IGNORED_PACKAGE_SUFFIXES
    )


def package_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise LocalScenarioError(f"Scenario package directory does not exist: {root}")
    files: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative_path = path.relative_to(root)
        if package_file_is_ignored(relative_path):
            continue
        if path.is_symlink():
            raise LocalScenarioError(f"Scenario packages cannot contain symlinks: {path}")
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise LocalScenarioError(f"Scenario packages cannot contain special files: {path}")
    return files


def package_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in package_files(root):
        relative_path = path.relative_to(root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        try:
            with path.open("rb") as package_file:
                for chunk in iter(lambda: package_file.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise LocalScenarioError(f"Unable to hash {path}: {exc}") from exc
        digest.update(b"\0")
    return digest.hexdigest()


def relative_to_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def timestamped_path(root: Path, scenario_id: str, *, now: int) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    candidate = root / scenario_id / timestamp
    if candidate.exists():
        candidate = root / scenario_id / f"{timestamp}-{uuid.uuid4().hex[:8]}"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def entry_points_from_profile(profile_path: Path, scenario_id: str) -> list[dict[str, Any]]:
    if not profile_path.is_file():
        return []
    profile = read_json_object(profile_path)
    matrix = profile.get("matrix")
    if not isinstance(matrix, dict):
        return []
    raw_entry_points = matrix.get("entry_points")
    if not isinstance(raw_entry_points, list):
        return []
    entry_points: list[dict[str, Any]] = []
    for raw_entry_point in raw_entry_points:
        if not isinstance(raw_entry_point, dict):
            continue
        role = str(raw_entry_point.get("role") or "").strip()
        if not role:
            continue
        entry_points.append(
            {
                "role": role,
                "display_name": str(raw_entry_point.get("display_name") or role),
                "uri": f"/v1/{scenario_id}/{role}",
                "route": f"{scenario_id}-{role}",
                "suggested_flow_name": f"{scenario_id}-{role}",
                "suggested_guard_name": f"{scenario_id}_{role}".replace("-", "_"),
                "guard_template": str(raw_entry_point.get("guard_template") or ""),
                "guard_next_hop_model": scenario_id,
                "expected_behavior": str(raw_entry_point.get("expected_behavior") or ""),
                "required_for_release": bool(raw_entry_point.get("required_for_release", False)),
            }
        )
    return entry_points


class LocalScenarioStore:
    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        local_root: Path = LOCAL_ROOT,
        raw_output_root: Path = RAW_OUTPUT_ROOT,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.local_root = local_root.resolve()
        self.state_path = self.local_root / "installed-scenarios.json"
        self.backup_root = self.local_root / "_backups"
        self.removed_root = self.local_root / "_removed"
        self.raw_output_root = raw_output_root.resolve()

    def scenario_path(self, scenario_id: str) -> Path:
        return self.local_root / scenario_id

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return empty_state()
        state = read_json_object(self.state_path)
        self.validate_state(state)
        return state

    def validate_state(self, state: dict[str, Any]) -> None:
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            raise LocalScenarioError(
                f"Unsupported installed scenario state version in {self.state_path}; "
                f"expected {STATE_SCHEMA_VERSION}"
            )
        installed = state.get("installed_scenarios")
        if not isinstance(installed, list):
            raise LocalScenarioError("installed_scenarios must be a list")
        stale_objects = state.get("stale_faig_objects")
        if not isinstance(stale_objects, list):
            raise LocalScenarioError("stale_faig_objects must be a list")
        scenario_ids: list[str] = []
        required_entry_fields = {
            "scenario_id",
            "installed_at",
            "updated_at",
            "source_profile",
            "source_hash",
            "installed_hash",
        }
        for index, entry in enumerate(installed):
            if not isinstance(entry, dict):
                raise LocalScenarioError(f"installed_scenarios[{index}] must be an object")
            missing = sorted(required_entry_fields - set(entry))
            if missing:
                raise LocalScenarioError(
                    f"installed_scenarios[{index}] is missing: {', '.join(missing)}"
                )
            scenario_ids.append(str(entry.get("scenario_id") or ""))
        duplicates = sorted(
            scenario_id
            for scenario_id in set(scenario_ids)
            if scenario_ids.count(scenario_id) > 1
        )
        if duplicates:
            raise LocalScenarioError(
                f"installed_scenarios contains duplicate IDs: {', '.join(duplicates)}"
            )

    def write_state(self, state: dict[str, Any]) -> None:
        self.validate_state(state)
        state["installed_scenarios"] = sorted(
            state["installed_scenarios"],
            key=lambda entry: entry["scenario_id"],
        )
        state["stale_faig_objects"] = sorted(
            state["stale_faig_objects"],
            key=lambda entry: (entry.get("scenario_id", ""), entry.get("recorded_at", 0)),
        )
        atomic_write_json(self.state_path, state)

    def find_entry(self, state: dict[str, Any], scenario_id: str) -> dict[str, Any] | None:
        return next(
            (
                entry
                for entry in state["installed_scenarios"]
                if entry.get("scenario_id") == scenario_id
            ),
            None,
        )

    def source_path(self, entry: dict[str, Any]) -> Path:
        source_profile = Path(str(entry.get("source_profile") or ""))
        if source_profile.is_absolute():
            return source_profile
        return self.repo_root / source_profile

    def status_for_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        scenario_id = str(entry["scenario_id"])
        local_package = self.scenario_path(scenario_id)
        source_profile = self.source_path(entry)
        source_package = source_profile.parent
        local_exists = local_package.is_dir()
        source_exists = source_profile.is_file()
        local_hash = package_hash(local_package) if local_exists else ""
        source_hash = package_hash(source_package) if source_exists else ""
        return {
            **entry,
            "local_path": relative_to_repo(local_package),
            "local_exists": local_exists,
            "local_hash": local_hash,
            "local_modified": bool(local_exists and local_hash != entry.get("installed_hash")),
            "source_exists": source_exists,
            "current_source_hash": source_hash,
            "source_update_available": bool(source_exists and source_hash != entry.get("source_hash")),
        }

    def orphan_packages(self, state: dict[str, Any]) -> list[str]:
        installed_ids = {
            str(entry.get("scenario_id") or "")
            for entry in state["installed_scenarios"]
        }
        if not self.local_root.exists():
            return []
        ignored_names = {"_backups", "_removed"}
        return sorted(
            path.name
            for path in self.local_root.iterdir()
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name not in ignored_names
            and path.name not in installed_ids
        )

    def list_installed(self) -> dict[str, Any]:
        state = self.load_state()
        return {
            "installed_scenarios": [
                self.status_for_entry(entry)
                for entry in state["installed_scenarios"]
            ],
            "orphan_packages": self.orphan_packages(state),
            "stale_faig_objects": state["stale_faig_objects"],
        }

    def stage_package(self, source_package: Path) -> tuple[Path, Path]:
        package_files(source_package)
        self.local_root.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(prefix=".scenario-stage-", dir=self.local_root)
        )
        staged_package = staging_root / "package"
        try:
            shutil.copytree(source_package, staged_package)
            if package_hash(staged_package) != package_hash(source_package):
                raise LocalScenarioError("Staged scenario package hash does not match its source")
        except (OSError, LocalScenarioError) as exc:
            shutil.rmtree(staging_root, ignore_errors=True)
            if isinstance(exc, LocalScenarioError):
                raise
            raise LocalScenarioError(f"Unable to stage scenario package: {exc}") from exc
        return staging_root, staged_package

    def clear_restored_stale_roles(
        self,
        state: dict[str, Any],
        scenario_id: str,
        active_roles: set[str],
    ) -> None:
        retained: list[dict[str, Any]] = []
        for stale_entry in state["stale_faig_objects"]:
            if stale_entry.get("scenario_id") != scenario_id:
                retained.append(stale_entry)
                continue
            stale_entry = dict(stale_entry)
            stale_entry["entry_points"] = [
                entry_point
                for entry_point in stale_entry.get("entry_points", [])
                if entry_point.get("role") not in active_roles
            ]
            if stale_entry["entry_points"]:
                retained.append(stale_entry)
        state["stale_faig_objects"] = retained

    def add(
        self,
        scenario_id: str,
        source_profile: Path,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        operation_time = int(now if now is not None else time.time())
        state = self.load_state()
        existing_entry = self.find_entry(state, scenario_id)
        if existing_entry:
            status = self.status_for_entry(existing_entry)
            return {
                "changed": False,
                "warning": (
                    f"{scenario_id} is already installed; no files were changed. "
                    "Use update to inspect it or update --force to replace it."
                ),
                "status": status,
            }
        destination = self.scenario_path(scenario_id)
        if destination.exists():
            raise LocalScenarioError(
                f"Local package exists but is not registered: {destination}. "
                "Move it aside before adding the scenario."
            )
        source_profile = source_profile.resolve()
        if not source_profile.is_file():
            raise LocalScenarioError(f"Scenario profile does not exist: {source_profile}")
        source_package = source_profile.parent
        source_hash = package_hash(source_package)
        staging_root, staged_package = self.stage_package(source_package)
        entry = {
            "scenario_id": scenario_id,
            "installed_at": operation_time,
            "updated_at": operation_time,
            "source_profile": relative_to_repo(source_profile),
            "source_hash": source_hash,
            "installed_hash": package_hash(staged_package),
        }
        try:
            os.replace(staged_package, destination)
            state["installed_scenarios"].append(entry)
            active_roles = {
                item["role"]
                for item in entry_points_from_profile(destination / "profile.json", scenario_id)
            }
            self.clear_restored_stale_roles(state, scenario_id, active_roles)
            try:
                self.write_state(state)
            except LocalScenarioError:
                shutil.rmtree(destination, ignore_errors=True)
                raise
        except OSError as exc:
            raise LocalScenarioError(f"Unable to install {scenario_id}: {exc}") from exc
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
        return {
            "changed": True,
            "installed_path": relative_to_repo(destination),
            "status": self.status_for_entry(entry),
        }

    def update(
        self,
        scenario_id: str,
        source_profile: Path,
        *,
        force: bool = False,
        now: int | None = None,
    ) -> dict[str, Any]:
        operation_time = int(now if now is not None else time.time())
        state = self.load_state()
        entry = self.find_entry(state, scenario_id)
        if not entry:
            raise LocalScenarioError(f"{scenario_id} is not installed; use add first")
        status = self.status_for_entry(entry)
        if not force:
            return {
                "changed": False,
                "warning": (
                    "No files were changed. Use update --force to back up the local "
                    "package and replace it from the tracked example."
                ),
                "status": status,
            }

        source_profile = source_profile.resolve()
        if not source_profile.is_file():
            raise LocalScenarioError(f"Scenario profile does not exist: {source_profile}")
        source_package = source_profile.parent
        source_hash = package_hash(source_package)
        staging_root, staged_package = self.stage_package(source_package)
        destination = self.scenario_path(scenario_id)
        old_entry_points = entry_points_from_profile(destination / "profile.json", scenario_id)
        backup_path: Path | None = None
        replacement_installed = False
        try:
            if destination.exists():
                backup_path = timestamped_path(
                    self.backup_root,
                    scenario_id,
                    now=operation_time,
                )
                os.replace(destination, backup_path)
            os.replace(staged_package, destination)
            replacement_installed = True
            new_entry_points = entry_points_from_profile(destination / "profile.json", scenario_id)
            new_roles = {entry_point["role"] for entry_point in new_entry_points}
            removed_entry_points = [
                entry_point
                for entry_point in old_entry_points
                if entry_point["role"] not in new_roles
            ]
            if removed_entry_points:
                state["stale_faig_objects"].append(
                    {
                        "scenario_id": scenario_id,
                        "recorded_at": operation_time,
                        "reason": "scenario-update",
                        "entry_points": removed_entry_points,
                    }
                )
            self.clear_restored_stale_roles(state, scenario_id, new_roles)
            entry.update(
                {
                    "updated_at": operation_time,
                    "source_profile": relative_to_repo(source_profile),
                    "source_hash": source_hash,
                    "installed_hash": package_hash(destination),
                }
            )
            try:
                self.write_state(state)
            except LocalScenarioError:
                shutil.rmtree(destination, ignore_errors=True)
                replacement_installed = False
                if backup_path and backup_path.exists():
                    os.replace(backup_path, destination)
                raise
        except OSError as exc:
            if replacement_installed:
                shutil.rmtree(destination, ignore_errors=True)
            if backup_path and backup_path.exists() and not destination.exists():
                os.replace(backup_path, destination)
            raise LocalScenarioError(f"Unable to update {scenario_id}: {exc}") from exc
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
        return {
            "changed": True,
            "backup_path": relative_to_repo(backup_path) if backup_path else "",
            "status": self.status_for_entry(entry),
        }

    def remove(self, scenario_id: str, *, now: int | None = None) -> dict[str, Any]:
        operation_time = int(now if now is not None else time.time())
        state = self.load_state()
        entry = self.find_entry(state, scenario_id)
        if not entry:
            raise LocalScenarioError(f"{scenario_id} is not installed")
        destination = self.scenario_path(scenario_id)
        stale_entry_points = entry_points_from_profile(destination / "profile.json", scenario_id)
        archive_path: Path | None = None
        try:
            if destination.exists():
                archive_path = timestamped_path(
                    self.removed_root,
                    scenario_id,
                    now=operation_time,
                )
                os.replace(destination, archive_path)
            state["installed_scenarios"] = [
                installed_entry
                for installed_entry in state["installed_scenarios"]
                if installed_entry.get("scenario_id") != scenario_id
            ]
            if stale_entry_points:
                state["stale_faig_objects"].append(
                    {
                        "scenario_id": scenario_id,
                        "recorded_at": operation_time,
                        "reason": "scenario-remove",
                        "entry_points": stale_entry_points,
                    }
                )
            try:
                self.write_state(state)
            except LocalScenarioError:
                if archive_path and archive_path.exists():
                    os.replace(archive_path, destination)
                raise
        except OSError as exc:
            if archive_path and archive_path.exists() and not destination.exists():
                os.replace(archive_path, destination)
            raise LocalScenarioError(f"Unable to remove {scenario_id}: {exc}") from exc
        return {
            "changed": True,
            "archive_path": relative_to_repo(archive_path) if archive_path else "",
            "stale_entry_points": stale_entry_points,
        }

    def acknowledge_stale(self, scenario_id: str | None = None) -> dict[str, Any]:
        state = self.load_state()
        before = len(state["stale_faig_objects"])
        if scenario_id:
            state["stale_faig_objects"] = [
                entry
                for entry in state["stale_faig_objects"]
                if entry.get("scenario_id") != scenario_id
            ]
        else:
            state["stale_faig_objects"] = []
        removed = before - len(state["stale_faig_objects"])
        if removed:
            self.write_state(state)
        return {"changed": bool(removed), "acknowledged": removed}

    def matrix_summary(self) -> dict[str, Any]:
        state = self.load_state()
        installed_scenarios: list[dict[str, Any]] = []
        for entry in state["installed_scenarios"]:
            scenario_id = str(entry["scenario_id"])
            local_package = self.scenario_path(scenario_id)
            profile_path = local_package / "profile.json"
            if not profile_path.is_file():
                raise LocalScenarioError(
                    f"Installed scenario profile is missing: {profile_path}. "
                    f"Use update {scenario_id} --force to restore it."
                )
            profile = read_json_object(profile_path)
            matrix = profile.get("matrix")
            if profile.get("schema_version") != 2 or not isinstance(matrix, dict):
                raise LocalScenarioError(
                    f"Installed scenario {scenario_id} is not a schema v2 matrix profile"
                )
            status = self.status_for_entry(entry)
            installed_scenarios.append(
                {
                    "scenario_id": scenario_id,
                    "display_name": str(profile.get("display_name") or scenario_id),
                    "local_profile": relative_to_repo(profile_path),
                    "content_hash": status["local_hash"],
                    "source_hash": entry["source_hash"],
                    "source_update_available": status["source_update_available"],
                    "model_alias": scenario_id,
                    "llm_target": matrix.get("llm_target", "llm-default"),
                    "instruction_profile": matrix.get(
                        "instruction_profile",
                        {
                            "source": "scenario_instruction",
                            "position": "prepend",
                            "enabled": True,
                        },
                    ),
                    "instruction_file": relative_to_repo(
                        local_package / str(profile.get("instruction_file") or "instructions.txt")
                    ),
                    "mcp": profile.get("mcp", {}),
                    "entry_points": entry_points_from_profile(profile_path, scenario_id),
                    "frontend_instruction_profiles": matrix.get(
                        "frontend_instruction_profiles", []
                    ),
                    "chatbot_profiles": matrix.get("chatbot_profiles", []),
                    "faig_chain": matrix.get("faig_chain", {"enabled": False}),
                }
            )
        return {
            "schema_version": 1,
            "global": {
                "passthrough_model_alias": "pass-model",
                "faig_passthrough_uri": "/v1/passthrough",
            },
            "installed_scenarios": installed_scenarios,
            "stale_faig_objects": state["stale_faig_objects"],
        }

    def render_work_order(self) -> str:
        matrix = self.matrix_summary()
        lines = [
            "# FAIG Scenario Work Order",
            "",
            "## Global Controls",
            "",
            "- LiteLLM passthrough alias: `pass-model`",
            "- FAIG passthrough configured URI: `/v1/passthrough/*`",
            "- Behavior: no scenario instructions",
            "",
            "## Installed Scenarios",
            "",
        ]
        if not matrix["installed_scenarios"]:
            lines.extend(["No scenarios are installed.", ""])
        for scenario in matrix["installed_scenarios"]:
            scenario_id = scenario["scenario_id"]
            lines.extend(
                [
                    f"### `{scenario_id}`",
                    "",
                    f"- LiteLLM alias: `{scenario_id}`",
                    f"- Underlying target: `{scenario['llm_target']}`",
                    f"- Local profile: `{scenario['local_profile']}`",
                    "",
                    "| Role | Suggested flow | Configured URI | Suggested guard | Next-hop model | Guard template | Required | Expected behavior |",
                    "|---|---|---|---|---|---|---|---|",
                ]
            )
            for entry_point in scenario["entry_points"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            entry_point["display_name"],
                            f"`{entry_point['suggested_flow_name']}`",
                            f"`{entry_point['uri']}/*`",
                            f"`{entry_point['suggested_guard_name']}`",
                            f"`{entry_point['guard_next_hop_model']}`",
                            f"`{entry_point['guard_template']}`",
                            "yes" if entry_point["required_for_release"] else "no",
                            entry_point["expected_behavior"].replace("|", "\\|"),
                        ]
                    )
                    + " |"
                )
            lines.append("")
            lines.extend(
                [
                    "Guard and flow names may differ, but the configured URI and guard next-hop",
                    "LiteLLM model alias must match this work order.",
                    "",
                ]
            )

        lines.extend(["## Stale FAIG Objects", ""])
        if not matrix["stale_faig_objects"]:
            lines.extend(["No stale FAIG objects are recorded.", ""])
        else:
            lines.extend(
                [
                    "These objects are not removed automatically. Remove them manually in the FAIG GUI,",
                    "then acknowledge the stale record with `scenario_profiles.py ack-stale`.",
                    "",
                    "| Scenario | Configured URI | Suggested guard | Reason |",
                    "|---|---|---|---|",
                ]
            )
            for stale in matrix["stale_faig_objects"]:
                for entry_point in stale.get("entry_points", []):
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                f"`{stale.get('scenario_id', '')}`",
                                f"`{entry_point.get('uri', '')}/*`",
                                f"`{entry_point.get('suggested_guard_name', '')}`",
                                str(stale.get("reason", "")),
                            ]
                        )
                        + " |"
                    )
            lines.append("")
        return "\n".join(lines)

    def write_work_order(self, output_path: Path, *, force: bool = False) -> Path:
        output_path = output_path.resolve()
        if output_path.exists() and not force:
            raise LocalScenarioError(
                f"Work order already exists: {output_path}. Use --force to replace it."
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            output_path.write_text(self.render_work_order(), encoding="utf-8")
        except OSError as exc:
            raise LocalScenarioError(f"Unable to write work order {output_path}: {exc}") from exc
        return output_path
