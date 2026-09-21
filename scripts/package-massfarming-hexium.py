#!/usr/bin/env python3
"""Create a Hexium-compatible package from Xeio's official MassFarming release asset."""

from __future__ import annotations

import binascii
import json
import os
import shutil
import struct
import zipfile
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_DIR = ROOT / "dist" / "upstream"
DIST = ROOT / "dist" / "hexium"
PACKAGE_NAME = "MassFarming_Xeio"
UPSTREAM_URL = "https://github.com/Xeio/MassFarming"
AUTOMATION_URL = "https://github.com/dav1dera/dav1dera-MassFarming-x-Hexium"


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def make_icon(path: Path) -> None:
    width = height = 256
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            # Neutral field with a simple crop/grid glyph.
            r, g, b, a = 45, 58, 42, 255
            if x % 48 in (0, 1) or y % 48 in (0, 1):
                r, g, b = 78, 96, 68
            if 70 <= x <= 186 and 88 <= y <= 168:
                if (x - 70) % 29 <= 3 or (y - 88) % 27 <= 3:
                    r, g, b = 183, 157, 79
            if 119 <= x <= 137 and 50 <= y <= 205:
                r, g, b = 205, 182, 96
            row.extend((r, g, b, a))
        rows.append(bytes(row))

    raw = b"".join(rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(raw, 9))
    png += png_chunk(b"IEND", b"")
    path.write_bytes(png)


def find_massfarming_dll(extract_dir: Path) -> Path:
    matches = [
        p
        for p in extract_dir.rglob("*")
        if p.is_file() and p.name.lower() == "massfarming.dll"
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"Expected exactly one MassFarming.dll in upstream ZIP, found {len(matches)}: "
            + ", ".join(str(p) for p in matches)
        )
    return matches[0]


def main() -> None:
    upstream_tag = required_env("UPSTREAM_TAG")
    upstream_version = required_env("UPSTREAM_VERSION")
    package_version = required_env("PACKAGE_VERSION")
    release_id = required_env("UPSTREAM_RELEASE_ID")
    asset_name = required_env("UPSTREAM_ASSET_NAME")
    asset_digest = os.environ.get("UPSTREAM_ASSET_DIGEST", "").strip() or "not-provided"

    source_zip = UPSTREAM_DIR / "MassFarming.zip"
    license_file = UPSTREAM_DIR / "LICENSE"
    if not source_zip.is_file() or source_zip.stat().st_size == 0:
        raise SystemExit(f"Missing upstream release asset: {source_zip}")
    if not license_file.is_file() or license_file.stat().st_size == 0:
        raise SystemExit(f"Missing upstream MIT license: {license_file}")

    extract_dir = UPSTREAM_DIR / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True)

    with zipfile.ZipFile(source_zip) as zf:
        zf.extractall(extract_dir)

    dll = find_massfarming_dll(extract_dir)

    package_dir = DIST / f"{PACKAGE_NAME}-{package_version}"
    zip_path = DIST / f"{PACKAGE_NAME}-{package_version}-hexium.zip"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    DIST.mkdir(parents=True, exist_ok=True)
    package_dir.mkdir(parents=True)

    shutil.copy2(dll, package_dir / "MassFarming.dll")
    shutil.copy2(license_file, package_dir / "LICENSE")
    make_icon(package_dir / "icon.png")

    manifest = {
        "name": PACKAGE_NAME,
        "description": (
            "Unofficial Hexium packaging mirror of Xeio's MassFarming. "
            "Client-side mass harvesting and grid planting; upstream code is unmodified."
        ),
        "version_number": package_version,
        "website_url": UPSTREAM_URL,
        "dependencies": [],
    }
    (package_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    readme = f"""# MassFarming — unofficial Hexium mirror

This package redistributes the official release artifact of **Xeio/MassFarming** without modifying the plugin.

- Original project: {UPSTREAM_URL}
- Original author: Xeio
- Automation/mirror: {AUTOMATION_URL}
- Upstream tag: {upstream_tag}
- Upstream version: {upstream_version}
- Hexium package version: {package_version}
- GitHub release ID: {release_id}
- Official asset: {asset_name}
- Official asset digest: {asset_digest}
- License: MIT (included as `LICENSE`)

## Usage

MassFarming is a client-side Valheim mod.

Hold the configured mass-action hotkey (Left Shift by default) while using the pickup action to harvest nearby pickupable items of the same type. Holding the hotkey while planting creates a configurable planting grid.

For manual installation, put `MassFarming.dll` in `BepInEx/plugins` and restart Valheim.

This mirror is not affiliated with Xeio. Please report MassFarming issues to the upstream project when they reproduce with the official upstream release.
"""
    (package_dir / "README.md").write_text(readme, encoding="utf-8")

    changelog = f"""# Changelog

## {package_version}

- Mirrored official Xeio/MassFarming release `{upstream_tag}`.
- Source GitHub release ID: {release_id}.
- Source asset: `{asset_name}`.
- Source asset digest: `{asset_digest}`.
- No MassFarming code modifications.
- Packaged for Hexium installation.
"""
    (package_dir / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
        for file in sorted(package_dir.iterdir()):
            zf.write(file, file.name)

    required = {
        "manifest.json",
        "icon.png",
        "README.md",
        "CHANGELOG.md",
        "MassFarming.dll",
        "LICENSE",
    }
    with ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    missing = required - names
    if missing:
        raise SystemExit(f"Hexium package missing required files: {sorted(missing)}")

    meta = {
        "package_name": PACKAGE_NAME,
        "package_version": package_version,
        "zip_path": str(zip_path.relative_to(ROOT)),
        "upstream_tag": upstream_tag,
        "upstream_version": upstream_version,
        "release_id": release_id,
        "asset_digest": asset_digest,
    }
    (DIST / "package-meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Hexium package ready: {zip_path}")
    print(f"Upstream: {upstream_tag} (release {release_id})")
    print(f"Hexium version: {package_version}")
    print(f"MassFarming.dll: {dll}")


if __name__ == "__main__":
    main()
