"""Strategy order lifecycle helpers."""

from __future__ import annotations

import heapq
from typing import Any, Callable

from .constants import StrategyIntrabarPath, StrategyOca, StrategySameBarPriority


def _validate_pending_entry_direction(orders, *, order_id: str, side: str) -> None:
    for previous in orders:
        if previous.get("type") == "entry" and str(previous.get("id") or "") == order_id and previous.get("side") != side:
            raise ValueError(
                f"PYNE_STRATEGY_PENDING_DIRECTION_CHANGE: pending entry {order_id!r} "
                "cannot change direction; cancel it first or use a different ID"
            )


def _exit_trigger(
    *,
    current_position: float,
    open_price: float,
    high: float,
    low: float,
    stop: float | None,
    limit: float | None,
    tick_verify: float = 0.0,
    same_bar_fill_priority: str = StrategySameBarPriority.stop_first,
    intrabar_path: str = StrategyIntrabarPath.same_bar_priority,
) -> tuple[str, float] | None:
    if current_position > 0:
        stop_hit = stop is not None and low <= stop
        limit_hit = limit is not None and high >= limit + tick_verify
        if stop_hit and limit_hit:
            reason, price = _same_bar_trigger(
                stop=stop,
                limit=limit,
                stop_path="low",
                limit_path="high",
                same_bar_fill_priority=same_bar_fill_priority,
                intrabar_path=intrabar_path,
            )
            return reason, _exit_fill_price(
                current_position=current_position,
                reason=reason,
                trigger_price=price,
                open_price=open_price,
            )
        if stop_hit:
            return "stop", _exit_fill_price(
                current_position=current_position,
                reason="stop",
                trigger_price=float(stop),
                open_price=open_price,
            )
        if limit_hit:
            return "limit", max(float(limit), float(open_price))
        return None
    stop_hit = stop is not None and high >= stop
    limit_hit = limit is not None and low <= limit - tick_verify
    if stop_hit and limit_hit:
        reason, price = _same_bar_trigger(
            stop=stop,
            limit=limit,
            stop_path="high",
            limit_path="low",
            same_bar_fill_priority=same_bar_fill_priority,
            intrabar_path=intrabar_path,
        )
        return reason, _exit_fill_price(
            current_position=current_position,
            reason=reason,
            trigger_price=price,
            open_price=open_price,
        )
    if stop_hit:
        return "stop", _exit_fill_price(
            current_position=current_position,
            reason="stop",
            trigger_price=float(stop),
            open_price=open_price,
        )
    if limit_hit:
        return "limit", min(float(limit), float(open_price))
    return None


def _is_pending_submission(order: dict[str, Any]) -> bool:
    return bool(order.get("_market_submission")) or order.get("_limit") is not None or order.get("_stop") is not None


def _pending_market_admission_state(orders, *, order_id: str | None, size: float, count: int) -> tuple[float, int]:
    """Reserve entry slots without making unfilled commands visible as trades."""
    for order in orders:
        if not order.get("_market_submission") or order.get("type") != "entry" or str(order.get("id")) == order_id:
            continue
        signed = abs(float(order.get("qty", 0.0))) * (1 if order.get("side") == "long" else -1)
        if size == 0 or (size > 0) != (signed > 0):
            size, count = signed, 1
        else:
            size += signed
            count += 1
    return size, count


