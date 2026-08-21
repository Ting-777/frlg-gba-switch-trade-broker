"""Domain exceptions. Endpoint failures must never be silently reinterpreted."""


class BrokerError(Exception):
    """Base class for expected broker failures."""


class InvalidPokemon(BrokerError, ValueError):
    """A record is not an exact or acceptable Gen 3 party Pokémon."""


class MailNotSupported(InvalidPokemon):
    """Mail preservation is not proven for the active endpoint."""


class JournalError(BrokerError):
    """The durable transaction journal is invalid or unavailable."""


class InvalidTransition(JournalError):
    """A state transition would violate the deterministic state graph."""


class RecoveryRequired(BrokerError):
    """Human reconciliation is required before any further trade."""


class EndpointError(BrokerError):
    """A hardware or mock endpoint did not provide reliable evidence."""


class ProtocolError(EndpointError):
    """A framed endpoint message was invalid, corrupt, or replayed."""


class CommitNotConfirmed(EndpointError):
    """An endpoint returned without a reliable irreversible commit indication."""


class PlaceholderMismatch(RecoveryRequired):
    """The final record returned by Switch is not the original placeholder."""

