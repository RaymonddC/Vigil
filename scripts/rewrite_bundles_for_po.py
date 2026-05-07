"""Rewrite Vigil seed bundles into the Synthea-style transaction format that
Prompt Opinion's data-import accepts.

Source: PUT-by-logical-ID with URN-pseudo fullUrls (`urn:uuid:Patient-PT-007`).
Target: POST + real `urn:uuid:<uuid4>` fullUrls + every reference rewritten
        to point at the new urn:uuid. The destination FHIR server then assigns
        its own IDs at ingest, so we don't fight PO over ID strategy.

Usage:
    uv run python scripts/rewrite_bundles_for_po.py SRC_DIR DST_DIR
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any


def _walk_refs(node: Any, ref_map: dict[str, str]) -> None:
    """Recursively rewrite any string fields named `reference` against ref_map."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "reference" and isinstance(v, str) and v in ref_map:
                node[k] = ref_map[v]
            else:
                _walk_refs(v, ref_map)
    elif isinstance(node, list):
        for item in node:
            _walk_refs(item, ref_map)


def rewrite_bundle(bundle: dict) -> dict:
    entries = bundle.get("entry", [])

    # Pass 1: assign real UUIDs and build the rewrite map.
    # Map both the old fullUrl AND the old logical-ID-style reference
    # (e.g. `Patient/PT-007`) onto the new urn:uuid.
    ref_map: dict[str, str] = {}
    for e in entries:
        resource = e.get("resource", {})
        rt = resource.get("resourceType")
        old_id = resource.get("id")
        old_full = e.get("fullUrl")

        new_full = f"urn:uuid:{uuid.uuid4()}"
        e["fullUrl"] = new_full

        if old_full:
            ref_map[old_full] = new_full
        if rt and old_id:
            ref_map[f"{rt}/{old_id}"] = new_full

        # Drop the logical id — server will assign one on POST.
        resource.pop("id", None)

        # Rewrite request: POST <ResourceType>, no conditional URL.
        e["request"] = {"method": "POST", "url": rt}

    # Pass 2: rewrite every `.reference` string we recognise.
    for e in entries:
        _walk_refs(e.get("resource", {}), ref_map)

    return bundle


def main(src_dir: str, dst_dir: str) -> None:
    src = Path(src_dir)
    dst = Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)

    count = 0
    for path in sorted(src.glob("PT-*.json")):
        with path.open(encoding="utf-8") as f:
            bundle = json.load(f)
        rewrite_bundle(bundle)
        out = dst / path.name
        with out.open("w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)
        print(f"  rewrote {path.name} -> {out}")
        count += 1
    print(f"\nDone. {count} bundles rewritten for PO import.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
