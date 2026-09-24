"""Shared, adapter-agnostic resilience helper: rate limiting, retry with backoff, and
circuit breaking, per `.github/instructions/supplier-adapters.instructions.md`.

Mouser, DigiKey, and Farnell adapters each construct one `ResilientCaller` and route
every HTTP attempt through `ResilientCaller.call` instead of reimplementing any of
this. This module is the one place in the package allowed to sleep and read a
monotonic clock (`sourcing/suppliers/` is the sanctioned I/O boundary) — both are
still injected (`sleep_fn`, `time_fn`, `rand_fn`) so tests never actually wait or
depend on wall-clock jitter.

`call()` never raises for a supplier-side failure: rate-limited, retried-out, or
circuit-open calls all come back as a failed `AdapterCallResult` instead, per the
"a dead supplier degrades a run; it never hangs or fails one" rule. Only a
programmer error inside the adapter's own attempt callable that isn't reported via
`AdapterHttpError` propagates — that would mean the pipeline itself is broken, not
the supplier.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from time import sleep as _real_sleep


class AdapterHttpError(Exception):
    """Raised by an adapter's attempt callable to report one HTTP-layer failure.

    `status_code` is `None` for a connection-level failure (timeout, refused, DNS) —
    still worth retrying. Any other 4xx is treated as non-retryable: retrying a
    malformed request or bad credentials cannot succeed differently.
    """

    def __init__(self, status_code: int | None, retry_after_seconds: float | None = None) -> None:
        super().__init__(f"adapter http error (status={status_code})")
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds

    @property
    def is_retryable(self) -> bool:
        return self.status_code is None or self.status_code == 429 or 500 <= self.status_code < 600


@dataclass(frozen=True)
class RateLimitConfig:
    """A token-bucket budget: `max_calls` tokens refilling over `period_seconds`."""

    max_calls: int
    period_seconds: float


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    cooldown_seconds: float = 60.0


@dataclass(frozen=True)
class AdapterCallResult[T]:
    """The outcome of one resilient call. Never raises; always inspect `failed`."""

    value: T | None
    failed: bool
    error: str | None = None
    attempts: int = 0


class RateLimiter:
    """Token bucket. `acquire()` blocks (via the injected `sleep_fn`) until a token is free."""

    def __init__(
        self,
        config: RateLimitConfig,
        *,
        time_fn: Callable[[], float] = monotonic,
        sleep_fn: Callable[[float], None] = _real_sleep,
    ) -> None:
        self._config = config
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._tokens = float(config.max_calls)
        self._last_refill = time_fn()

    def acquire(self) -> None:
        refill_rate = self._config.max_calls / self._config.period_seconds
        now = self._time_fn()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._config.max_calls), self._tokens + elapsed * refill_rate)
        self._last_refill = now

        if self._tokens < 1:
            wait_seconds = (1 - self._tokens) / refill_rate
            self._sleep_fn(wait_seconds)
            self._tokens = 0.0
            self._last_refill = self._time_fn()
        else:
            self._tokens -= 1


class CircuitBreaker:
    """Opens after `failure_threshold` consecutive failures; half-opens after cooldown."""

    def __init__(
        self, config: CircuitBreakerConfig, *, time_fn: Callable[[], float] = monotonic
    ) -> None:
        self._config = config
        self._time_fn = time_fn
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if self._time_fn() - self._opened_at >= self._config.cooldown_seconds:
            return False  # cooldown elapsed: half-open, let the next call try again
        return True

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._config.failure_threshold:
            self._opened_at = self._time_fn()


class ResilientCaller:
    """One rate limiter + retry policy + circuit breaker, shared by one adapter."""

    def __init__(
        self,
        *,
        rate_limit: RateLimitConfig,
        retry: RetryConfig | None = None,
        circuit_breaker: CircuitBreakerConfig | None = None,
        time_fn: Callable[[], float] = monotonic,
        sleep_fn: Callable[[float], None] = _real_sleep,
        rand_fn: Callable[[], float] = random.random,
    ) -> None:
        retry = retry if retry is not None else RetryConfig()
        circuit_breaker = circuit_breaker if circuit_breaker is not None else CircuitBreakerConfig()
        self._limiter = RateLimiter(rate_limit, time_fn=time_fn, sleep_fn=sleep_fn)
        self._breaker = CircuitBreaker(circuit_breaker, time_fn=time_fn)
        self._retry = retry
        self._sleep_fn = sleep_fn
        self._rand_fn = rand_fn

    @property
    def circuit_open(self) -> bool:
        return self._breaker.is_open

    def call[T](self, attempt: Callable[[], T]) -> AdapterCallResult[T]:
        if self._breaker.is_open:
            return AdapterCallResult(value=None, failed=True, error="circuit_open", attempts=0)

        last_error = "unknown_error"
        attempt_number = 0
        max_attempts = self._retry.max_retries + 1
        for attempt_number in range(1, max_attempts + 1):
            self._limiter.acquire()
            try:
                value = attempt()
            except AdapterHttpError as exc:
                last_error = f"http_status_{exc.status_code}"
                self._breaker.record_failure()
                if not exc.is_retryable or attempt_number >= max_attempts:
                    return AdapterCallResult(
                        value=None, failed=True, error=last_error, attempts=attempt_number
                    )
                self._sleep_fn(self._backoff_delay(attempt_number, exc.retry_after_seconds))
                continue
            except Exception as exc:  # adapter boundary: recorded failure, never unhandled
                last_error = f"{type(exc).__name__}: {exc}"
                self._breaker.record_failure()
                return AdapterCallResult(
                    value=None, failed=True, error=last_error, attempts=attempt_number
                )
            else:
                self._breaker.record_success()
                return AdapterCallResult(value=value, failed=False, attempts=attempt_number)

        return AdapterCallResult(value=None, failed=True, error=last_error, attempts=attempt_number)

    def _backoff_delay(self, attempt_number: int, retry_after_seconds: float | None) -> float:
        if retry_after_seconds is not None:
            # Clamp a supplier-controlled `Retry-After` to the same ceiling as
            # exponential backoff: an unbounded value could stall the whole run.
            return max(0.0, min(retry_after_seconds, self._retry.max_delay_seconds))
        base: float = min(
            self._retry.max_delay_seconds,
            self._retry.base_delay_seconds * (2 ** (attempt_number - 1)),
        )
        jitter: float = self._rand_fn()
        return base * (0.5 + jitter)  # full jitter around the exponential base
