# FRLG GBA ↔ Switch Trade Broker

> **Status: hardware-candidate, not yet physically validated. Begin only with disposable Pokémon.**

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
| Framed/versioned GB-Link USB protocol | Firmware/Python codecs, SHA-256 and replay-safe command ACKs implemented |
| Switch adapter boundary | Persistent two-trade driver with an explicit inter-round offer gate implemented |
| Physical GBA/Switch end-to-end | **Not validated** |

See [architecture](docs/architecture.md), [transaction model](docs/transaction-model.md),
[recovery](docs/recovery.md), [protocol](docs/protocol.md), and [hardware setup](docs/hardware.md).

## Install and mock demo

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test,hardware]'
pytest
frlg-trade-broker --mock-demo --journal ./journal.json
```

The demo creates deterministic 100-byte `A`, `B`, and `P` fixtures and proves final ownership is
GBA=`B`, Switch=`A`, broker=`P`.

## Prepare a real-hardware candidate

Pin the two reviewed upstreams, install the GB-Link integration, then build/flash it with the upstream
Zephyr workflow:

```bash
git clone https://github.com/GB-Link/GBLink-Firmware.git
git -C GBLink-Firmware checkout 2facc86bc7292b1adad436ba8ebd5a7ccd649c12
./scripts/install_gb_link_integration.sh ./GBLink-Firmware

git clone https://github.com/andrew171717/frlg-ldn-trade-gba-bridge.git
git -C frlg-ldn-trade-gba-bridge checkout d1299e124d1ebe702b447e5c9d70501ed57683e6
```

The placeholder must be an encrypted/raw, checksum-valid 100-byte party record (`.ek3` wire form).
Run the non-connecting preflight first:

```bash
sudo .venv/bin/frlg-trade-broker --preflight \
  --gba /dev/serial/by-id/YOUR_GB_LINK \
  --placeholder placeholder.ek3 \
  --switch-checkout ./frlg-ldn-trade-gba-bridge \
  --phy phy0 \
  --keys prod.keys \
  --journal /var/lib/frlg-trade-broker/journal.json
```

Only after preflight succeeds, remove `--preflight` to start the real session:

```bash
sudo .venv/bin/frlg-trade-broker \
  --gba /dev/serial/by-id/YOUR_GB_LINK \
  --placeholder placeholder.ek3 \
  --switch-checkout ./frlg-ldn-trade-gba-bridge \
  --phy phy0 \
  --keys prod.keys \
  --journal /var/lib/frlg-trade-broker/journal.json
```

`placeholder.ek3` must be a legitimate, user-provided, exactly 100-byte party record. The broker does
not create a hacked placeholder. Pokémon holding Mail are refused in v1 because the reviewed GB-Link
path sends an empty 220-byte mail block; mail is never silently stripped.

## Safety

- Back up nothing through this tool: it deliberately does not touch saves.
- Start with disposable test Pokémon and verify each screen before confirming.
- Keep the journal and its adjacent artifact directory; they are the recovery evidence.
- If the CLI reports `RECOVERY_REQUIRED`, stop. Do not start another trade until ownership is manually
  reconciled using hashes and on-console inspection.
- Keep the Switch in the same Direct Corner session after trade 1; the driver holds its party response
  while the physical GBA trade runs, then supplies A for trade 2.
- A successful mock/host test does not prove real hardware timing or commit semantics.

## Licensing and attribution

Broker code is AGPL-3.0-or-later. No upstream implementation has been copied into the Python broker.
The design is informed by GBLink-Firmware (GPL-3.0), the FRLG LDN bridge and its upstream (AGPL-3.0),
and pret/pokefirered (no top-level license found at the reviewed commit; reference only). Exact commits,
files, functions, and reuse limits are documented in [license research](docs/license-research.md).

Pokémon and Nintendo trademarks belong to their respective owners. This is an independent research
project and is not affiliated with or endorsed by Nintendo, The Pokémon Company, or Game Freak.
