"""Acceptance: transient request-provider fault, typed-state restore, plot retention.

These checks use only public session, snapshot, result-line, and request-error
APIs. They do not treat provider history revisions as a supported data-update
protocol; a second provider that would answer different historical values is
only a probe that already-committed timestamped points stay put.
"""

from __future__ import annotations

import copy

import pyne_runtime as pn
import pytest
from pyne_runtime.security import PyneSecurityError


SYMBOL = "TEST:ASSET"
CHART_TF = "10S"
SECURITY_TF = "10S"
LOWER_TF = "5S"
CHART_STEP = 10
LOWER_STEP = 5
REVISION_SHIFT = 1_000_000.0

SECURITY_SCRIPT = """
indicator("Request recovery security", mode="incremental")
def on_bar(ctx, bar):
    count = ctx.state("count", 0)
    count.value += 1
    ctx.plot("Count", count.value)
    ctx.plot("Requested", ctx.request.security("TEST:ASSET", "10S", "close"))
"""

LOWER_TF_SCRIPT = """
indicator("Request recovery lower tf", mode="incremental")
def on_bar(ctx, bar):
    count = ctx.state("count", 0)
    count.value += 1
    ctx.plot("Count", count.value)
    lower = ctx.request.security_lower_tf("TEST:ASSET", "5S", "close")
    ctx.plot("LTF Count", lower.size())
    ctx.plot("LTF Last", lower.last())
"""


def chart_bars(count: int = 8) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for index in range(count):
        close = 100.0 + index
        rows.append(
            {
                "time": index * CHART_STEP,
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 10.0,
            }
        )
    return rows


def security_close(timestamp: int, revision: int = 0) -> float:
    return 1000.0 + timestamp + revision * REVISION_SHIFT


def lower_tf_close(timestamp: int, revision: int = 0) -> float:
    return 2000.0 + timestamp + revision * REVISION_SHIFT


def script_for(api: str) -> str:
    if api == "request.security":
        return SECURITY_SCRIPT
    if api == "request.security_lower_tf":
        return LOWER_TF_SCRIPT
    raise ValueError(api)


class ImmutableOHLCVProvider:
    """Host-neutral immutable OHLCV. Optional fail on a newly fetched range."""

    capabilities = {
        "request.security": True,
        "request.security_lower_tf": True,
    }

    def __init__(self, *, revision: int = 0) -> None:
        self.revision = revision
        self.fail_on_new_range = False
        self.calls: list[tuple[str, int, int]] = []
        self._served_end: dict[str, int] = {}

    def arm_new_range_failure(self) -> None:
        self.fail_on_new_range = True

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, float]]:
        assert symbol == SYMBOL
        start_i = int(start)
        end_i = int(end)
        self.calls.append((timeframe, start_i, end_i))
        if self.fail_on_new_range:
            served = self._served_end.get(timeframe)
            if served is not None and end_i > served:
                raise pn.PyneProviderDataError("transient market data fault")
        step = {"10S": CHART_STEP, "5S": LOWER_STEP}[timeframe]
        first = start_i if start_i % step == 0 else start_i + (step - start_i % step)
        rows: list[dict[str, float]] = []
        for timestamp in range(first, end_i + 1, step):
            close = (
                security_close(timestamp, self.revision)
                if timeframe == SECURITY_TF
                else lower_tf_close(timestamp, self.revision)
            )
            rows.append(
                {
                    "time": timestamp,
                    "open": close,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "volume": 1.0,
                }
            )
        previous = self._served_end.get(timeframe)
        self._served_end[timeframe] = end_i if previous is None else max(previous, end_i)
        return rows

    def get_request_metadata(self, symbol: str, timeframe: str) -> dict[str, object]:
        return {"syminfo": {"tickerid": symbol}, "timeframe": timeframe}


def settings_for(
    provider: ImmutableOHLCVProvider,
    *,
    cache_max_items: int | None = None,
) -> pn.PyneSettings:
    kwargs: dict[str, object] = {
        "executor_mode": "inline",
        "timeframe": CHART_TF,
        "syminfo": {"tickerid": SYMBOL},
        "data_provider": provider,
    }
    if cache_max_items is not None:
        kwargs["cache_max_items"] = cache_max_items
    return pn.PyneSettings(**kwargs)


