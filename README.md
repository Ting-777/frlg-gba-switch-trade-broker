# FRLG GBA ↔ Switch Trade Broker

> **Status: experimental, pre-hardware-validation. Do not use valuable Pokémon yet.**

This project coordinates three ordinary application-level trades so a physical original GBA running
Pokémon FireRed/LeafGreen can exchange a Pokémon with the Switch/Switch 2 FRLG release. The broker's
abstraction boundary is an unchanged, canonical 100-byte Gen 3 party Pokémon record plus a persistent
transaction journal.

## What this project is—and is not

It **is**:

- a transactional, application-level Pokémon trade broker;
- a standard physical GBA wired trade on one side;
- a Switch FRLG LDN/Pia trade session on the other side;
- a safety-first state machine that stops for explicit recovery when outcomes are uncertain.

It is **not**:

- a save editor or save-file transfer/import mechanism;
- a transparent GBA RFU bridge;
- an AGB-015 Wireless Adapter emulator;
- a cable-packet ↔ RFU-packet translator.

No AGB-015 reverse engineering, logic analyzer, or GBA save dump is required.

## Three-stage escrow

Let the GBA own `A`, the Switch own `B`, and the broker own a legitimate user-supplied placeholder `P`:

```text
1. Switch:  B → broker, P → Switch
2. GBA:     A → broker, B → GBA
3. Switch:  P → broker, A → Switch

Final: GBA=B, Switch=A, broker=P
```

These are independent trades coordinated by the broker, not one transparent RFU transaction. The
journal is atomically persisted after every observed irreversible boundary and records SHA-256 hashes
and believed ownership. An incomplete transaction never auto-resumes.

## Current milestone status

| Area | Status |
|---|---|
| `Pokemon100`, journal, transaction coordinator | Implemented and tested |
| Mock GBA/Switch end-to-end demo | Implemented and tested |
| Framed/versioned GB-Link USB protocol | Python codec implemented; firmware integration patch is experimental |
| Switch adapter boundary | Implemented; real LDN driver wiring remains hardware validation work |
| Physical GBA/Switch end-to-end | **Not validated** |

See [architecture](docs/architecture.md), [transaction model](docs/transaction-model.md),
[recovery](docs/recovery.md), [protocol](docs/protocol.md), and [hardware setup](docs/hardware.md).

## Install and mock demo

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test,serial]'
pytest
frlg-trade-broker --mock-demo --journal ./journal.json
```

The demo creates deterministic 100-byte `A`, `B`, and `P` fixtures and proves final ownership is
GBA=`B`, Switch=`A`, broker=`P`.

## Real-hardware shape (not yet validated)

```bash
sudo frlg-trade-broker \
  --gba /dev/ttyACM0 \
  --placeholder placeholder.pk3 \
  --phy phy0 \
  --keys prod.keys \
  --journal /var/lib/frlg-trade-broker/journal.json
```

`placeholder.pk3` must be a legitimate, user-provided, exactly 100-byte party record. The broker does
not create a hacked placeholder. Pokémon holding Mail are refused in v1 because the reviewed GB-Link
path sends an empty 220-byte mail block; mail is never silently stripped.

## Safety

- Back up nothing through this tool: it deliberately does not touch saves.
- Start with disposable test Pokémon and verify each screen before confirming.
- Keep the journal and its adjacent artifact directory; they are the recovery evidence.
- If the CLI reports `RECOVERY_REQUIRED`, stop. Do not start another trade until ownership is manually
  reconciled using hashes and on-console inspection.
- A successful mock test does not prove real hardware timing or commit semantics.

## Licensing and attribution

Broker code is AGPL-3.0-or-later. No upstream implementation has been copied into the Python broker.
The design is informed by GBLink-Firmware (GPL-3.0), the FRLG LDN bridge and its upstream (AGPL-3.0),
and pret/pokefirered (no top-level license found at the reviewed commit; reference only). Exact commits,
files, functions, and reuse limits are documented in [license research](docs/license-research.md).

Pokémon and Nintendo trademarks belong to their respective owners. This is an independent research
project and is not affiliated with or endorsed by Nintendo, The Pokémon Company, or Game Freak.

