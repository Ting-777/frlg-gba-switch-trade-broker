# Transaction model

## States

`IDLE → SWITCH_STAGE1_STARTED → SWITCH_B_CAPTURED → PLACEHOLDER_ON_SWITCH → GBA_STAGE_STARTED →
GBA_A_CAPTURED → B_COMMITTED_TO_GBA → SWITCH_STAGE2_STARTED → A_COMMITTED_TO_SWITCH → COMPLETE`

Any exception, contradictory hash, missing commit evidence, unexpected disconnect, replay, or restart in
a nonterminal state leads to `RECOVERY_REQUIRED` for operator reconciliation.

## Ownership invariant

The journal contains SHA-256 identifiers for known `A`, `B`, and `P`, plus their believed locations:
`gba`, `switch`, or `broker`. Unknown values are explicit. No transition invents a hash. Once a hash is
known it is immutable for the transaction.

The coordinator persists before initiating each external stage and immediately after an endpoint returns
commit evidence. If the process dies between a device's irreversible action and the following atomic
write, the previous `*_STARTED` state intentionally remains ambiguous and blocks restart.

## Placeholder rule

`P` must be a user-supplied legitimate 100-byte record. After the second Switch trade the received record
must equal `P` byte-for-byte. A mismatch is not normalized or accepted: the journal records both hashes
and enters `RECOVERY_REQUIRED`.