class _PendingOrderBook:
    """Price-indexed pending orders with sequence-stable candidate selection."""

    def __init__(
        self,
        *,
        tick_verify: float,
        consume_operations: Callable[[int], None] | None = None,
    ) -> None:
        self._tick_verify = max(float(tick_verify), 0.0)
        self._consume_operations = consume_operations
        self._active: dict[int, dict[str, Any]] = {}
        self._versions: dict[int, int] = {}
        self._by_id: dict[str, set[int]] = {}
        self._by_oca: dict[tuple[str, str], set[int]] = {}
        self._long_stops: list[tuple[float, int, int]] = []
        self._long_limits: list[tuple[float, int, int]] = []
        self._short_stops: list[tuple[float, int, int]] = []
        self._short_limits: list[tuple[float, int, int]] = []
        self._market_seqs: set[int] = set()

    def __bool__(self) -> bool:
        return bool(self._active)

    def __len__(self) -> int:
        return len(self._active)

    def add(self, order: dict[str, Any]) -> None:
        seq = int(order.get("_seq", 0))
        if seq in self._active:
            self.reindex(order)
            return
        if order.get("type") in {"entry", "order"}:
            order_id = str(order.get("id") or "")
            previous_seqs = sorted(self._by_id.get(order_id, set()))
            superseded = set()
            for previous_seq in previous_seqs:
                previous = self._active.get(previous_seq)
                if previous is not None and previous.get("type") == order.get("type"):
                    superseded.add(previous_seq)
                    previous_oca = self._oca_key(previous)
                    if order.get("type") == "order" and previous_oca is not None and previous_oca[1] == StrategyOca.cancel and previous_oca != self._oca_key(order):
                        superseded.update(self._by_oca.get(previous_oca, set()))
            self._consume(len(superseded))
            for previous_seq in sorted(superseded):
                previous = self._active[previous_seq]
                self._mark_canceled(previous, timestamp=int(order.get("_submit_time", order.get("time", 0))), canceled_by=order_id)
                self.remove(previous)
        self._active[seq] = order
        if order.get("_market_submission"):
            self._market_seqs.add(seq)
        self._by_id.setdefault(str(order.get("id") or ""), set()).add(seq)
        oca_key = self._oca_key(order)
        if oca_key is not None:
            self._by_oca.setdefault(oca_key, set()).add(seq)
        self._push_thresholds(order)

    def contains(self, order: dict[str, Any]) -> bool:
        seq = int(order.get("_seq", 0))
        return self._active.get(seq) is order

    def validate_entry_direction(self, order: dict[str, Any]) -> None:
        order_id = str(order.get("id") or "")
        _validate_pending_entry_direction(
            (self._active[seq] for seq in self._by_id.get(order_id, set())),
            order_id=order_id, side=str(order.get("side")),
        )

    def remove(self, order: dict[str, Any]) -> bool:
        seq = int(order.get("_seq", 0))
        active = self._active.get(seq)
        if active is not order:
            return False
        self._active.pop(seq, None)
        self._market_seqs.discard(seq)
        self._versions[seq] = self._versions.get(seq, 0) + 1
        self._discard_index(self._by_id, str(order.get("id") or ""), seq)
        oca_key = self._oca_key(order)
        if oca_key is not None:
            self._discard_index(self._by_oca, oca_key, seq)
        return True

    def reindex(self, order: dict[str, Any]) -> None:
        if self.contains(order):
            self._push_thresholds(order)

    def candidates(self, *, high: float, low: float) -> list[dict[str, Any]]:
        candidate_seqs: set[int] = set(self._market_seqs)
        self._collect_candidates(
            self._long_stops,
            threshold=float(high),
            candidate_seqs=candidate_seqs,
        )
        self._collect_candidates(
            self._long_limits,
            threshold=-float(low),
            candidate_seqs=candidate_seqs,
        )
        self._collect_candidates(
            self._short_stops,
            threshold=-float(low),
            candidate_seqs=candidate_seqs,
        )
        self._collect_candidates(
            self._short_limits,
            threshold=float(high),
            candidate_seqs=candidate_seqs,
        )
        return [self._active[seq] for seq in sorted(candidate_seqs) if seq in self._active]

    def entry_admission_state(self, order: dict[str, Any], *, size: float, count: int) -> tuple[float, int]:
        return _pending_market_admission_state(
            (self._active[seq] for seq in sorted(self._market_seqs)),
            order_id=str(order.get("id")) if order.get("_market_submission") else None, size=size, count=count,
        )

    def cancel_market_entry(self, order: dict[str, Any]) -> None:
        seqs = sorted(self._by_id.get(str(order.get("id") or ""), set()) & self._market_seqs)
        matches = [self._active[seq] for seq in seqs if self._active[seq].get("type") == "entry"]
        self._consume(len(matches))
        for previous in matches:
            self._mark_canceled(previous, timestamp=int(order.get("_submit_time", order.get("time", 0))), canceled_by=str(order.get("id")))
            self.remove(previous)

    def cancel_id(
        self,
        order_id: str,
        *,
        timestamp: int,
        canceled_by: str,
    ) -> list[dict[str, Any]]:
        canceled: list[dict[str, Any]] = []
        seqs = sorted(self._by_id.get(str(order_id), set()))
        self._consume(len(seqs))
        for seq in seqs:
            order = self._active.get(seq)
            if order is None:
                continue
            self._mark_canceled(order, timestamp=timestamp, canceled_by=canceled_by)
            self.remove(order)
            canceled.append(order)
        return canceled

    def cancel_all(self, *, timestamp: int, canceled_by: str) -> list[dict[str, Any]]:
        canceled: list[dict[str, Any]] = []
        seqs = sorted(self._active)
        self._consume(len(seqs))
        for seq in seqs:
            order = self._active.get(seq)
            if order is None:
                continue
            self._mark_canceled(order, timestamp=timestamp, canceled_by=canceled_by)
            self.remove(order)
            canceled.append(order)
        return canceled

    def apply_oca_after_fill(self, filled_order: dict[str, Any]) -> None:
        oca_key = self._oca_key(filled_order)
        if oca_key is None:
            return
        oca_type = filled_order.get("_oca_type")
        filled_qty = abs(float(filled_order.get("qty", 0.0)))
        seqs = sorted(self._by_oca.get(oca_key, set()))
        self._consume(len(seqs))
        for seq in seqs:
            order = self._active.get(seq)
            if order is None or order is filled_order:
                continue
            if oca_type == StrategyOca.cancel:
                self._mark_canceled(
                    order,
                    timestamp=int(filled_order.get("time", 0)),
                    canceled_by=str(filled_order.get("id") or ""),
                )
                self.remove(order)
            elif oca_type == StrategyOca.reduce:
                remaining = max(float(order.get("qty", 0.0)) - filled_qty, 0.0)
                order["qty"] = remaining
                if remaining <= 0:
                    self._mark_canceled(
                        order,
                        timestamp=int(filled_order.get("time", 0)),
                        canceled_by=str(filled_order.get("id") or ""),
                    )
                    self.remove(order)

    def _push_thresholds(self, order: dict[str, Any]) -> None:
        seq = int(order.get("_seq", 0))
        version = self._versions.get(seq, 0) + 1
        self._versions[seq] = version
        side = str(order.get("side") or "")
        stop = order.get("_stop")
        limit = order.get("_limit")
        if side == "long":
            if stop is not None:
                heapq.heappush(self._long_stops, (float(stop), seq, version))
            if limit is not None:
                adjusted = float(limit) - self._tick_verify
                heapq.heappush(self._long_limits, (-adjusted, seq, version))
            return
        if stop is not None:
            heapq.heappush(self._short_stops, (-float(stop), seq, version))
        if limit is not None:
            adjusted = float(limit) + self._tick_verify
            heapq.heappush(self._short_limits, (adjusted, seq, version))

    def _collect_candidates(
        self,
        heap: list[tuple[float, int, int]],
        *,
        threshold: float,
        candidate_seqs: set[int],
    ) -> None:
        while heap and heap[0][0] <= threshold:
            _price, seq, version = heapq.heappop(heap)
            if self._versions.get(seq) == version and seq in self._active:
                candidate_seqs.add(seq)

    def _consume(self, count: int) -> None:
        if count > 0 and self._consume_operations is not None:
            self._consume_operations(count)

    @staticmethod
    def _discard_index(index: dict[Any, set[int]], key: Any, seq: int) -> None:
        values = index.get(key)
        if values is None:
            return
        values.discard(seq)
        if not values:
            index.pop(key, None)

    @staticmethod
    def _mark_canceled(order: dict[str, Any], *, timestamp: int, canceled_by: str) -> None:
        order["_canceled"] = True
        order["_canceled_time"] = timestamp
        order["_canceled_by"] = canceled_by

    @staticmethod
    def _oca_key(order: dict[str, Any]) -> tuple[str, str] | None:
        oca_name = str(order.get("_oca_name") or "")
        oca_type = str(order.get("_oca_type") or StrategyOca.none)
        if not oca_name or oca_type == StrategyOca.none:
            return None
        return oca_name, oca_type


