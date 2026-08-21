# Recovery

The broker deliberately has no automatic resume command. Repeating an ambiguous trade can duplicate or
lose track of a Pokémon.

1. Stop the broker and do not confirm another trade on either console.
2. Copy the journal and adjacent `artifacts/<transaction-id>/` records to safe storage.
3. Read `state`, `last_error`, hashes, and `locations`.
4. Inspect the actual GBA and Switch parties. Export through normal endpoint observation only if safe;
   do not edit/import saves.
5. Match observed 100-byte hashes to `A`, `B`, and `P` when possible.
6. Decide a manual compensating trade. Never infer success from animation alone.
7. Archive the old journal before starting a new transaction.

Typical interpretation:

| Last durable state | Safe conclusion |
|---|---|
| `SWITCH_STAGE1_STARTED` | Switch trade outcome unknown |
| `PLACEHOLDER_ON_SWITCH` | Broker believes `B` is captured and `P` is on Switch |
| `GBA_STAGE_STARTED` | GBA trade outcome unknown |
| `B_COMMITTED_TO_GBA` | Broker believes `B` reached GBA and holds `A` |
| `SWITCH_STAGE2_STARTED` | Return trade outcome unknown |
| `A_COMMITTED_TO_SWITCH` | `A` likely on Switch; placeholder verification not yet durable |
| `COMPLETE` | All three endpoint commits and exact placeholder recovery were recorded |

`RECOVERY_REQUIRED` may contain more current observations than the prior state, but it is never permission
to retry automatically.

