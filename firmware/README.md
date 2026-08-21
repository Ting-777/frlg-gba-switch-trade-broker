# Firmware work

The files under `gb-link/` are an experimental GPL-3.0-or-later integration layer for
`GB-Link/GBLink-Firmware` commit `2facc86bc7292b1adad436ba8ebd5a7ccd649c12`.

They are intentionally source-only: no firmware image is claimed to be hardware validated. Apply the
integration points in `patches/0001-trade-broker-integration.patch`, build with the upstream Zephyr
toolchain, then execute the staged checks in `docs/hardware.md`.

The integration reuses the existing CDC/WebUSB transport's 64-byte chunks. `FGBR` frames are the inner
application protocol and may span multiple transport chunks. The dedicated mode variant prevents inner
frames from being mistaken for the legacy 100-byte `.pk3` upload stream.

