# osmium-core

Shared, **source-only** core for the Osmium media player. It holds the custom app
code that is identical across the hardware targets, once:

- the Python application (`api_server.py`, `webui_server.py`, `sources_server.py`,
  the `hifi_*.py` modules, `vu_meter_daemon.py`, …) and its tests (`tests/`);
- the on-screen UI `native-ui-qt/` (Qt/QML source) and the Now-Playing WebAssembly
  UI `native-ui-np/` (source);
- the web admin `admin-webui/`;
- shared resources: `src/` (data + i18n), `anim-store/`, `vu-store/`, `brand/`.

This repository **builds nothing** and ships **no per-arch binary**. It is consumed
as a **git submodule** (`core/`) by the image repositories, which copy the Python as
is and native-/cross-compile the UIs for their own architecture:

- `hifi-media-player` — x86 image
- `osmium-sound-raspberry` — Raspberry Pi image

The image repositories keep the **platform layer** only (boot, RAUC/OTA, image CI,
CamillaDSP per-arch, `distro/`, `live-build-config/`, `flasher/`).

## Platform configuration

The code is platform-clean. Everything platform-specific is read at runtime from
`/etc/hifi-player/platform.conf` (`KEY=VALUE`, `HIFI_*` names), which each image
writes at build time. `hifi_platform.py` loads it into the environment at import and
exposes `platform()` / `is_raspberry()` (with a `/proc/device-tree/model` fallback,
defaulting to x86). Platform-only behaviour is a runtime branch on that marker, never
a forked file — e.g. the I2S HAT selector reports `supported: false` on x86, so its UI
hides itself.

## CI

`.github/workflows/tests.yml` runs the Python suite. The two store publishers
(`publish-anim-store.yml`, `publish-vu-store.yml`) take the target host/bucket as
inputs (defaults reproduce the historical `file.osmiumsound.it` target). Image and
OTA workflows live in the image repositories, not here.
