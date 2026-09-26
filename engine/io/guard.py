"""Garde-fou des appels API externes (spec §5).

Par hôte : intervalle minimal entre appels, retries avec attente croissante
(ou Retry-After), disjoncteur après N échecs consécutifs, budget d'appels
par job. Akamai (stats.nba.com) répond parfois 200 avec un contenu vide :
`is_empty` permet de traiter ce cas comme un échec à retenter.
"""
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


class BreakerOpen(RuntimeError):
    """Hôte coupé pour ce passage après trop d'échecs consécutifs."""


class BudgetExceeded(RuntimeError):
    """Budget d'appels de l'hôte épuisé pour ce job."""


@dataclass(frozen=True)
class HostPolicy:
    min_interval: float
    max_retries: int
    breaker_threshold: int
    budget: int
    base_backoff: float = 2.0


DEFAULT_POLICIES = {
    "stats.nba.com": HostPolicy(min_interval=5.0, max_retries=2, breaker_threshold=3, budget=400),
    "cdn.nba.com": HostPolicy(min_interval=1.0, max_retries=2, breaker_threshold=5, budget=300),
    "espn": HostPolicy(min_interval=1.0, max_retries=2, breaker_threshold=3, budget=20),
}


def _retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    try:
        value = headers.get("Retry-After")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class ApiGuard:
    def __init__(self, policies: dict[str, HostPolicy] | None = None, *,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.policies = policies or DEFAULT_POLICIES
        self._sleep = sleep
        self._clock = clock
        self._last_call: dict[str, float] = {}
        self._consecutive_failures: dict[str, int] = {}
        self._calls: dict[str, int] = {}
        self._failures: dict[str, int] = {}

    def is_open(self, host: str) -> bool:
        return self._consecutive_failures.get(host, 0) >= self.policies[host].breaker_threshold

    def summary(self) -> dict[str, dict[str, int]]:
        hosts = set(self._calls) | set(self._failures)
        return {h: {"calls": self._calls.get(h, 0), "failures": self._failures.get(h, 0)} for h in sorted(hosts)}

    def _wait_turn(self, host: str, policy: HostPolicy) -> None:
        last = self._last_call.get(host)
        if last is not None:
            elapsed = self._clock() - last
            if elapsed < policy.min_interval:
                self._sleep(policy.min_interval - elapsed)
        self._last_call[host] = self._clock()

    def call(self, host: str, fn: Callable[[], T], *,
             is_empty: Callable[[T], bool] = lambda r: False) -> T:
        policy = self.policies[host]
        if self.is_open(host):
            raise BreakerOpen(host)
        last_exc: Exception | None = None
        result = None
        for attempt in range(policy.max_retries + 1):
            if self._calls.get(host, 0) >= policy.budget:
                raise BudgetExceeded(host)
            self._wait_turn(host, policy)
            self._calls[host] = self._calls.get(host, 0) + 1
            delay = None
            try:
                result = fn()
            except Exception as exc:  # réseau, 429, 5xx, timeout
                last_exc = exc
                delay = _retry_after(exc)
            else:
                last_exc = None
                if not is_empty(result):
                    self._consecutive_failures[host] = 0
                    return result
            if attempt < policy.max_retries:
                self._sleep(delay if delay is not None else policy.base_backoff * (2 ** attempt))
        self._consecutive_failures[host] = self._consecutive_failures.get(host, 0) + 1
        self._failures[host] = self._failures.get(host, 0) + 1
        if last_exc is not None:
            raise last_exc
        return result
