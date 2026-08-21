# Hardware setup and validation plan

## Required

- Original GBA with an authentic FireRed/LeafGreen cartridge and ordinary GBA link cable.
- GB-Link-compatible RP2040 adapter flashed with the experimental broker firmware integration.
- Linux PC/Raspberry Pi with USB access to the adapter and a supported Wi-Fi PHY for the existing LDN
  bridge.
- Switch/Switch 2 FRLG release, legal keys required by the upstream LDN tool, and a legitimate encrypted
  100-byte placeholder `.ek3` (raw wire form).

## Install and preflight

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test,hardware]'
pytest
make -C firmware/tests/host

git -C /path/to/GBLink-Firmware checkout 2facc86bc7292b1adad436ba8ebd5a7ccd649c12
./scripts/install_gb_link_integration.sh /path/to/GBLink-Firmware

sudo .venv/bin/frlg-trade-broker --preflight \
  --gba /dev/serial/by-id/YOUR_GB_LINK \
  --placeholder ./placeholder.ek3 \
  --switch-checkout /path/to/frlg-ldn-trade-gba-bridge \
  --keys /path/to/prod.keys --phy phy0 \
  --journal /var/lib/frlg-trade-broker/journal.json
```

Preflight checks the placeholder checksum/Mail policy, device permissions, non-empty keys file, pinned
Switch bridge commit, Python hardware dependencies, Wi-Fi PHY, and journal directory. It never opens a
serial or LDN connection.

## Staged validation

1. **USB codec only:** run protocol tests and corrupt frames to verify CRC, length, version, transaction
   id, first-HELLO adoption, stale rejection, and duplicate-command ACK replay.
2. **GBA only:** load disposable `B`; verify the firmware reports the full 600-byte party and selected
   slot; confirm exported `A` is exactly that 100-byte slice; measure/confirm the committed event and
   successful link-close event.
3. **Switch only with mocked GBA:** perform `B ↔ P`, pause in the same room, replace the future offer with
   mocked `A`, perform `P ↔ A`, and verify exact `P` recovery.
4. **End to end:** use disposable Pokémon; induce cable, USB, process, and Wi-Fi failures at every journal
   boundary; reconcile parties and journal before progressing.

## udev example

Prefer a stable `/dev/serial/by-id/...` path. If using `/dev/ttyACM0`, grant only the required group
access rather than running the entire broker as root. Wi-Fi/LDN setup may still require upstream-specific
capabilities; follow that project's instructions.

## Known limitations

- No physical hardware was available in the implementation environment.
- Mail is refused until the full six-entry 220-byte mail block can be preserved and tested.
- The exact Switch 2026 implementation and platform behavior may change; pin and revalidate the upstream
  bridge commit.
- The included firmware integration compiles as host-side C++ and applies cleanly to the pinned source;
  a full Zephyr image still must be built in the upstream SDK and is not signed or prebuilt here.
