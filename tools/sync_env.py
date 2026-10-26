#!/usr/bin/env python3
"""Validate configured .env.example files and synchronize matching .env files."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


EXCLUDED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "__pycache__"}
CREDENTIAL_KEY = re.compile(r"(?:API_KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)
CONNECTION_KEYS = {"DATABASE_URL", "QDRANT_URL"}
PLACEHOLDER = re.compile(
    r"(?:replace(?:[-_ ]?with)?|change[-_ ]?me|placeholder|"
    r"your[-_ ]|example|todo|user:password|api[-_ ]?key|x{3,}|<[^>]+>)",
    re.IGNORECASE,
)
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


class EnvSyncError(RuntimeError):
    pass


def display_path(path: Path, repository_root: Path) -> str:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return str(path)


def discover(root: Path, name: str) -> list[Path]:
    results: list[Path] = []
    for path in root.rglob(name):
        if path.is_file() and not any(part in EXCLUDED_DIRECTORIES for part in path.parts):
            results.append(path)
    return sorted(results)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_env(
    path: Path, repository_root: Path, *, allow_empty: bool = False
) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise EnvSyncError(
            f"Cannot read {display_path(path, repository_root)}: {exc}"
        ) from exc

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT.match(line)
        if not match:
            raise EnvSyncError(
                f"Invalid environment entry in {display_path(path, repository_root)} "
                f"at line {line_number}."
            )
        key, raw_value = match.groups()
        if key in values:
            raise EnvSyncError(
                f"Duplicate key {key} in {display_path(path, repository_root)}."
            )
        values[key] = unquote(raw_value)

    if not values and not allow_empty:
        raise EnvSyncError(f"{display_path(path, repository_root)} is empty.")
    return values


def requires_private_value(key: str) -> bool:
    return bool(CREDENTIAL_KEY.search(key)) or key.upper() in CONNECTION_KEYS


def placeholder_reason(key: str, value: str) -> str | None:
    if not requires_private_value(key):
        return None
    if not value.strip():
        return "is empty"
    if PLACEHOLDER.search(value):
        return "still contains an example placeholder"
    if CREDENTIAL_KEY.search(key) and len(value.strip()) < 8:
        return "is too short to be a configured credential"
    return None


def incomplete_reasons(values: dict[str, str], expected: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    missing_keys = [key for key in expected if key not in values]
    if missing_keys:
        reasons.append(f"missing keys: {', '.join(missing_keys)}")
    for key in expected:
        if key not in values or not requires_private_value(key):
            continue
        reason = placeholder_reason(key, values[key])
        if reason:
            reasons.append(f"{key} {reason}")
    return reasons


def copy_atomically(source: Path, destination: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".env.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def import_env_files(
    root: Path, source_root: Path, repository_root: Path, check_only: bool
) -> None:
    """Copy each .env from source_root, mirroring the .env.example layout under root."""
    examples = discover(root, ".env.example")
    if not examples:
        raise EnvSyncError(f"No .env.example files were found under {root}.")

    plan: list[tuple[Path, Path]] = []
    problems: list[str] = []
    for example in examples:
        relative = example.parent.relative_to(root) / ".env"
        source = source_root / relative
        destination = example.with_name(".env")
        if not source.is_file():
            problems.append(f"{source} is missing")
            continue
        reasons = incomplete_reasons(
            parse_env(source, repository_root, allow_empty=True),
            parse_env(example, repository_root),
        )
        if reasons:
            problems.append(f"{source}: {'; '.join(reasons)}")
            continue
        plan.append((source, destination))

    if problems:
        raise EnvSyncError(
            f"Cannot import environment files from {source_root}: {'; '.join(problems)}"
        )

    for source, destination in plan:
        relative_destination = display_path(destination, repository_root)
        if destination.exists() and destination.read_bytes() == source.read_bytes():
            print(f"ENV IMPORT: {relative_destination} already matches {source}")
            continue
        if check_only:
            print(f"ENV CHECK: normal startup will import {source} -> {relative_destination}")
            continue

        if destination.exists():
            backup = destination.with_name(".env.pre-sync.bak")
            try:
                shutil.copy2(destination, backup)
            except OSError as exc:
                raise EnvSyncError(
                    f"Cannot back up {relative_destination} before import: {exc}"
                ) from exc
            backup_note = f"; previous file saved as {display_path(backup, repository_root)}"
        else:
            backup_note = ""

        try:
            copy_atomically(source, destination)
        except OSError as exc:
            raise EnvSyncError(
                f"Cannot copy {source} to {relative_destination}: {exc}"
            ) from exc
        print(f"ENV IMPORTED: {source} -> {relative_destination}{backup_note}")


def validate_and_sync(root: Path, repository_root: Path, check_only: bool) -> None:
    examples = discover(root, ".env.example")
    env_files = discover(root, ".env")
    if not examples:
        raise EnvSyncError(f"No .env.example files were found under {root}.")

    example_by_directory = {path.parent.resolve(): path for path in examples}
    orphaned_envs = [path for path in env_files if path.parent.resolve() not in example_by_directory]
    if orphaned_envs:
        names = ", ".join(display_path(path, repository_root) for path in orphaned_envs)
        raise EnvSyncError(f"Environment files without matching .env.example files: {names}")

    parsed_examples: dict[Path, dict[str, str]] = {}
    incomplete_pairs: list[tuple[Path, Path, list[str]]] = []
    for example in examples:
        values = parse_env(example, repository_root)
        parsed_examples[example] = values
        destination = example.with_name(".env")
        if not destination.exists():
            incomplete_pairs.append((example, destination, ["file is missing"]))
            continue
        destination_values = parse_env(destination, repository_root, allow_empty=True)
        reasons = incomplete_reasons(destination_values, values)
        if reasons:
            incomplete_pairs.append((example, destination, reasons))
        else:
            print(
                f"ENV READY: {display_path(destination, repository_root)} is complete; "
                "no synchronization needed"
            )

    if not incomplete_pairs:
        print(
            f"ENV VALID: all {len(examples)} .env file(s) are complete; launch can continue."
        )
        return

    credential_count = 0
    problems: list[str] = []
    for example, values in parsed_examples.items():
        for key, value in values.items():
            if not requires_private_value(key):
                continue
            credential_count += 1
            reason = placeholder_reason(key, value)
            if reason:
                problems.append(
                    f"{display_path(example, repository_root)}: {key} {reason}"
                )

    if credential_count == 0:
        raise EnvSyncError(
            "At least one .env file is incomplete, but no API key, token, secret, "
            "password, or connection field was found in the examples."
        )
    if problems:
        incomplete_names = ", ".join(
            display_path(destination, repository_root)
            for _, destination, _ in incomplete_pairs
        )
        raise EnvSyncError(
            f"Incomplete environment file(s): {incomplete_names}. Synchronization is "
            f"blocked because required example values are not configured: {'; '.join(problems)}"
        )

    for example, destination, reasons in incomplete_pairs:
        relative_example = display_path(example, repository_root)
        relative_destination = display_path(destination, repository_root)
        if check_only:
            action = "replace" if destination.exists() else "create"
            print(
                f"ENV CHECK: {relative_destination} is incomplete "
                f"({'; '.join(reasons)}); normal startup will {action} it from "
                f"{relative_example}"
            )
            continue

        if destination.exists():
            backup = destination.with_name(".env.pre-sync.bak")
            try:
                shutil.copy2(destination, backup)
            except OSError as exc:
                raise EnvSyncError(
                    f"Cannot back up {relative_destination} before synchronization: {exc}"
                ) from exc
            backup_note = f"; previous file saved as {display_path(backup, repository_root)}"
        else:
            backup_note = ""

        try:
            copy_atomically(example, destination)
        except OSError as exc:
            raise EnvSyncError(
                f"Cannot copy {relative_example} to {relative_destination}: {exc}"
            ) from exc
        print(f"ENV SYNCED: {relative_example} -> {relative_destination}{backup_note}")

    print(
        f"ENV VALID: checked {len(examples)} pair(s) and {credential_count} required "
        "credential/connection field(s)."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="Directory to scan")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate and report differences without copying files",
    )
    parser.add_argument(
        "--import-from",
        type=Path,
        help="Folder holding .env files laid out like the repository; copied in first",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    repository_root = Path(__file__).resolve().parent.parent

    if not root.is_dir():
        print(f"ERROR: Environment root does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    try:
        if args.import_from is not None:
            source_root = args.import_from.expanduser().resolve()
            if not source_root.is_dir():
                raise EnvSyncError(
                    f"Environment folder does not exist or is not a directory: {source_root}"
                )
            if source_root != root:
                import_env_files(root, source_root, repository_root, args.check)
                if args.check:
                    # Imported files were already validated against their examples.
                    print(f"ENV VALID: all .env files in {source_root} are complete.")
                    return 0
        validate_and_sync(root, repository_root, args.check)
    except EnvSyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
