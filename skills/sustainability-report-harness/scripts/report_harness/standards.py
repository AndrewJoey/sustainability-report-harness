"""Reviewed standard-package registry, recommendation, and immutable project locking."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .audit import append_event
from .config import load_project_config
from .errors import HarnessError
from .io import read_json, write_json, write_yaml
from .models import Requirement, StandardVersion
from .workflow import WorkflowStore

PACKAGE_STATUSES = {"simulated", "reviewed", "published"}
LOCK_PATH = Path("state/standards.lock.json")


def calculate_standard_content_hash(
    clauses: list[dict[str, Any]], requirements: list[dict[str, Any]]
) -> str:
    canonical = json.dumps(
        {"clauses": clauses, "requirements": requirements},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def calculate_lock_hash(lock: dict[str, Any]) -> str:
    payload = {key: value for key, value in lock.items() if key != "lock_hash"}
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def load_standard_package(path: Path) -> dict[str, Any]:
    try:
        package = read_json(path)
    except HarnessError:
        raise
    if not isinstance(package, dict):
        raise HarnessError(
            "INVALID_STANDARD_PACKAGE", "Standard package must be an object", str(path)
        )
    errors = validate_standard_package(package)
    if errors:
        raise HarnessError(
            "INVALID_STANDARD_PACKAGE",
            "Standard package validation failed",
            str(path),
            {"errors": errors},
        )
    return package


def validate_standard_package(package: Any) -> list[str]:
    if not isinstance(package, dict):
        return ["package: object required"]
    errors: list[str] = []
    package_status = package.get("package_status")
    if package_status not in PACKAGE_STATUSES:
        errors.append(f"package_status: must be one of {sorted(PACKAGE_STATUSES)}")
    raw_version = package.get("standard_version")
    version: StandardVersion | None = None
    if not isinstance(raw_version, dict):
        errors.append("standard_version: object required")
    else:
        try:
            version = StandardVersion.from_dict(raw_version)
        except HarnessError as exc:
            errors.append(f"standard_version: {exc}")
    raw_requirements = package.get("requirements")
    raw_clauses = package.get("clauses")
    clauses: dict[str, str] = {}
    if not isinstance(raw_clauses, list) or not raw_clauses:
        errors.append("clauses: non-empty list required")
    else:
        for index, raw_clause in enumerate(raw_clauses):
            if not isinstance(raw_clause, dict):
                errors.append(f"clauses[{index}]: object required")
                continue
            clause_id = raw_clause.get("clause_id")
            original_text = raw_clause.get("original_text")
            if not isinstance(clause_id, str) or not clause_id.strip():
                errors.append(f"clauses[{index}].clause_id: non-empty string required")
                continue
            if clause_id in clauses:
                errors.append(f"clauses[{index}].clause_id: duplicate {clause_id}")
            if not isinstance(original_text, str) or not original_text.strip():
                errors.append(f"clauses[{index}].original_text: non-empty string required")
                continue
            clauses[clause_id] = original_text
    requirements: list[Requirement] = []
    if not isinstance(raw_requirements, list) or not raw_requirements:
        errors.append("requirements: non-empty list required")
    else:
        seen: set[str] = set()
        for index, raw in enumerate(raw_requirements):
            try:
                requirement = Requirement.from_dict(raw) if isinstance(raw, dict) else None
            except HarnessError as exc:
                errors.append(f"requirements[{index}]: {exc}")
                continue
            if requirement is None:
                errors.append(f"requirements[{index}]: object required")
                continue
            if requirement.requirement_id in seen:
                errors.append(
                    f"requirements[{index}].requirement_id: duplicate {requirement.requirement_id}"
                )
            seen.add(requirement.requirement_id)
            requirements.append(requirement)
            clause_text = clauses.get(requirement.clause_id)
            if clause_text is None:
                errors.append(f"requirements[{index}].clause_id: unknown source clause")
            elif requirement.original_text != clause_text:
                errors.append(f"requirements[{index}].original_text: does not match source clause")
            if version and (
                requirement.standard_id != version.standard_id
                or requirement.version_id != version.version_id
            ):
                errors.append(f"requirements[{index}]: standard/version does not match package")
    referenced_clauses = {item.clause_id for item in requirements}
    for clause_id in sorted(set(clauses) - referenced_clauses):
        errors.append(f"clauses.{clause_id}: source clause has no decomposed requirement")
    if version and isinstance(raw_requirements, list) and isinstance(raw_clauses, list):
        actual_hash = calculate_standard_content_hash(raw_clauses, raw_requirements)
        if version.content_hash != actual_hash:
            errors.append("standard_version.content_hash: does not match requirements payload")
        if package_status == "simulated":
            notice = package.get("fixture_notice")
            if not isinstance(notice, str) or "NOT AN OFFICIAL STANDARD" not in notice:
                errors.append("fixture_notice: simulated packages require an explicit warning")
        else:
            if version.review_status not in {"reviewed", "published"}:
                errors.append(
                    "standard_version.review_status: reviewed package cannot remain draft"
                )
            if (
                not isinstance(package.get("reviewed_by"), str)
                or not package["reviewed_by"].strip()
            ):
                errors.append("reviewed_by: reviewed packages require a named reviewer")
            if not isinstance(package.get("reviewed_at"), str):
                errors.append("reviewed_at: reviewed packages require a review timestamp")
            else:
                try:
                    datetime.fromisoformat(package["reviewed_at"])
                except ValueError:
                    errors.append("reviewed_at: expected an ISO-8601 timestamp")
            if any(item.review_status == "draft" for item in requirements):
                errors.append("requirements: reviewed packages cannot contain draft requirements")
            if version.source_uri.startswith("urn:report-agent:simulated"):
                errors.append(
                    "standard_version.source_uri: reviewed package cannot use fixture URI"
                )
            if package_status == "published" and version.review_status != "published":
                errors.append("standard_version.review_status: published package must be published")
    return errors


def recommend_standard_versions(
    reporting_period_end: str,
    standard_ids: list[str],
    package_paths: list[Path],
) -> dict[str, Any]:
    end = date.fromisoformat(reporting_period_end)
    packages = [load_standard_package(path.resolve()) for path in package_paths]
    recommendations: list[dict[str, Any]] = []
    missing: list[str] = []
    for standard_id in standard_ids:
        candidates = []
        for package in packages:
            raw = package["standard_version"]
            if raw["standard_id"] != standard_id:
                continue
            effective_from = date.fromisoformat(raw["effective_from"])
            effective_to = date.fromisoformat(raw["effective_to"]) if raw["effective_to"] else None
            if effective_from <= end and (effective_to is None or end <= effective_to):
                candidates.append(package)
        if not candidates:
            missing.append(standard_id)
            continue
        selected = max(
            candidates,
            key=lambda item: date.fromisoformat(item["standard_version"]["effective_from"]),
        )
        recommendations.append(
            {
                "standard_version": selected["standard_version"],
                "package_status": selected["package_status"],
            }
        )
    return {"recommendations": recommendations, "missing_standard_ids": missing}


def lock_standard_versions(
    project_dir: Path,
    package_paths: list[Path],
    *,
    confirmed_by: str,
    allow_simulated: bool = False,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    if not confirmed_by.strip():
        raise HarnessError("APPROVER_REQUIRED", "confirmed_by is required")
    store = WorkflowStore(project_dir)
    workflow = store.load()
    if workflow["workflow_state"] != "awaiting_standard_confirmation":
        raise HarnessError(
            "STANDARD_LOCK_NOT_ALLOWED",
            "Standards can only be locked while awaiting standard confirmation",
            "workflow_state",
        )
    packages = [load_standard_package(path.resolve()) for path in package_paths]
    if not packages:
        raise HarnessError("MISSING_STANDARDS", "At least one standard package is required")
    if any(item["package_status"] == "simulated" for item in packages) and not allow_simulated:
        raise HarnessError(
            "SIMULATED_STANDARD_REQUIRES_CONFIRMATION",
            "Use allow_simulated only for development or structural tests",
        )
    pairs = [
        (
            item["standard_version"]["standard_id"],
            item["standard_version"]["version_id"],
        )
        for item in packages
    ]
    if len(pairs) != len(set(pairs)):
        raise HarnessError("DUPLICATE_STANDARD_VERSION", "Standard/version pairs must be unique")
    standard_ids = [pair[0] for pair in pairs]
    if len(standard_ids) != len(set(standard_ids)):
        raise HarnessError(
            "MULTIPLE_VERSIONS_SELECTED",
            "A project can lock only one version of each standard",
        )

    lock = {
        "schema_version": "1.0.0",
        "confirmed_by": confirmed_by,
        "locked_at": datetime.now(UTC).isoformat(),
        "standards": packages,
    }
    lock["lock_hash"] = calculate_lock_hash(lock)
    write_json(project_dir / LOCK_PATH, lock)
    config = load_project_config(project_dir)
    config["selected_standards"] = [
        {
            "standard_id": standard_id,
            "version_id": version_id,
            "confirmed_by_user": True,
        }
        for standard_id, version_id in pairs
    ]
    write_yaml(project_dir / "project.yaml", config)
    store.set_checkpoint(
        "standards",
        "approved",
        approved_by=confirmed_by,
        artifacts=[LOCK_PATH.as_posix(), "project.yaml"],
        notes=f"Locked {len(packages)} standard version(s)",
    )
    store.transition("ingesting_sources")
    append_event(
        project_dir,
        project_id=str(config["project_id"]),
        event="standards.locked",
        message=f"Locked {len(packages)} user-confirmed standard version(s)",
        details={"standard_versions": [f"{a}:{b}" for a, b in pairs]},
    )
    return {
        "valid": True,
        "locked_standards": config["selected_standards"],
        "workflow_state": store.load()["workflow_state"],
        "artifact": LOCK_PATH.as_posix(),
    }


def validate_project_standard_lock(project_dir: Path) -> list[str]:
    path = project_dir / LOCK_PATH
    if not path.is_file():
        return []
    try:
        lock = read_json(path)
    except HarnessError as exc:
        return [str(exc)]
    if not isinstance(lock, dict) or not isinstance(lock.get("standards"), list):
        return [f"{LOCK_PATH}: standards list required"]
    errors: list[str] = []
    if not isinstance(lock.get("confirmed_by"), str) or not lock["confirmed_by"].strip():
        errors.append(f"{LOCK_PATH}.confirmed_by: non-empty string required")
    if not isinstance(lock.get("locked_at"), str):
        errors.append(f"{LOCK_PATH}.locked_at: ISO-8601 timestamp required")
    else:
        try:
            datetime.fromisoformat(lock["locked_at"])
        except ValueError:
            errors.append(f"{LOCK_PATH}.locked_at: ISO-8601 timestamp required")
    if lock.get("lock_hash") != calculate_lock_hash(lock):
        errors.append(f"{LOCK_PATH}.lock_hash: locked payload has changed")
    for index, package in enumerate(lock["standards"]):
        errors.extend(
            f"{LOCK_PATH}.standards[{index}].{error}"
            for error in validate_standard_package(package)
        )
    try:
        config = load_project_config(project_dir)
    except HarnessError as exc:
        return errors + [str(exc)]
    locked_pairs = {
        (
            package.get("standard_version", {}).get("standard_id"),
            package.get("standard_version", {}).get("version_id"),
        )
        for package in lock["standards"]
        if isinstance(package, dict)
    }
    configured_pairs = {
        (item.get("standard_id"), item.get("version_id"))
        for item in config.get("selected_standards", [])
        if isinstance(item, dict) and item.get("confirmed_by_user") is True
    }
    if locked_pairs != configured_pairs:
        errors.append(f"{LOCK_PATH}: locked versions do not match project.yaml")
    return errors
