# MassFarming x Hexium

Automated, unofficial Hexium packaging mirror for [Xeio/MassFarming](https://github.com/Xeio/MassFarming).

This repository does **not** modify MassFarming. GitHub Actions periodically checks the latest official Xeio release, downloads the official `MassFarming.zip` release asset, verifies its GitHub-provided SHA-256 when available, packages it for Hexium, and publishes a new Hexium version when needed.

## Upstream

- Project: https://github.com/Xeio/MassFarming
- Author: Xeio
- License: MIT
- Mod type: client-side
- Default mass-action hotkey: Left Shift

## Hexium package

- Team: `Sgorbi`
- Package: `MassFarming_Xeio`
- Dependency string: `hex:Sgorbi-MassFarming_Xeio-*`

MassFarming is client-side, so this package is intended for modded Valheim clients. It does not need to be installed on a dedicated server merely for its normal mass-harvest / mass-plant functionality.

## Automation

The workflow runs every six hours and can also be started manually from GitHub Actions.

Required repository secret:

- `HEXIUM_TOKEN`

The release ZIP, DLL, upstream tag, release ID and digest are recorded in the generated package metadata/README for traceability.
