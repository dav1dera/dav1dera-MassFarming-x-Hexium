#!/usr/bin/env python3
"""Publish the generated MassFarming mirror package to Hexium."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "hexium"
META = DIST / "package-meta.json"

HEXIUM_BASE = os.environ.get("HEXIUM_BASE_URL", "https://hexium.gg").rstrip("/")
HEXIUM_TEAM = os.environ.get("HEXIUM_TEAM", "Sgorbi")
HEXIUM_PACKAGE = os.environ.get("HEXIUM_PACKAGE", "MassFarming_Xeio")
HEXIUM_COMMUNITY = os.environ.get("HEXIUM_COMMUNITY", "valheim")
HEXIUM_CATEGORIES = [
    item.strip()
    for item in os.environ.get("HEXIUM_CATEGORIES", "Valheim 1.0").split(",")
    if item.strip()
]
USER_AGENT = "dav1dera-massfarming-hexium-publisher"


def load_meta() -> dict:
    if not META.is_file():
        raise SystemExit(f"Missing package metadata: {META}")
    data = json.loads(META.read_text(encoding="utf-8"))
    if data.get("package_name") != HEXIUM_PACKAGE:
        raise SystemExit(
            f"Package metadata name {data.get('package_name')!r} does not match "
            f"HEXIUM_PACKAGE {HEXIUM_PACKAGE!r}"
        )
    return data


def parse_json_or_none(raw: str) -> object | None:
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def http_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: object | None = None,
    expected: tuple[int, ...] = (200,),
) -> tuple[int, object | None, str]:
    body = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = parse_json_or_none(raw)
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
        if status not in expected:
            raise RuntimeError(f"{method} {url} -> HTTP {status}: {raw[:2000]}") from exc
        data = parse_json_or_none(raw)

    if status not in expected:
        raise RuntimeError(f"{method} {url} -> unexpected HTTP {status}")
    return status, data, raw


def version_already_exists(version: str) -> bool:
    url = f"{HEXIUM_BASE}/api/experimental/package/{HEXIUM_TEAM}/{HEXIUM_PACKAGE}/{version}/"
    status, _data, _raw = http_json(url, expected=(200, 404))
    return status == 200


def initiate_upload(token: str, zip_path: Path) -> dict:
    url = f"{HEXIUM_BASE}/api/experimental/usermedia/initiate-upload/"
    _status, data, _raw = http_json(
        url,
        method="POST",
        token=token,
        payload={"filename": zip_path.name, "file_size_bytes": zip_path.stat().st_size},
        expected=(200, 201),
    )
    if not isinstance(data, dict):
        raise RuntimeError("Hexium initiate-upload returned invalid JSON")
    return data


def upload_parts(zip_path: Path, upload_urls: list[dict]) -> list[dict]:
    blob = zip_path.read_bytes()
    completed: list[dict] = []

    for part in sorted(upload_urls, key=lambda item: int(item["part_number"])):
        part_number = int(part["part_number"])
        offset = int(part["offset"])
        length = int(part["length"])
        chunk = blob[offset : offset + length]
        if len(chunk) != length:
            raise RuntimeError(
                f"Hexium upload part {part_number} requested {length} bytes at {offset}, "
                f"but only {len(chunk)} bytes are available"
            )

        request = urllib.request.Request(
            str(part["url"]),
            data=chunk,
            headers={"User-Agent": USER_AGENT},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(
                        f"Upload part {part_number} failed with HTTP {response.status}"
                    )
                etag = response.headers.get("ETag")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Upload part {part_number} failed with HTTP {exc.code}: {raw[:1000]}"
            ) from exc

        if not etag:
            raise RuntimeError(f"Upload part {part_number} response did not contain ETag")

        completed.append({"ETag": etag, "PartNumber": part_number})
        print(f"Uploaded Hexium part {part_number}/{len(upload_urls)}")

    return completed


def finish_upload(token: str, uuid: str, parts: list[dict]) -> None:
    url = f"{HEXIUM_BASE}/api/experimental/usermedia/{uuid}/finish-upload/"
    http_json(
        url,
        method="POST",
        token=token,
        payload={"parts": parts},
        expected=(200, 201, 204),
    )


def abort_upload(token: str, uuid: str) -> None:
    url = f"{HEXIUM_BASE}/api/experimental/usermedia/{uuid}/abort-upload/"
    try:
        http_json(url, method="POST", token=token, expected=(200, 201, 204, 404))
    except Exception as exc:
        print(f"Warning: could not abort Hexium upload {uuid}: {exc}", file=sys.stderr)


def submit_package(token: str, uuid: str) -> None:
    url = f"{HEXIUM_BASE}/api/experimental/submission/submit/"
    metadata = {
        "author_name": HEXIUM_TEAM,
        "categories": [],
        "communities": [HEXIUM_COMMUNITY],
        "has_nsfw_content": False,
        "upload_uuid": uuid,
        "community_categories": {HEXIUM_COMMUNITY: HEXIUM_CATEGORIES},
    }
    http_json(
        url,
        method="POST",
        token=token,
        payload=metadata,
        expected=(200, 201, 202),
    )


def main() -> None:
    token = os.environ.get("HEXIUM_TOKEN", "").strip()
    if not token:
        raise SystemExit("HEXIUM_TOKEN is not set")
    if not token.startswith("hexium_"):
        print("Warning: HEXIUM_TOKEN does not use the expected hexium_ prefix", file=sys.stderr)

    meta = load_meta()
    version = str(meta["package_version"])
    zip_path = ROOT / str(meta["zip_path"])

    if not zip_path.is_file() or zip_path.stat().st_size == 0:
        raise SystemExit(f"Hexium package ZIP not found: {zip_path}")

    if version_already_exists(version):
        print(
            f"Hexium already has {HEXIUM_TEAM}/{HEXIUM_PACKAGE} {version}; "
            "skipping publish"
        )
        return

    response = initiate_upload(token, zip_path)
    user_media = response.get("user_media") or {}
    uuid = user_media.get("uuid")
    upload_urls = response.get("upload_urls")

    if not uuid or not isinstance(upload_urls, list) or not upload_urls:
        raise RuntimeError("Hexium initiate-upload response is missing uuid/upload_urls")

    print(f"Hexium upload created: {uuid} ({len(upload_urls)} part(s))")

    try:
        parts = upload_parts(zip_path, upload_urls)
        finish_upload(token, str(uuid), parts)
        submit_package(token, str(uuid))
    except Exception:
        abort_upload(token, str(uuid))
        raise

    print(
        f"Published {HEXIUM_TEAM}/{HEXIUM_PACKAGE} {version} to {HEXIUM_COMMUNITY}; "
        "Hexium may keep the version pending until its malware scan completes"
    )


if __name__ == "__main__":
    main()
