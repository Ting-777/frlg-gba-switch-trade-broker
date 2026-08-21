"""Strict, immutable handling of canonical 100-byte Gen 3 party records."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Final

from .errors import InvalidPokemon, MailNotSupported

PARTY_RECORD_SIZE: Final = 100
SECURE_START: Final = 32
SECURE_END: Final = 80
MAIL_ITEM_MIN: Final = 121
MAIL_ITEM_MAX: Final = 132

# PID % 24 substructure order used by Gen 3. We decrypt only for sanity inspection;
# `raw` is never modified or normalized.
SUBSTRUCT_ORDERS: Final[tuple[str, ...]] = (
    "GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
    "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
    "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
    "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG",
)


@dataclass(frozen=True, slots=True)
class Pokemon100:
    """An unchanged, exact-length party Pokémon record.

    Construction copies bytes to avoid retaining a mutable buffer. Equality is
    byte-for-byte by design.
    """

    raw: bytes

    def __post_init__(self) -> None:
        copied = bytes(self.raw)
        if len(copied) != PARTY_RECORD_SIZE:
            raise InvalidPokemon(
                f"party Pokémon must be exactly {PARTY_RECORD_SIZE} bytes; got {len(copied)}"
            )
        object.__setattr__(self, "raw", copied)

    @classmethod
    def load(cls, path: str | Path) -> "Pokemon100":
        return cls(Path(path).read_bytes())

    def save(self, path: str | Path) -> None:
        """Save bytes unchanged; transaction artifacts use JournalStore's atomic writer."""
        Path(path).write_bytes(self.raw)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    @property
    def short_hash(self) -> str:
        return self.sha256[:12]

    @property
    def personality(self) -> int:
        return int.from_bytes(self.raw[0:4], "little")

    @property
    def trainer_id(self) -> int:
        return int.from_bytes(self.raw[4:8], "little")

    def _decrypted_secure(self) -> bytes:
        key = self.personality ^ self.trainer_id
        secure = bytearray(self.raw[SECURE_START:SECURE_END])
        for offset in range(0, len(secure), 4):
            value = int.from_bytes(secure[offset : offset + 4], "little") ^ key
            secure[offset : offset + 4] = value.to_bytes(4, "little")
        return bytes(secure)

    @property
    def checksum_valid(self) -> bool:
        secure = self._decrypted_secure()
        calculated = sum(
            int.from_bytes(secure[offset : offset + 2], "little")
            for offset in range(0, len(secure), 2)
        ) & 0xFFFF
        stored = int.from_bytes(self.raw[28:30], "little")
        return calculated == stored

    @property
    def held_item(self) -> int:
        secure = self._decrypted_secure()
        order = SUBSTRUCT_ORDERS[self.personality % 24]
        growth_offset = order.index("G") * 12
        return int.from_bytes(secure[growth_offset + 2 : growth_offset + 4], "little")

    @property
    def holds_mail(self) -> bool:
        return MAIL_ITEM_MIN <= self.held_item <= MAIL_ITEM_MAX

    def refuse_mail(self) -> None:
        if self.holds_mail:
            raise MailNotSupported(
                f"record {self.short_hash} holds a Mail item ({self.held_item}); "
                "v1 cannot prove 220-byte mail preservation"
            )

    def hex_debug(self, limit: int = 32) -> str:
        if not 0 <= limit <= PARTY_RECORD_SIZE:
            raise ValueError("limit must be in 0..100")
        suffix = "…" if limit < PARTY_RECORD_SIZE else ""
        return self.raw[:limit].hex() + suffix

    def __bytes__(self) -> bytes:
        return self.raw

