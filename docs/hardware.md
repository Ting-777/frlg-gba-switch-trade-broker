# Hardware setup and validation plan

## Required

- Original GBA with an authentic FireRed/LeafGreen cartridge and ordinary GBA link cable.
- GB-Link-compatible RP2040 adapter flashed with the experimental broker firmware integration.
- Linux PC/Raspberry Pi with USB access to the adapter and a supported Wi-Fi PHY for the existing LDN
  bridge.
- Switch/Switch 2 FRLG release, legal keys required by the upstream LDN tool, and a legitimate 100-byte
  placeholder `.pk3`.

## Staged validation

1. **USB codec only:** run protocol tests and corrupt frames to verify CRC, length, version, transaction
   id, and replay rejection.
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
- The included firmware integration is a reviewable starting point, not a signed/prebuilt firmware image.

