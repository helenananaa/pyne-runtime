"""Fixed-horizon incremental historical execution; no realtime flag substitution."""
from __future__ import annotations
import copy
from collections.abc import Mapping
from numbers import Real
from .incremental import PyneIncrementalSession, is_incremental_pyne_script
from .incremental.session import PyneIncrementalSessionSnapshot
from .data import PyneData
from .incremental._bar_admission import admit_bar
from .barstate import PyneIncrementalBarState
from .security import enforce_input_limits


class HistoricalSession:
    def __init__(self, source, bars, *, params=None, settings=None):
        if not bars:
            raise ValueError("history cannot be empty")
        self._session = PyneIncrementalSession(script=source, params=params or {}, settings=settings)
        enforce_input_limits(len(bars), self._session.policy)
        validated = PyneData.from_ohlcv(bars)
        if not is_incremental_pyne_script(source):
            raise ValueError("fixed history requires init/on_bar script")
        self._bars = copy.deepcopy(bars)
        self._times = tuple(bar["time"] for bar in validated)
        self._session.seed([])
        self.equity = []
        self.cursor = 0

    def advance(self, target):
        if type(target) is not int or not self.cursor <= target <= len(self._bars):
            raise ValueError("historical cursor outside forward range")
        session = self._session
        session._ensure_healthy()
        while self.cursor < target:
            index = self.cursor
            bar = admit_bar(self._bars[index])
            session._validate_event_time(bar, preview=False)
            session._run_bar(session._ctx, bar, preview=False, bar_index=index, last_bar_index=len(self._bars)-1,
                barstate=PyneIncrementalBarState(isfirst=index==0, islast=index==len(self._bars)-1,
                    ishistory=True, isrealtime=False, isnew=True, isconfirmed=True, islastconfirmedhistory=index==len(self._bars)-1))
            session.last_closed_time = bar.time
            session._closed_count = index + 1
            session._commit_retention(bar.time)
            # Portable realtime snapshots cannot represent this distinct horizon contract.
            session._portable_complete = False
            self.cursor += 1
            self.equity.append({"time": bar.time, "value": session._ctx.strategy.equity})
        return session.snapshot_result()

    def snapshot(self):
        return {"contract": "pyne.fixed-history/1", "horizon": copy.deepcopy(self._bars), "cursor": self.cursor,
                "state": self._session.snapshot_state(), "equity": copy.deepcopy(self.equity)}

    def restore(self, snapshot):
        if (not isinstance(snapshot, Mapping) or snapshot.get("contract") != "pyne.fixed-history/1"
                or snapshot.get("horizon") != self._bars):
            raise ValueError("historical snapshot horizon mismatch")
        cursor = snapshot.get("cursor")
        state, incoming_equity = snapshot.get("state"), snapshot.get("equity")
        if (type(cursor) is not int or not 0 <= cursor <= len(self._bars)
                or not isinstance(state, PyneIncrementalSessionSnapshot)
                or cursor != state.closed_count or type(incoming_equity) is not list
                or len(incoming_equity) != cursor):
            raise ValueError("historical snapshot cursor mismatch")
        retained = cursor if state.retention_bars is None else min(cursor, state.retention_bars)
        if (state.retained_closed_times != self._times[cursor - retained:cursor]
                or state.last_closed_time != (self._times[cursor - 1] if cursor else None)):
            raise ValueError("historical snapshot state timeline mismatch")
        if state.context is None:
            raise ValueError("historical snapshot initialization is missing")
        if cursor:
            bar = state.context.current_bar
            if (bar is None or state.context.last_bar_index != len(self._bars) - 1
                    or bar.last_bar_index != len(self._bars) - 1 or not bar.is_history or bar.is_realtime):
                raise ValueError("historical snapshot horizon flags mismatch")
        for index, point in enumerate(incoming_equity):
            if (type(point) is not dict or set(point) != {"time", "value"}
                    or type(point["time"]) is not int or point["time"] != self._times[index]
                    or isinstance(point["value"], bool) or not isinstance(point["value"], Real)):
                raise ValueError("historical snapshot equity is invalid")
        equity = copy.deepcopy(incoming_equity)
        self._session.restore_state(state)
        self.cursor = cursor
        self.equity = equity
