# Upstream license and reuse research

This is an engineering note, not legal advice. Sources were cloned and inspected before implementation.

| Repository | Reviewed commit | Observed license | Reuse decision |
|---|---|---|---|
| `GB-Link/GBLink-Firmware` | `2facc86bc7292b1adad436ba8ebd5a7ccd649c12` | GPL-3.0 (`LICENSE`) | Architecture and identifiers cited. Firmware changes/patches that derive from it remain GPL-3.0-compatible and retain notices. No firmware source copied into the Python broker. |
| `andrew171717/frlg-ldn-trade-gba-bridge` | `d1299e124d1ebe702b447e5c9d70501ed57683e6` | AGPL-3.0 (`LICENSE`) | Adapter boundary is original code. A real driver may import/use the separately installed upstream; redistributed modifications must comply with AGPL-3.0 and retain attribution/source offer. |
| `tornadus/frlg-ldn-trade` | `799b674e8a2ce02bb49d5a98b5231bc17288a67b` | AGPL-3.0 (`LICENSE`) | Reference only; no copied code. |
| `pret/pokefirered` | `c75f352304d529f6ba92d4f74b9cf8b5c3810788` | **No top-level license found** | Behavioral/layout reference only. Do not copy code/assets. Tool subdirectories have their own licenses and are unrelated here. |

The broker uses AGPL-3.0-or-later so an eventual linked/imported integration with the AGPL Switch
implementation has an aligned strong-copyleft license. Merely documenting protocol facts does not import
upstream code. The experimental GB-Link integration files carry explicit GPL-3.0-or-later SPDX markers.

If upstream licenses or repository contents change, re-run this review against pinned commits before
copying or distributing modifications.