def _strategy_lifecycle_events(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for order in _orders_in_lifecycle_order(orders):
        event = _strategy_lifecycle_event(order)
        if event is not None:
            events.append(event)
    return events


def _incremental_strategy_lifecycle_events(
    orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Serialize the scalar engine ledger with the shared lifecycle state machine."""
    events: list[dict[str, Any]] = []
    for order in _orders_in_lifecycle_order(orders):
        state = _order_lifecycle_state(order)
        pending = state["pending"]
        active = state["active"]
        canceled = state["canceled"]
        rejected = state["rejected"]
        event: dict[str, Any] = {
            "id": order.get("id"),
            "from_entry": order.get("from_entry"),
            "type": state["order_type"],
            "status": state["status"],
            "phase": state["phase"],
            "submitted_time": order.get("_submit_time", order.get("time")),
            "filled_time": order.get("time") if active and not canceled else None,
            "canceled_time": order.get("_canceled_time", order.get("time"))
            if canceled
            else None,
            "rejected_time": order.get("_rejected_time") if rejected else None,
            "side": order.get("side"),
            "qty": order.get("qty"),
            "price": order.get("price"),
            "position_after": order.get("position_after"),
        }
        for key in ("reason", "comment", "commission", "oca_name", "oca_type", "canceled"):
            if order.get(key) is not None:
                event[key] = order.get(key)
        for internal_key, public_key in (("_limit", "limit"), ("_stop", "stop")):
            if order.get(internal_key) is not None:
                event[public_key] = order.get(internal_key)
        if order.get("_requested_fill_qty") is not None and (
            active or rejected or (pending and order.get("reason"))
        ):
            event["requested_qty"] = round(float(order.get("_requested_fill_qty", 0.0)), 8)
        if order.get("_filled_qty") is not None and (active or rejected):
            event["filled_qty"] = round(float(order.get("_filled_qty", 0.0)), 8)
        for internal_key, public_key in (
            ("_target_qty", "target_qty"),
            ("_qty_percent", "qty_percent"),
            ("_transaction_qty", "transaction_qty"),
        ):
            if order.get(internal_key) is not None:
                event[public_key] = round(float(order.get(internal_key, 0.0)), 8)
        if order.get("_canceled_by") is not None:
            event["canceled_by"] = order.get("_canceled_by")
        if order.get("_rejected_reason") is not None:
            event["rejected_reason"] = order.get("_rejected_reason")
        events.append(
            {
                key: value
                for key, value in event.items()
                if value is not None
                or key in {"price", "filled_time", "canceled_time", "rejected_time"}
            }
        )
    return events


def _orders_in_replay_order(
    orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _orders_in_key_order(
        orders,
        # Fills rewrite time for reporting. Replaying must retain command order,
        # including when a later call adds no events at all.
        key=lambda item: (
            item.get("_submit_time", item.get("time", 0)),
            item.get("_seq", 0),
        ),
    )


def _orders_in_lifecycle_order(
    orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _orders_in_key_order(
        orders,
        key=lambda item: (
            item.get("_submit_time", item.get("time", 0)),
            item.get("_seq", 0),
        ),
    )


def _orders_in_sequence_order(
    orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _orders_in_key_order(
        orders,
        key=lambda item: item.get("_seq", 0),
    )


def _orders_in_key_order(
    orders: list[dict[str, Any]],
    *,
    key: Callable[[dict[str, Any]], Any],
) -> list[dict[str, Any]]:
    ordered = list(orders)
    if len(ordered) < 2:
        return ordered
    previous = key(ordered[0])
    for item in ordered[1:]:
        current = key(item)
        if current < previous:
            ordered.sort(key=key)
            break
        previous = current
    return ordered


def _strategy_lifecycle_event(order: dict[str, Any]) -> dict[str, Any] | None:
    state = _order_lifecycle_state(order)
    order_type = state["order_type"]
    active = state["active"]
    canceled = state["canceled"]
    rejected = state["rejected"]
    pending_submission = state["pending"]

    if not active and not canceled and not rejected and not pending_submission:
        return None

    status = state["status"]
    phase = state["phase"]
    event: dict[str, Any] = {
        "id": order.get("id"),
        "type": order_type,
        "status": status,
        "phase": phase,
        "submitted_time": order.get("_submit_time", order.get("time")),
        "filled_time": order.get("time") if status == "filled" else None,
        "canceled_time": order.get("_canceled_time")
        if status == "canceled" and pending_submission
        else order.get("time")
        if status == "canceled"
        else None,
        "rejected_time": order.get("_rejected_time") if status == "rejected" else None,
        "side": order.get("side"),
        "qty": order.get("qty"),
        "price": order.get("price"),
        "position_after": order.get("position_after"),
    }
    optional_fields = (
        "from_entry",
        "reason",
        "comment",
        "canceled",
        "commission",
        "oca_name",
        "oca_type",
    )
    for key in optional_fields:
        if key in order:
            event[key] = order[key]
    for internal_key, public_key in (("_limit", "limit"), ("_stop", "stop")):
        if order.get(internal_key) is not None:
            event[public_key] = order.get(internal_key)
    if order.get("_requested_fill_qty") is not None:
        event["requested_qty"] = round(float(order.get("_requested_fill_qty", 0.0)), 8)
    if order.get("_filled_qty") is not None:
        event["filled_qty"] = round(float(order.get("_filled_qty", 0.0)), 8)
    if order.get("_target_qty") is not None:
        event["target_qty"] = round(float(order.get("_target_qty", 0.0)), 8)
    if order.get("_qty_percent") is not None:
        event["qty_percent"] = round(float(order.get("_qty_percent", 0.0)), 8)
    if order.get("_transaction_qty") is not None:
        event["transaction_qty"] = round(float(order.get("_transaction_qty", 0.0)), 8)
    if order.get("_canceled_by"):
        event["canceled_by"] = order.get("_canceled_by")
    if order.get("_rejected_reason"):
        event["rejected_reason"] = order.get("_rejected_reason")
    return event


def _order_lifecycle_state(order: dict[str, Any]) -> dict[str, Any]:
    """Return the shared batch/incremental order lifecycle state machine view."""
    order_type = str(order.get("type") or "")
    active = bool(order.get("_active", True))
    canceled = bool(order.get("_canceled")) or (
        order_type in {"cancel", "cancel_all"} and active
    )
    rejected = bool(order.get("_rejected_reason"))
    pending_submission = bool(order.get("_pending_submission")) or (
        order_type in {"entry", "order"} and _is_pending_submission(order)
    )
    status = _strategy_lifecycle_status(
        order_type=order_type,
        active=active,
        canceled=canceled,
        rejected=rejected,
        pending_submission=pending_submission,
    )
    phase = _strategy_lifecycle_phase(
        order_type=order_type,
        status=status,
        pending_submission=pending_submission,
    )
    if order.get("_market_submission") and status in {"filled", "rejected"}:
        phase = "market_fill" if status == "filled" else "rejected"
    return {
        "order_type": order_type,
        "active": active,
        "canceled": canceled,
        "rejected": rejected,
        "pending": pending_submission,
        "status": status,
        "phase": phase,
    }


def _strategy_lifecycle_status(
    *,
    order_type: str,
    active: bool,
    canceled: bool,
    rejected: bool,
    pending_submission: bool,
) -> str:
    if canceled or order_type in {"cancel", "cancel_all"} and active:
        return "canceled"
    if rejected:
        return "rejected"
    if active:
        return "filled"
    if pending_submission:
        return "pending"
    return "submitted"


def _strategy_lifecycle_phase(
    *,
    order_type: str,
    status: str,
    pending_submission: bool,
) -> str:
    if order_type in {"cancel", "cancel_all"}:
        return "cancel"
    if status == "canceled" and pending_submission:
        return "pending_canceled"
    if status == "rejected":
        return "pending_rejected" if pending_submission else "rejected"
    if status == "pending":
        return "pending"
    if pending_submission:
        return "pending_fill"
    if order_type == "exit":
        return "exit_fill"
    if order_type == "close":
        return "close_fill"
    if order_type == "close_all":
        return "close_all_fill"
    if order_type in {"entry", "order"}:
        return "market_fill"
    return order_type or status


def _reject_order(order: dict[str, Any], *, timestamp: int, reason: str) -> None:
    if order.get("type") in {"entry", "order"}:
        order.setdefault(
            "_requested_fill_qty",
            float(order.get("_original_qty", order.get("qty", 0.0))),
        )
        order.setdefault("_filled_qty", 0.0)
    order["_rejected_reason"] = reason
    order["_rejected_time"] = timestamp


def _stop_limit_trigger(
    *, order_state: dict[str, Any], side: str, open_price: float, high: float,
    low: float, close_price: float, stop: float, limit: float, tick_verify: float,
    intrabar_path: str,
) -> tuple[str, float] | None:
    """Activate the stop, then traverse only the remaining limit-price path."""
    if intrabar_path == StrategyIntrabarPath.open_high_low_close:
        high_first = True
    elif intrabar_path == StrategyIntrabarPath.open_low_high_close:
        high_first = False
    else:
        high_first = abs(high - open_price) < abs(open_price - low)
    points = [open_price, high, low, close_price] if high_first else [open_price, low, high, close_price]
    long = side == "long"
    threshold = limit - tick_verify if long else limit + tick_verify
    active = bool(order_state.get("_stop_limit_activated", False))
    for index, point in enumerate(points):
        if not active:
            stop_hit = point >= stop if long else point <= stop
            if not stop_hit:
                continue
            active = True
            order_state["_stop_limit_activated"] = True
            # A gap activates at the open; an intrabar crossing activates at
            # the stop, so prices visited before that crossing are excluded.
            point = point if index == 0 else stop
        limit_hit = point <= threshold if long else point >= threshold
        if limit_hit:
            return "limit", float(point)
        if index + 1 < len(points):
            endpoint = points[index + 1]
            crossed = endpoint <= threshold if long else endpoint >= threshold
            if crossed:
                return "limit", float(limit)
    return None


def _pending_trigger(
    *,
    side: str,
    open_price: float,
    high: float,
    low: float,
    limit: float | None,
    stop: float | None,
    tick_verify: float = 0.0,
    same_bar_fill_priority: str = StrategySameBarPriority.stop_first,
    intrabar_path: str = StrategyIntrabarPath.same_bar_priority,
    order_state: dict[str, Any] | None = None,
    close_price: float | None = None,
) -> tuple[str | None, float] | None:
    if order_state is not None and order_state.get("_market_submission"):
        return None, float(order_state.get("_base_price", open_price))
    if stop is not None and limit is not None:
        return _stop_limit_trigger(
            order_state={} if order_state is None else order_state,
            side=side, open_price=open_price, high=high, low=low,
            close_price=open_price if close_price is None else close_price,
            stop=float(stop), limit=float(limit), tick_verify=tick_verify, intrabar_path=intrabar_path,
        )
    if side == "long":
        stop_hit = stop is not None and high >= stop
        limit_hit = limit is not None and low <= limit - tick_verify
        if stop_hit:
            return "stop", _pending_fill_price(
                side=side,
                reason="stop",
                trigger_price=float(stop),
                open_price=open_price,
            )
        if limit_hit:
            return "limit", _pending_fill_price(
                side=side,
                reason="limit",
                trigger_price=float(limit),
                open_price=open_price,
            )
        return None
    stop_hit = stop is not None and low <= stop
    limit_hit = limit is not None and high >= limit + tick_verify
    if stop_hit:
        return "stop", _pending_fill_price(
            side=side,
            reason="stop",
            trigger_price=float(stop),
            open_price=open_price,
        )
    if limit_hit:
        return "limit", _pending_fill_price(
            side=side,
            reason="limit",
            trigger_price=float(limit),
            open_price=open_price,
        )
    return None


def _pending_fill_price(
    *,
    side: str,
    reason: str,
    trigger_price: float,
    open_price: float,
) -> float:
    trigger = float(trigger_price)
    opened = float(open_price)
    if side == "long":
        return max(trigger, opened) if reason == "stop" else min(trigger, opened)
    return min(trigger, opened) if reason == "stop" else max(trigger, opened)


def _exit_fill_price(
    *,
    current_position: float,
    reason: str,
    trigger_price: float,
    open_price: float,
) -> float:
    trigger = float(trigger_price)
    opened = float(open_price)
    if current_position > 0:
        return min(trigger, opened) if reason == "stop" else max(trigger, opened)
    return max(trigger, opened) if reason == "stop" else min(trigger, opened)


def _same_bar_trigger(
    *,
    stop: float | None,
    limit: float | None,
    stop_path: str,
    limit_path: str,
    same_bar_fill_priority: str,
    intrabar_path: str,
) -> tuple[str, float]:
    if intrabar_path == StrategyIntrabarPath.open_high_low_close:
        if stop_path == "high" and limit_path == "low":
            return "stop", float(stop)
        if limit_path == "high" and stop_path == "low":
            return "limit", float(limit)
    if intrabar_path == StrategyIntrabarPath.open_low_high_close:
        if stop_path == "low" and limit_path == "high":
            return "stop", float(stop)
        if limit_path == "low" and stop_path == "high":
            return "limit", float(limit)
    if same_bar_fill_priority == StrategySameBarPriority.limit_first:
        return "limit", float(limit)
    return "stop", float(stop)


def _normalize_same_bar_fill_priority(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "stop": StrategySameBarPriority.stop_first,
        "stop_first": StrategySameBarPriority.stop_first,
        "stop-first": StrategySameBarPriority.stop_first,
        "limit": StrategySameBarPriority.limit_first,
        "limit_first": StrategySameBarPriority.limit_first,
        "limit-first": StrategySameBarPriority.limit_first,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(
        "same_bar_fill_priority must be strategy.same_bar.stop_first or "
        "strategy.same_bar.limit_first"
    )


def _normalize_intrabar_path(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "same_bar_priority": StrategyIntrabarPath.same_bar_priority,
        "same-bar-priority": StrategyIntrabarPath.same_bar_priority,
        "priority": StrategyIntrabarPath.same_bar_priority,
        "open_high_low_close": StrategyIntrabarPath.open_high_low_close,
        "ohlc": StrategyIntrabarPath.open_high_low_close,
        "high_low": StrategyIntrabarPath.open_high_low_close,
        "open-high-low-close": StrategyIntrabarPath.open_high_low_close,
        "open_low_high_close": StrategyIntrabarPath.open_low_high_close,
        "open-low-high-close": StrategyIntrabarPath.open_low_high_close,
        "olhc": StrategyIntrabarPath.open_low_high_close,
        "low_high": StrategyIntrabarPath.open_low_high_close,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(
        "intrabar_path must be strategy.intrabar.same_bar_priority, "
        "strategy.intrabar.open_high_low_close, or "
        "strategy.intrabar.open_low_high_close"
    )


def _normalize_oca_type(value: str | None) -> str:
    if value is None:
        return StrategyOca.none
    normalized = str(value or "").lower()
    if normalized in {"cancel", "strategy.oca.cancel"}:
        return StrategyOca.cancel
    if normalized in {"reduce", "strategy.oca.reduce"}:
        return StrategyOca.reduce
    if normalized in {"none", "", "strategy.oca.none"}:
        return StrategyOca.none
    raise ValueError(
        "oca_type must be strategy.oca.none, strategy.oca.cancel, or strategy.oca.reduce"
    )


def _apply_oca_after_fill(
    filled_order: dict[str, Any],
    pending_orders: list[dict[str, Any]],
) -> None:
    oca_type = filled_order.get("_oca_type")
    oca_name = str(filled_order.get("_oca_name") or "")
    if not oca_name or oca_type == StrategyOca.none:
        return
    filled_qty = abs(float(filled_order.get("qty", 0.0)))
    for order in pending_orders:
        if order is filled_order:
            continue
        if order.get("_oca_name") != oca_name or order.get("_oca_type") != oca_type:
            continue
        if oca_type == StrategyOca.cancel:
            order["_canceled"] = True
            order["_canceled_time"] = filled_order.get("time")
            order["_canceled_by"] = filled_order.get("id")
        elif oca_type == StrategyOca.reduce:
            remaining = max(float(order.get("qty", 0.0)) - filled_qty, 0.0)
            order["qty"] = remaining
            if remaining <= 0:
                order["_canceled"] = True
                order["_canceled_time"] = filled_order.get("time")
                order["_canceled_by"] = filled_order.get("id")