def new_session(
    api: str,
    provider: ImmutableOHLCVProvider,
    *,
    cache_max_items: int | None = None,
    retention_bars: int = 8,
) -> pn.PyneIncrementalSession:
    return pn.PyneIncrementalSession(
        script=script_for(api),
        settings=settings_for(provider, cache_max_items=cache_max_items),
        retention_bars=retention_bars,
    )


def restore_typed_state(
    payload: bytes,
    api: str,
    provider: ImmutableOHLCVProvider,
    *,
    cache_max_items: int | None = None,
) -> pn.PyneIncrementalSession:
    return pn.PyneIncrementalSession.from_portable_snapshot(
        payload,
        script=script_for(api),
        settings=settings_for(provider, cache_max_items=cache_max_items),
    )


def expected_points(
    api: str,
    bars: list[dict[str, float]],
    *,
    revision: int = 0,
) -> dict[str, list[tuple[int, float]]]:
    count = [(int(bar["time"]), float(index + 1)) for index, bar in enumerate(bars)]
    if api == "request.security":
        return {
            "Count": count,
            "Requested": [
                (int(bar["time"]), security_close(int(bar["time"]), revision))
                for bar in bars
            ],
        }
    return {
        "Count": count,
        "LTF Count": [(int(bar["time"]), 2.0) for bar in bars],
        "LTF Last": [
            (int(bar["time"]), lower_tf_close(int(bar["time"]) + LOWER_STEP, revision))
            for bar in bars
        ],
    }


def plot_points(result: object) -> dict[str, list[tuple[int, float | None]]]:
    assert result.ok, result.error
    points: dict[str, list[tuple[int, float | None]]] = {}
    for line in result.lines:
        series: list[tuple[int, float | None]] = []
        for item in line["data"]:
            value = item["value"]
            series.append((int(item["time"]), None if value is None else float(value)))
        points[line["name"]] = series
    return points


def points_at(
    points: dict[str, list[tuple[int, float | None]]],
    timestamps: list[int],
) -> dict[str, list[tuple[int, float | None]]]:
    wanted = set(timestamps)
    return {
        name: [item for item in series if item[0] in wanted]
        for name, series in points.items()
    }


def assert_points_match(
    actual: dict[str, list[tuple[int, float | None]]],
    expected: dict[str, list[tuple[int, float]]],
) -> None:
    assert set(actual) == set(expected)
    for name, series in expected.items():
        observed = actual[name]
        assert [item[0] for item in observed] == [item[0] for item in series]
        assert [item[1] for item in observed] == [item[1] for item in series]


def assert_committed_numeric_equal(
    actual: object,
    control: object,
    expected: dict[str, list[tuple[int, float]]],
) -> None:
    """Compare public plot transport and structured output, not fetch diagnostics.

    Excluded because they are not computation identity after a cold restore:
    ``meta["requestDiagnostics"]`` and ``meta["requestDiagnosticsInfo"]`` (cache
    hits, adaptive start/end, dropped counts), plus ``meta["barstate"]["isnew"]``
    when a later preview has already visited the same bar. Snapshot bookkeeping
    such as ``retentionBars`` / ``retainedBars`` / ``totalCommittedBars`` is
    compared when present on both sides.
    """
    assert actual.ok and control.ok
    actual_points = plot_points(actual)
    control_points = plot_points(control)
    assert actual_points == control_points
    assert_points_match(actual_points, expected)
    assert actual.output == control.output
    left = copy.deepcopy(actual.meta)
    right = copy.deepcopy(control.meta)
    for meta in (left, right):
        meta.pop("requestDiagnostics", None)
        meta.pop("requestDiagnosticsInfo", None)
        meta.get("barstate", {}).pop("isnew", None)
    assert left == right


