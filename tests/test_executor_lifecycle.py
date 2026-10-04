"""Process admission, transport failures and explicit resource cleanup."""
from types import SimpleNamespace
import pickle

import pytest

import pyne_runtime as pn
import pyne_runtime.executor as executor


BARS = [dict(time=1, open=1, high=1, low=1, close=1, volume=1)]


@pytest.mark.parametrize("entry", [executor.execute_pyne_script, executor.execute_pyne_script_in_process])
@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -1])
def test_invalid_timeout_rejects_before_allocating_process(entry, timeout, monkeypatch):
    def forbidden():
        pytest.fail("Invalid deadline must not allocate multiprocessing resources")
    monkeypatch.setattr(executor, "_multiprocessing_context", forbidden)
    with pytest.raises(ValueError, match="timeout_seconds must be finite and non-negative"):
        entry(script="plot(close)", ohlcv=BARS, timeout_seconds=timeout)


def test_unpickleable_output_reports_result_serialization_failure():
    result = pn.run('indicator("Payload", callback=lambda: None)\nplot(close)', BARS,
                    executor_mode="process", settings=pn.PyneSettings(timeout_seconds=5))
    assert not result.ok
    assert result.code == "PYNE_PROCESS_SERIALIZATION_ERROR"
    assert "result must be pickle-serializable" in result.error
    assert "results" in result.hint and "inline" in result.hint
    assert pn.run('plot(close)', BARS, executor_mode="process").ok


class FakeQueue:
    def __init__(self):
        self.closed = self.joined = False
        self.payload = None

    def put(self, payload):
        self.payload = payload

    def close(self):
        self.closed = True

    def join_thread(self):
        self.joined = True


class FakeProcess:
    def __init__(self, *, spawn_error=False, stubborn=False):
        self.spawn_error = spawn_error
        self.stubborn = stubborn
        self.alive = self.started = self.closed = self.terminated = self.killed = False
        self.exitcode = 0

    def start(self):
        if self.spawn_error:
            raise OSError("worker creation failed")
        self.alive = self.started = True

    def is_alive(self):
        return self.alive

    def join(self, timeout):
        if not self.stubborn:
            self.alive = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.alive = False

    def close(self):
        assert not self.alive
        self.closed = True


@pytest.mark.parametrize("case", ["success", "invalid-result", "decode-error", "timeout", "spawn-error",
                                 "queue-read-error", "interrupted", "dead-worker"])
def test_process_and_queue_close_on_every_exit(case, monkeypatch):
    result_queue = FakeQueue()
    process = FakeProcess(spawn_error=case == "spawn-error", stubborn=case == "timeout")
    context = SimpleNamespace(Queue=lambda **kwargs: result_queue, Process=lambda **kwargs: process)
    monkeypatch.setattr(executor, "_multiprocessing_context", lambda: context)

    def read(*args):
        if case == "queue-read-error":
            raise OSError("transport failed")
        if case == "interrupted":
            raise KeyboardInterrupt()
        if case == "dead-worker":
            process.alive = False
            process.exitcode = 8
            return None
        if case == "timeout":
            return None
        if case == "decode-error":
            return b"not a pickle"
        if case == "invalid-result":
            return 42
        return pickle.dumps({"kind": "result", "result": pn.PyneResult(ok=True).to_dict()})

    monkeypatch.setattr(executor, "_read_process_result", read)
    if case == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            executor.execute_pyne_script_in_process(script="plot(close)", ohlcv=BARS)
    else:
        result = executor.execute_pyne_script_in_process(script="plot(close)", ohlcv=BARS,
                                                        settings=pn.PyneSettings(timeout_seconds=1))
        assert result.ok == (case == "success")
        if case == "timeout":
            assert result.code == "PYNE_TIMEOUT"
            assert process.terminated and process.killed
        elif case != "success":
            assert result.code == "PYNE_PROCESS_FAILED"
    assert result_queue.closed and result_queue.joined
    assert process.closed


def test_worker_serializes_custom_result_once_before_queue(monkeypatch):
    calls = []
    class Custom:
        def __reduce__(self):
            calls.append(True)
            return str, ("transported",)
    value = Custom()
    class Runtime:
        def __init__(self, **kwargs):
            pass
        def execute(self, **kwargs):
            return SimpleNamespace(to_dict=lambda: {"ok": True, "meta": {"value": value}})
    monkeypatch.setattr(executor, "PyneRuntime", Runtime)
    result_queue = FakeQueue()
    executor._pyne_worker(result_queue, "plot(close)", BARS, {}, None, pn.PyneSettings())
    assert isinstance(result_queue.payload, bytes)
    assert pickle.loads(result_queue.payload)["result"]["meta"]["value"] == "transported"
    assert calls == [True]
