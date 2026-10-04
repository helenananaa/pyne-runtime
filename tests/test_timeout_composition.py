"""Nested and caller-owned POSIX deadlines survive local Pyne execution."""
from types import SimpleNamespace

import pytest

import pyne_runtime._timeouts as timers
from pyne_runtime.security import PyneTimeoutError, execution_timeout


class Alarm:
    SIGALRM = 14
    ITIMER_REAL = 0
    SIG_IGN = 1
    SIG_DFL = 0

    def __init__(self, handler=SIG_IGN, delay=0, interval=0):
        self.now = 0.0
        self.handler = handler
        self.due = delay if delay else None
        self.interval = interval

    def getsignal(self, signal):
        return self.handler

    def signal(self, signal, handler):
        self.handler = handler

    def getitimer(self, timer):
        return (max(self.due - self.now, 0) if self.due is not None else 0, self.interval)

    def setitimer(self, timer, delay, interval=0):
        self.due = self.now + delay if delay else None
        self.interval = interval

    def trigger(self):
        assert self.due is not None
        self.now = self.due
        self.due = self.now + self.interval if self.interval else None
        self.handler(self.SIGALRM, None)


def install(monkeypatch, alarm):
    monkeypatch.setattr(timers, "signal", alarm)
    monkeypatch.setattr(timers, "monotonic", lambda: alarm.now)


def test_existing_caller_timer_restored_with_elapsed_remaining_time(monkeypatch):
    def callback(*args):
        pass
    alarm = Alarm(callback, delay=10, interval=2)
    install(monkeypatch, alarm)
    with execution_timeout(3):
        assert alarm.getitimer(0) == (3, 0)
        alarm.now += 1
    assert alarm.handler is callback
    assert alarm.getitimer(0) == (9, 2)


def test_nested_longer_timeout_cannot_extend_outer_deadline(monkeypatch):
    alarm = Alarm()
    install(monkeypatch, alarm)
    with pytest.raises(PyneTimeoutError, match="2s timeout"):
        with execution_timeout(2):
            with execution_timeout(10):
                assert alarm.getitimer(0) == (2, 0)
                alarm.trigger()
    assert alarm.handler == alarm.SIG_IGN
    assert alarm.getitimer(0) == (0, 0)


def test_shorter_inner_timeout_restores_outer_remaining_budget(monkeypatch):
    alarm = Alarm()
    install(monkeypatch, alarm)
    with execution_timeout(5):
        with pytest.raises(PyneTimeoutError, match="1s timeout"):
            with execution_timeout(1):
                alarm.trigger()
        assert alarm.getitimer(0) == (4, 0)
        with pytest.raises(PyneTimeoutError, match="5s timeout"):
            alarm.trigger()
    assert alarm.getitimer(0) == (0, 0)


def test_periodic_caller_handler_runs_without_discarding_pyne_deadline(monkeypatch):
    events = []
    alarm = Alarm(lambda *args: events.append(alarm.now), delay=1, interval=1)
    callback = alarm.handler
    install(monkeypatch, alarm)
    with pytest.raises(PyneTimeoutError, match="3s timeout"):
        with execution_timeout(3):
            alarm.trigger()
            alarm.trigger()
            alarm.trigger()
    assert events == [1, 2, 3]
    assert alarm.handler is callback
    assert alarm.getitimer(0) == (1, 1)


def test_caller_handler_exception_keeps_its_identity(monkeypatch):
    error = RuntimeError("caller deadline")
    def callback(*args):
        raise error
    alarm = Alarm(callback, delay=1)
    install(monkeypatch, alarm)
    with pytest.raises(RuntimeError) as caught:
        with execution_timeout(10):
            alarm.trigger()
    assert caught.value is error
    assert alarm.handler is callback
    assert alarm.getitimer(0) == (0, 0)


def test_unsupported_or_failed_timer_does_not_leave_pyne_handler_installed(monkeypatch):
    alarm = Alarm(delay=10)
    install(monkeypatch, alarm)
    def failed(*args):
        raise OSError("timer unavailable")
    monkeypatch.setattr(alarm, "setitimer", failed)
    with execution_timeout(1):
        assert alarm.handler == alarm.SIG_IGN
    monkeypatch.setattr(timers, "signal", SimpleNamespace())
    with execution_timeout(1):
        pass
