"""Domain exceptions for pcbpick. Raise these instead of bare ValueError/RuntimeError."""


class PcbPickError(Exception):
    """Base class for all pcbpick domain errors."""


class RunNotFoundError(PcbPickError):
    """Raised when a run id has no corresponding run directory."""


class StageNotFoundError(PcbPickError):
    """Raised when a `--from` target does not match a registered stage."""


class ContractViolationError(PcbPickError):
    """Raised when an artifact fails to satisfy its contract at a stage boundary."""


class IngestFileError(PcbPickError):
    """Raised when a BOM source file cannot be safely read (size, format, encoding limits)."""
