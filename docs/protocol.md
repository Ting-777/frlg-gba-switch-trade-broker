# GB-Link broker USB protocol v1

Binary frames are transported over the existing USB byte stream. Newline-delimited binary is forbidden.

On CDC-ACM, GBLink-Firmware already wraps logical transport chunks as `GB | channel | u16 length |
payload` with a 64-byte payload limit. `FGBR` is an inner stream: the Python transport enters Gen 3
trade-emulator mode variant 1, chunks each `FGBR` frame into existing data-channel packets, and
reassembles those packets before CRC parsing. This extends the existing transport instead of replacing it.

## Frame

All integers are little-endian.

| Field | Bytes | Meaning |
|---|---:|---|
| magic | 4 | ASCII `FGBR` |
| version | 1 | `1` |
| message type | 1 | enum below |
| flags | 2 | v1 requires zero |
| payload length | 4 | `0..4096` |
| transaction id | 16 | UUID bytes |
| sequence | 4 | strictly increasing per direction/transaction |
| payload | N | message-specific |
| CRC32 | 4 | IEEE CRC32 of header and payload |

The receiver scans for magic, bounds payload length before allocation, validates CRC/version/flags, and
rejects duplicate or decreasing sequence numbers. Commands that may be retried carry the same sequence;
firmware must return the cached acknowledgement rather than apply them twice.

## Messages

| Type | Direction | Payload |
|---|---|---|
| `HELLO` (1) | either | implementation/version UTF-8 |
| `GET_CAPABILITIES` (2) | PC→device | empty |
| `CAPABILITIES` (3) | device→PC | `u32` capability bitmask |
| `TRADE_SESSION_STARTED` (16) | device→PC | empty |
| `PARTNER_PARTY` (17) | device→PC | exactly 600 bytes |
| `PARTNER_SELECTED_SLOT` (18) | device→PC | one byte, `0..5` |
| `PARTNER_SELECTED_MON` (19) | device→PC | exactly 100 bytes |
| `SET_OFFER_MON` (32) | PC→device | slot byte followed by 100 bytes |
| `OFFER_READY` (33) | device→PC | slot byte plus SHA-256 (32 bytes) |
| `TRADE_NEGOTIATION` (34) | device→PC | link command and arguments |
| `TRADE_COMMITTED` (35) | device→PC | offered/received SHA-256 hashes |
| `TRADE_ABORTED` (36) | device→PC | reason code |
| `TRADE_LINK_CLOSED` (37) | device→PC | close status byte |
| `ABORT_IF_SAFE` (38) | PC→device | empty |
| `ERROR` (127) | either | `u16` code plus bounded UTF-8 detail |

Capability bits v1: partner-party export, selected-mon export, offer injection, pre-commit abort,
commit event, close event, mail-preservation. The broker requires every capability except mail
preservation; absence of that bit activates the v1 Mail refusal policy.

## Firmware mapping

- Reset partner accumulation and emit `TRADE_SESSION_STARTED` when the trade connection starts.
- After the third 200-byte party block, emit one `PARTNER_PARTY` event.
- At `LINKCMD_READY_TO_TRADE`, validate `command[2] < 6`, emit selected slot and the corresponding
  immutable `g_partnerParty` slice, then proceed with existing link negotiation.
- `SET_OFFER_MON` replaces only the configured emulator party slot before selection becomes committed.
- Emit `TRADE_COMMITTED` only at the reviewed irreversible link state; this location is intentionally
  marked hardware-validation-required in the experimental patch.
- Emit `TRADE_LINK_CLOSED` after the normal wired close handshake, not merely on USB disconnect.