@pytest.mark.parametrize("api", ("request.security", "request.security_lower_tf"))
def test_transient_provider_fault_poisons_then_typed_state_restore_matches_control(api: str) -> None:
    data = chart_bars(8)
    failing = ImmutableOHLCVProvider()
    control_provider = ImmutableOHLCVProvider()
    recovered_provider = ImmutableOHLCVProvider()
    session = new_session(api, failing)
    control = new_session(api, control_provider)

    first = session.seed(data[:2])
    control.seed(data[:2])
    assert first.ok, first.error
    assert control.snapshot_result().ok
    assert len(data[:2]) >= 2

    checkpoint = session.snapshot_portable_state()
    prefix_expected = expected_points(api, data[:2])
    assert_committed_numeric_equal(session.snapshot_result(), control.snapshot_result(), prefix_expected)

    failing.arm_new_range_failure()
    with pytest.raises(pn.PyneRequestError) as error:
        session.on_bar_closed(data[2])
    assert error.value.category == "providerFailure"
    assert error.value.code == "PYNE_RUNTIME_ERROR"
    assert error.value.request_context.get("api") == api
    assert error.value.request_context.get("symbol") == SYMBOL

    with pytest.raises(PyneSecurityError, match="poisoned"):
        session.on_bar_closed(data[2])

    recovered = restore_typed_state(checkpoint, api, recovered_provider)
    assert_committed_numeric_equal(
        recovered.snapshot_result(),
        control.snapshot_result(),
        prefix_expected,
    )

    committed = list(data[:2])
    for bar in data[2:]:
        recovered_result = recovered.on_bar_closed(bar)
        control_result = control.on_bar_closed(bar)
        committed.append(bar)
        current = expected_points(api, committed)
        current_time = [int(bar["time"])]
        assert_committed_numeric_equal(
            recovered_result,
            control_result,
            points_at(current, current_time),
        )
        assert_committed_numeric_equal(
            recovered.snapshot_result(),
            control.snapshot_result(),
            current,
        )


@pytest.mark.parametrize("api", ("request.security", "request.security_lower_tf"))
def test_later_steps_keep_retained_points_when_provider_history_would_differ(api: str) -> None:
    data = chart_bars(8)
    original = ImmutableOHLCVProvider(revision=0)
    # Declared cache-item limit may evict covered request ranges; plot retention
    # is still the session window. This is not a provider-revision feature.
    session = new_session(api, original, cache_max_items=1)
    prefix_bars = data[:3]
    seeded = session.seed(prefix_bars)
    assert seeded.ok, seeded.error
    checkpoint = session.snapshot_portable_state()
    retained = plot_points(session.snapshot_result())
    prefix_times = [int(bar["time"]) for bar in prefix_bars]
    assert_points_match(retained, expected_points(api, prefix_bars, revision=0))

    revised = ImmutableOHLCVProvider(revision=1)
    recovered = restore_typed_state(checkpoint, api, revised, cache_max_items=1)
    assert points_at(plot_points(recovered.snapshot_result()), prefix_times) == points_at(
        retained, prefix_times
    )

    committed = list(prefix_bars)
    for bar in data[3:]:
        preview = recovered.on_bar_updated(bar)
        assert preview.ok, preview.error
        assert points_at(plot_points(recovered.snapshot_result()), prefix_times) == points_at(
            retained, prefix_times
        )
        current_time = [int(bar["time"])]
        committed_with_preview = committed + [bar]
        assert_points_match(
            points_at(plot_points(preview), current_time),
            points_at(expected_points(api, committed_with_preview, revision=1), current_time),
        )
        closed = recovered.on_bar_closed(bar)
        committed.append(bar)
        closed_points = plot_points(closed)
        assert_points_match(
            points_at(closed_points, current_time),
            points_at(expected_points(api, committed, revision=1), current_time),
        )
        retained_after = plot_points(recovered.snapshot_result())
        assert points_at(retained_after, prefix_times) == points_at(retained, prefix_times)
        mixed = expected_points(api, committed, revision=1)
        for name, series in expected_points(api, prefix_bars, revision=0).items():
            mixed[name] = series + [item for item in mixed[name] if item[0] not in set(prefix_times)]
        assert_points_match(retained_after, mixed)

