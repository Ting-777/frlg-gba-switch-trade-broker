# Architecture

## Boundary

```text
Physical GBA FRLG --wired link--> GB-Link/RP2040 --framed USB--> Python broker
                                                               |
                                                        100-byte records
                                                               |
Switch/Switch 2 FRLG <--LDN/Pia-- existing FRLG LDN implementation <--adapter
```

The broker never translates GBA cable words to Switch RFU/LDN packets. Each real endpoint owns its
timing-sensitive protocol. The broker coordinates only `Pokemon100` values, commit evidence, and
persistent ownership state.

## Components

- `broker.pokemon.Pokemon100`: immutable exact-length value with SHA-256 and optional Gen 3 checksum
  sanity inspection. No silent decrypt/re-encrypt or normalization.
- `broker.journal.JournalStore`: JSON journal written with file `fsync`, atomic rename, and directory
  `fsync`. Records monotonic sequence, hashes, locations, and errors.
- `broker.transaction.TradeCoordinator`: deterministic three-stage state machine. Every uncertain
  result becomes `RECOVERY_REQUIRED`; it never guesses or auto-resumes.
- `broker.gba.protocol`: binary stream framing, CRC32, version, UUID transaction id, message sequence,
  replay rejection, and bounded payloads.
- `broker.gba.gb_link`: endpoint adapter around the framed firmware event API.
- `broker.switch.upstream_driver`: persistent real LDN driver. After trade 1 it withholds the next
  200-byte party response until A is staged, while the upstream live loop keeps Pia/link state alive.
- mock endpoints model ownership and inject failures without hardware.

## Verified source observations

Reviewed 2026-08-20 at the commits listed in `license-research.md`.

### GBLink-Firmware

- `src/payloads/pokemon.cpp`: `g_party` and `g_partnerParty` are each 600 bytes; `slot()` slices
  `index * 100, 100`; `partnerPartyConstruct()` accumulates partner data with 200-byte thresholds.
- `party::tradePkmnAtIndex(index)` copies the selected 100-byte partner record into the corresponding
  local slot.
- `party::usbReceivePkmFile()` accumulates exactly `0x64` bytes and loads the first filler slot.
- `src/sections/tradeConnection.cpp`: `LINKCMD_READY_TO_TRADE` reads `command[2]`, echoes it through
  `LINKCMD_SET_MONS_TO_TRADE`, and calls `tradePkmnAtIndex(command[2])`.
- The reviewed path uses `getEmptyMailPayload()` for a 220-byte mail exchange. Therefore v1 refuses
  mail-bearing Pokémon until preservation is proved.

### Switch LDN bridge

- `frlgtrade.py` describes and configures 1..6 sequential trades.
- `frlgsim/trade.py:TradeEngine.__init__` documents that the wireless link stays up and that each
  trade re-runs party exchange.
- `TradeEngine._commit()` captures the selected host party record, swaps it into the offered slot,
  increments the round, and calls `_arm_next_round()` when more trades remain.
- `_reset_round_state()` rebuilds the 600-byte staged party from current `self.party`.
- `frlgsim/mon.py` defines `PARTY_MON_SIZE = 100`, `PARTY_BLOCK_SIZE = 200`, and explicit `.pk3` ↔
  encrypted wire conversion. This broker intentionally carries bytes unchanged; format conversion
  belongs at the endpoint adapter.

### pokefirered reference

- `include/pokemon.h` defines `BoxPokemon` plus the party tail in `struct Pokemon`; layout totals 100
  bytes on the target ABI.
- `src/trade.c:BufferTradeParties()` is reached before the menu is populated; the existing LDN bridge
  cites this path for repeated party exchange.
- `src/trade.c` and `src/trade_scene.c` are used only as behavioral references because no top-level
  license was present at the reviewed commit.

## Assumptions requiring hardware validation

- Which exact GB-Link link state is the earliest reliable irreversible commit signal.
- USB event delivery latency and ordering under RP2040 load; sequence/replay handling is implemented
  but not measured.
- Whether the current Switch release returns byte-identical 100-byte placeholder data. Any observed
  normalization must be documented and explicitly opted into; the default is byte-for-byte.
- Whether a live `TradeEngine` can safely pause between sequential rounds while the physical GBA trade
  occurs. The source supports repeated rounds, but the long inter-round broker pause is unmeasured.
- Whether dynamically replacing a future offered slot between rounds is accepted by the live host.
- Mail semantics. v1 refuses Mail rather than risk silent loss.

The reviewed Switch engine immediately arms the next round from `_commit()`. The broker driver now adds
an explicit inter-round gate before the host's next 200-byte party exchange; restarting the legacy CLI
would break the same-session requirement and is deliberately not used.

## Trust model

An endpoint's `commit_confirmed` is evidence supplied by that endpoint, not proof of the other console's
save completion. A disconnect near commit is ambiguous and always stops for recovery. Journal ownership
means “broker's best evidenced belief,” never an instruction to repeat a trade automatically.
