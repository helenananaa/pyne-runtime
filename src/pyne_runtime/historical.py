"""Fixed-horizon incremental historical execution; no realtime flag substitution."""
from __future__ import annotations
import copy
from .incremental import PyneIncrementalSession, is_incremental_pyne_script
from .data import PyneData
from .incremental.bar import IncrementalBar
from .barstate import PyneIncrementalBarState


class HistoricalSession:
    def __init__(self, source, bars, *, params=None, settings=None):
        if not bars: raise ValueError("history cannot be empty")
        PyneData.from_ohlcv(bars)
        if not is_incremental_pyne_script(source):
            raise ValueError("fixed history requires init/on_bar script")
        self._bars = copy.deepcopy(bars)
        self._session = PyneIncrementalSession(script=source, params=params or {}, settings=settings)
        self._session.seed([])
        self.equity = []
        self.cursor = 0

    def advance(self, target):
        if type(target) is not int or not self.cursor <= target <= len(self._bars):
            raise ValueError("historical cursor outside forward range")
        session = self._session
        while self.cursor < target:
            index = self.cursor
            bar = IncrementalBar.from_dict(self._bars[index], is_confirmed=True)
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
        if snapshot.get("contract") != "pyne.fixed-history/1" or snapshot.get("horizon") != self._bars:
            raise ValueError("historical snapshot horizon mismatch")
        cursor = snapshot.get("cursor")
        if (type(cursor) is not int or not 0 <= cursor <= len(self._bars)
                or cursor != snapshot["state"].closed_count or len(snapshot["equity"]) != cursor):
            raise ValueError("historical snapshot cursor mismatch")
        self._session.restore_state(snapshot["state"])
        self.cursor = snapshot["cursor"]
        self.equity = copy.deepcopy(snapshot["equity"])
