"""Tests for `pcbpick.sourcing.suppliers.resilience`, per
`.github/instructions/supplier-adapters.instructions.md`'s rate-limit/retry/circuit-breaker
rules. No real sleeping and no real wall clock: `time_fn`/`sleep_fn`/`rand_fn` are fake in
every test.
"""

from pcbpick.sourcing.suppliers.resilience import (
    AdapterHttpError,
    CircuitBreakerConfig,
    RateLimitConfig,
    RateLimiter,
    ResilientCaller,
    RetryConfig,
)


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_rate_limiter_queues_when_budget_exhausted() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(
        RateLimitConfig(max_calls=2, period_seconds=10), time_fn=clock.time, sleep_fn=clock.sleep
    )

    limiter.acquire()  # token 1, no wait
    limiter.acquire()  # token 2, no wait
    assert clock.now == 0.0

    limiter.acquire()  # bucket empty: must wait for a refill
    assert clock.now > 0.0


def test_rate_limiter_refills_over_time_without_waiting() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(
        RateLimitConfig(max_calls=1, period_seconds=1), time_fn=clock.time, sleep_fn=clock.sleep
    )

    limiter.acquire()
    clock.now += 1.0  # a full period elapses: bucket should have refilled
    limiter.acquire()
    assert clock.now == 1.0  # no additional sleep was needed


def test_retry_backs_off_and_eventually_succeeds() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    def attempt() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise AdapterHttpError(status_code=503)
        return "ok"

    caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=3, base_delay_seconds=1, max_delay_seconds=10),
        time_fn=clock.time,
        sleep_fn=clock.sleep,
        rand_fn=lambda: 0.0,
    )

    result = caller.call(attempt)

    assert result.failed is False
    assert result.value == "ok"
    assert result.attempts == 3
    assert clock.now > 0.0  # backoff actually slept between attempts


def test_retry_honors_retry_after_header() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    def attempt() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise AdapterHttpError(status_code=429, retry_after_seconds=42.0)
        return "ok"

    caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=3, base_delay_seconds=1, max_delay_seconds=10),
        time_fn=clock.time,
        sleep_fn=clock.sleep,
        rand_fn=lambda: 0.0,
    )

    result = caller.call(attempt)

    assert result.failed is False
    assert clock.now == 10.0  # server asked for 42s but it's clamped to max_delay_seconds


def test_retry_gives_up_after_max_retries_and_records_failure() -> None:
    clock = _FakeClock()

    def attempt() -> str:
        raise AdapterHttpError(status_code=500)

    caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=2, base_delay_seconds=0.1, max_delay_seconds=1),
        time_fn=clock.time,
        sleep_fn=clock.sleep,
        rand_fn=lambda: 0.0,
    )

    result = caller.call(attempt)

    assert result.failed is True
    assert result.value is None
    assert result.attempts == 3  # 1 initial + 2 retries
    assert result.error == "http_status_500"


def test_non_retryable_status_fails_immediately_without_retry() -> None:
    clock = _FakeClock()
    attempts = {"count": 0}

    def attempt() -> str:
        attempts["count"] += 1
        raise AdapterHttpError(status_code=404)

    caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=5),
        time_fn=clock.time,
        sleep_fn=clock.sleep,
    )

    result = caller.call(attempt)

    assert result.failed is True
    assert attempts["count"] == 1  # no retry attempted for a non-retryable 404


def test_circuit_breaker_opens_after_repeated_failures_and_short_circuits() -> None:
    clock = _FakeClock()

    def always_fails() -> str:
        raise AdapterHttpError(status_code=500)

    caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=2, cooldown_seconds=30),
        time_fn=clock.time,
        sleep_fn=clock.sleep,
    )

    first = caller.call(always_fails)
    second = caller.call(always_fails)
    assert first.failed is True
    assert second.failed is True

    attempts_after_open = {"count": 0}

    def counting_attempt() -> str:
        attempts_after_open["count"] += 1
        return "should never run"

    third = caller.call(counting_attempt)

    assert third.failed is True
    assert third.error == "circuit_open"
    assert attempts_after_open["count"] == 0  # short-circuited: the attempt never ran


def test_circuit_breaker_half_opens_after_cooldown() -> None:
    clock = _FakeClock()

    def always_fails() -> str:
        raise AdapterHttpError(status_code=500)

    caller = ResilientCaller(
        rate_limit=RateLimitConfig(max_calls=100, period_seconds=1),
        retry=RetryConfig(max_retries=0),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=10),
        time_fn=clock.time,
        sleep_fn=clock.sleep,
    )

    caller.call(always_fails)  # opens the breaker
    assert caller.call(lambda: "unused").error == "circuit_open"

    clock.now += 10.0  # cooldown elapses

    def succeeds() -> str:
        return "recovered"

    result = caller.call(succeeds)
    assert result.failed is False
    assert result.value == "recovered"


def test_call_never_raises_for_an_unexpected_exception() -> None:
    def attempt() -> str:
        raise RuntimeError("boom")

    caller = ResilientCaller(rate_limit=RateLimitConfig(max_calls=100, period_seconds=1))

    result = caller.call(attempt)

    assert result.failed is True
    assert "RuntimeError" in (result.error or "")
