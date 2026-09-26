import pytest

from engine.io.guard import ApiGuard, BreakerOpen, BudgetExceeded, HostPolicy


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def _guard(**policy):
    fc = FakeClock()
    p = HostPolicy(**{"min_interval": 5.0, "max_retries": 2, "breaker_threshold": 3, "budget": 10, **policy})
    return ApiGuard({"h": p}, sleep=fc.sleep, clock=fc.clock), fc


def test_intervalle_minimal_entre_appels():
    g, fc = _guard()
    g.call("h", lambda: 1)
    g.call("h", lambda: 2)
    assert fc.sleeps == [5.0]


def test_retry_sur_exception_puis_succes():
    g, fc = _guard(min_interval=0.0)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 2:
            raise ConnectionError("boom")
        return "ok"

    assert g.call("h", flaky) == "ok"
    assert fc.sleeps == [2.0]           # backoff base 2 s × 2^0
    assert g.summary() == {"h": {"calls": 2, "failures": 0}}


def test_retry_after_respecte():
    g, fc = _guard(min_interval=0.0)

    class Resp:
        headers = {"Retry-After": "7"}

    class TooMany(Exception):
        response = Resp()

    calls = []

    def limited():
        calls.append(1)
        if len(calls) == 1:
            raise TooMany()
        return "ok"

    assert g.call("h", limited) == "ok"
    assert fc.sleeps == [7.0]


def test_echec_definitif_releve_l_exception_et_compte():
    g, _ = _guard(min_interval=0.0)
    with pytest.raises(ConnectionError):
        g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert g.summary()["h"] == {"calls": 3, "failures": 1}


def test_reponse_vide_retentee_puis_rendue():
    g, _ = _guard(min_interval=0.0)
    assert g.call("h", lambda: [], is_empty=lambda r: not r) == []
    assert g.summary()["h"] == {"calls": 3, "failures": 1}


def test_disjoncteur_s_ouvre_et_bloque_sans_appel():
    g, _ = _guard(min_interval=0.0, max_retries=0, breaker_threshold=2)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert g.is_open("h")
    called = []
    with pytest.raises(BreakerOpen):
        g.call("h", lambda: called.append(1))
    assert called == []


def test_succes_remet_le_compteur_du_disjoncteur_a_zero():
    g, _ = _guard(min_interval=0.0, max_retries=0, breaker_threshold=2)
    with pytest.raises(ConnectionError):
        g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    g.call("h", lambda: "ok")
    with pytest.raises(ConnectionError):
        g.call("h", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert not g.is_open("h")


def test_budget_depasse():
    g, _ = _guard(min_interval=0.0, budget=2)
    g.call("h", lambda: 1)
    g.call("h", lambda: 2)
    with pytest.raises(BudgetExceeded):
        g.call("h", lambda: 3)
