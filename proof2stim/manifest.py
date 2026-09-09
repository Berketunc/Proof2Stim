"""Load and validate pinned Proof2Stim benchmark manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import jsonschema
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "benchmark-manifest-v1.schema.json"


class ManifestError(ValueError):
    """Raised when a benchmark manifest violates its artifact contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path, schema_path: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(document, schema)
    except (OSError, yaml.YAMLError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
        raise ManifestError(str(exc)) from exc
    if not isinstance(document, dict):
        raise ManifestError("manifest root must be an object")
    return document


def verify_sources(document: dict[str, Any], project_root: Path = PROJECT_ROOT) -> list[str]:
    errors: list[str] = []
    for source in document["rtl"]["sources"]:
        path = project_root / source["path"]
        if not path.is_file():
            errors.append(f"missing source: {source['path']}")
            continue
        actual = sha256_file(path)
        if actual != source["sha256"]:
            errors.append(
                f"hash mismatch for {source['path']}: expected {source['sha256']}, got {actual}"
            )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--skip-source-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        document = load_manifest(args.manifest, args.schema)
    except ManifestError as exc:
        print(f"INVALID: {exc}")
        return 1
    errors = [] if args.skip_source_check else verify_sources(document)
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print(f"VALID: {document['benchmark']['id']} ({args.manifest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
