"""Application-level database errors, raised by db/queries.py's run() so callers and the API's
exception handlers can respond to WHAT failed, not to raw PostgREST/httpx errors."""


class DatabaseUnavailableError(RuntimeError):
    """A transient database failure (timeout, connection error, PostgREST pool timeout) that
    retrying did not resolve - or that was not retried because the operation is not idempotent.

    `outcome_uncertain` is True for a failed non-idempotent write (a plain INSERT): the request
    may have reached the database and committed before the reply was lost, so the caller cannot
    know whether it happened. False for reads and idempotent writes, which simply did not
    succeed. api/main.py turns this into a 503 whose message reflects the difference."""

    def __init__(self, operation: str, outcome_uncertain: bool):
        self.operation = operation
        self.outcome_uncertain = outcome_uncertain
        kind = "outcome uncertain" if outcome_uncertain else "not completed"
        super().__init__(f"Database unavailable during {operation} ({kind})")
