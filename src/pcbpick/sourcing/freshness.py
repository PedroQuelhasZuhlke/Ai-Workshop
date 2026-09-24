"""Pure freshness policy for supplier-sourced data.

No network I/O, no wall-clock reads: `now` always arrives from the caller (ultimately
`StageContext.now` upstream, or a live adapter's own injected clock), per
`.github/instructions/python.instructions.md`'s "no module-level clock" rule. This is
what lets a live adapter's pre-export re-validation decision be unit-tested without
ever touching real time.
"""

from datetime import datetime, timedelta


def is_stale(fetched_at: datetime, *, now: datetime, max_age: timedelta) -> bool:
    """True when `fetched_at` is older than `max_age` relative to `now`."""
    return now - fetched_at > max_age
