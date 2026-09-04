"""Step-by-step technical analysis helpers for incremental sessions."""
from __future__ import annotations

import math
from collections import deque
from typing import Any

from ..ta_kernels import _normalize_pivot_type, _pivot_level_values
from ..utils import require_positive_period
from ..values import is_condition_true
from .limits import IncrementalLimits, _LimitTracker


class _StepSMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float | None] = deque()
        self.sum = 0.0
        self.valid_count = 0

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        self.window.append(number)
        if number is not None:
            self.sum += number
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            if removed is not None:
                self.sum -= removed
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None
        return self.sum / self.period


class _StepEMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.alpha = 2.0 / (self.period + 1)
        self.count = 0
        self.seed_sum = 0.0
        self.seed_count = 0
        self.ema: float | None = None

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        if self.ema is not None:
            if number is None:
                return self.ema
            self.ema = self.alpha * number + (1 - self.alpha) * self.ema
            return self.ema

        self.count += 1
        if number is not None:
            self.seed_sum += number
            self.seed_count += 1
        if self.count < self.period:
            return None
        if self.seed_count == 0:
            return self.ema
        self.ema = self.seed_sum / self.seed_count
        return self.ema


class _StepRMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.alpha = 1.0 / self.period
        self.seed_sum = 0.0
        self.seed_count = 0
        self.value: float | None = None

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        if number is None:
            return self.value
        if self.value is None:
            self.seed_sum += number
            self.seed_count += 1
            if self.seed_count < self.period:
                return None
            self.value = self.seed_sum / self.period
            return self.value
        self.value = self.alpha * number + (1.0 - self.alpha) * self.value
        return self.value


class _StepWMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float | None] = deque()
        self.simple_sum = 0.0
        self.weighted_sum = 0.0
        self.valid_count = 0
        self.denominator = self.period * (self.period + 1) / 2.0

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        numeric = number or 0.0
        next_weight = len(self.window) + 1
        self.window.append(number)
        self.simple_sum += numeric
        self.weighted_sum += next_weight * numeric
        if number is not None:
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            self.weighted_sum -= self.simple_sum
            self.simple_sum -= removed or 0.0
            if removed is not None:
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None
        return self.weighted_sum / self.denominator


class _StepVWMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[tuple[float | None, float | None]] = deque()
        self.numerator = 0.0
        self.denominator = 0.0

    def update(self, value: Any, volume: Any) -> float | None:
        number = _number_or_none(value)
        weight = _number_or_none(volume)
        self.window.append((number, weight))
        if number is not None and weight is not None:
            self.numerator += number * weight
        if weight is not None:
            self.denominator += weight
        if len(self.window) > self.period:
            removed_value, removed_weight = self.window.popleft()
            if removed_value is not None and removed_weight is not None:
                self.numerator -= removed_value * removed_weight
            if removed_weight is not None:
                self.denominator -= removed_weight
        if len(self.window) < self.period or self.denominator <= 0.0:
            return None
        return self.numerator / self.denominator


class _StepVariance:
    def __init__(self, period: int, *, biased: bool = True) -> None:
        self.period = max(int(period), 1)
        self.biased = bool(biased)
        self.window: deque[float | None] = deque()
        self.sum = 0.0
        self.sumsq = 0.0
        self.valid_count = 0

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        self.window.append(number)
        if number is not None:
            self.sum += number
            self.sumsq += number * number
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            if removed is not None:
                self.sum -= removed
                self.sumsq -= removed * removed
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None
        denominator = self.period if self.biased else self.period - 1
        if denominator <= 0:
            return None
        centered = max(self.sumsq - self.sum * self.sum / self.period, 0.0)
        return centered / denominator


class _StepStdev(_StepVariance):
    def update(self, value: Any) -> float | None:
        variance = super().update(value)
        return None if variance is None else math.sqrt(variance)


class _StepChange:
    def __init__(self, period: int = 1) -> None:
        self.period = require_positive_period(period)
        self.window: deque[float | None] = deque(maxlen=self.period + 1)

    def update(self, value: Any) -> float | None:
        current = _number_or_none(value)
        self.window.append(current)
        if len(self.window) <= self.period:
            return None
        previous = self.window[0]
        return None if current is None or previous is None else current - previous


class _StepExtremeBars:
    def __init__(self, period: int, *, highest: bool) -> None:
        self.period = max(int(period), 1)
        self.highest = bool(highest)
        self.index = -1
        self.window: deque[tuple[int, float]] = deque()

    def update(self, value: Any) -> float | None:
        self.index += 1
        expiry = self.index - self.period
        while self.window and self.window[0][0] <= expiry:
            self.window.popleft()
        current = _number_or_none(value)
        if current is not None:
            if self.highest:
                while self.window and self.window[-1][1] <= current:
                    self.window.pop()
            else:
                while self.window and self.window[-1][1] >= current:
                    self.window.pop()
            self.window.append((self.index, current))
        return None if not self.window else float(self.window[0][0] - self.index)


class _StepPivot:
    """Causal pivot detector returning the value on its confirmation bar."""

    def __init__(self, left: int, right: int, *, highest: bool) -> None:
        self.left = max(int(left), 0)
        self.right = max(int(right), 0)
        self.highest = bool(highest)
        self.window_size = self.left + self.right + 1
        self.window: deque[float | None] = deque(maxlen=self.window_size)

    @property
    def confirmation_offset(self) -> int:
        return -self.right

    def update(self, value: Any) -> float | None:
        self.window.append(_number_or_none(value))
        if len(self.window) <= self.right:
            return None
        values = list(self.window)
        center = values[len(values) - self.right - 1]
        if center is None:
            return None
        valid = [item for item in values if item is not None]
        extreme = max(valid) if self.highest else min(valid)
        return center if center == extreme and valid.count(extreme) == 1 else None


class _StepTrueRange:
    def __init__(self) -> None:
        self.previous_close: float | None = None

    def update(self, bar_or_high: Any, low: Any = None, close: Any = None) -> float | None:
        if low is None and close is None:
            high = _number_or_none(getattr(bar_or_high, "high"))
            low_value = _number_or_none(getattr(bar_or_high, "low"))
            close_value = _number_or_none(getattr(bar_or_high, "close"))
        else:
            high = _number_or_none(bar_or_high)
            low_value = _number_or_none(low)
            close_value = _number_or_none(close)
        if high is None or low_value is None:
            result = None
        elif self.previous_close is None:
            result = high - low_value
        else:
            result = max(
                high - low_value,
                abs(high - self.previous_close),
                abs(low_value - self.previous_close),
            )
        self.previous_close = close_value
        return result


class _StepCum:
    def __init__(self) -> None:
        self.total = 0.0

    def update(self, value: Any) -> float:
        current = _number_or_none(value)
        if current is not None:
            self.total += current
        return self.total


class _StepSWMA:
    def __init__(self) -> None:
        self.window: deque[float | None] = deque(maxlen=4)

    def update(self, value: Any) -> float | None:
        self.window.append(_number_or_none(value))
        if len(self.window) < 4 or any(item is None for item in self.window):
            return None
        a, b, c, d = self.window
        return (float(a) + 2.0 * float(b) + 2.0 * float(c) + float(d)) / 6.0


class _StepALMA:
    def __init__(self, period: int, offset: float = 0.85, sigma: float = 6.0) -> None:
        self.period = max(int(period), 1)
        if float(sigma) == 0.0:
            raise ValueError("ctx.ta.alma() sigma must be non-zero")
        midpoint = float(offset) * (self.period - 1)
        width = self.period / float(sigma)
        raw = [math.exp(-((index - midpoint) ** 2) / (2.0 * width * width)) for index in range(self.period)]
        total = sum(raw)
        self.weights = tuple(weight / total for weight in raw)
        self.window: deque[float | None] = deque(maxlen=self.period)

    def update(self, value: Any) -> float | None:
        self.window.append(_number_or_none(value))
        if len(self.window) < self.period or any(item is None for item in self.window):
            return None
        return sum(float(item) * weight for item, weight in zip(self.window, self.weights))


class _StepDev:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float | None] = deque(maxlen=self.period)

    def update(self, value: Any) -> float | None:
        self.window.append(_number_or_none(value))
        if len(self.window) < self.period or any(item is None for item in self.window):
            return None
        values = [float(item) for item in self.window]
        mean = sum(values) / self.period
        return sum(abs(item - mean) for item in values) / self.period


class _StepBOLL:
    def __init__(self, period: int, multiplier: float = 2.0) -> None:
        self.period = max(int(period), 1)
        self.multiplier = float(multiplier)
        self.window: deque[float | None] = deque()
        self.sum = 0.0
        self.sumsq = 0.0
        self.valid_count = 0

    def update(self, value: Any) -> tuple[float | None, float | None, float | None]:
        number = _number_or_none(value)
        self.window.append(number)
        if number is not None:
            self.sum += number
            self.sumsq += number * number
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            if removed is not None:
                self.sum -= removed
                self.sumsq -= removed * removed
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None, None, None
        mid = self.sum / self.period
        variance = max(self.sumsq / self.period - mid * mid, 0.0)
        std = math.sqrt(variance)
        return mid + self.multiplier * std, mid, mid - self.multiplier * std


class _StepBB(_StepBOLL):
    def update(self, value: Any) -> tuple[float | None, float | None, float | None]:
        upper, middle, lower = super().update(value)
        return middle, upper, lower


class _StepMACD:
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = _StepEMA(max(int(fast), 1))
        self.slow = _StepEMA(max(int(slow), 1))
        self.signal = _StepEMA(max(int(signal), 1))

    def update(self, value: Any) -> tuple[float | None, float | None, float | None]:
        fast_value = self.fast.update(value)
        slow_value = self.slow.update(value)
        if fast_value is None or slow_value is None:
            return None, None, None
        dif = fast_value - slow_value
        dea = self.signal.update(dif)
        hist = dif - dea if dea is not None else None
        return dif, dea, hist


class _StepRSI:
    def __init__(self, period: int = 14) -> None:
        self.period = max(int(period), 1)
        self.prev: float | None = None
        self.count = 0
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.avg_gain: float | None = None
        self.avg_loss: float | None = None

    def update(self, value: Any) -> float | None:
        current = _number_or_none(value)
        if current is None:
            self.prev = None
            return self._current_value()
        if self.prev is None:
            self.prev = current
            return self._current_value()
        delta = current - self.prev
        self.prev = current
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        if self.avg_gain is None or self.avg_loss is None:
            self.count += 1
            self.gain_sum += gain
            self.loss_sum += loss
            if self.count < self.period:
                return None
            self.avg_gain = self.gain_sum / self.period
            self.avg_loss = self.loss_sum / self.period
        else:
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        return _rsi_from_avgs(self.avg_gain, self.avg_loss)

    def _current_value(self) -> float | None:
        if self.avg_gain is None or self.avg_loss is None:
            return None
        return _rsi_from_avgs(self.avg_gain, self.avg_loss)


class _StepATR:
    def __init__(self, period: int = 14) -> None:
        self.period = max(int(period), 1)
        self.prev_close: float | None = None
        self.count = 0
        self.tr_sum = 0.0
        self.atr: float | None = None

    def update(self, bar_or_high: Any, low: Any = None, close: Any = None) -> float | None:
        if low is None and close is None:
            high = _number_or_none(getattr(bar_or_high, "high"))
            low = _number_or_none(getattr(bar_or_high, "low"))
            close = _number_or_none(getattr(bar_or_high, "close"))
        else:
            high = _number_or_none(bar_or_high)
            low = _number_or_none(low)
            close = _number_or_none(close)

        if high is None or low is None:
            self.prev_close = close
            return self.atr

        if self.prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
        self.prev_close = close

        if self.atr is None:
            self.count += 1
            self.tr_sum += tr
            if self.count < self.period:
                return None
            self.atr = self.tr_sum / self.period
        else:
            self.atr = (self.atr * (self.period - 1) + tr) / self.period
        return self.atr


class _StepMonotonic:
    def __init__(self, period: int, *, highest: bool) -> None:
        self.period = max(int(period), 1)
        self.highest = highest
        self.index = -1
        self.window: deque[tuple[int, float]] = deque()

    def update(self, value: Any) -> float | None:
        self.index += 1
        expiry = self.index - self.period
        while self.window and self.window[0][0] <= expiry:
            self.window.popleft()
        number = _number_or_none(value)
        if number is not None:
            if self.highest:
                while self.window and self.window[-1][1] <= number:
                    self.window.pop()
            else:
                while self.window and self.window[-1][1] >= number:
                    self.window.pop()
            self.window.append((self.index, number))
        if self.index + 1 < self.period:
            return None
        return self.window[0][1] if self.window else None


class _StepStoch:
    def __init__(self, period: int) -> None:
        self.highest = _StepMonotonic(period, highest=True)
        self.lowest = _StepMonotonic(period, highest=False)

    def update(self, source: Any, high: Any, low: Any) -> float | None:
        current = _number_or_none(source)
        highest = self.highest.update(high)
        lowest = self.lowest.update(low)
        if highest is None and self.highest.window:
            highest = self.highest.window[0][1]
        if lowest is None and self.lowest.window:
            lowest = self.lowest.window[0][1]
        if current is None or highest is None or lowest is None:
            return None
        spread = highest - lowest
        return 50.0 if spread == 0.0 else 100.0 * (current - lowest) / spread


class _StepCCI:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float | None] = deque()

    def update(self, source: Any) -> float | None:
        current = _number_or_none(source)
        self.window.append(current)
        if len(self.window) > self.period:
            self.window.popleft()
        if len(self.window) < self.period or any(value is None for value in self.window):
            return None
        values = [float(value) for value in self.window if value is not None]
        average = sum(values) / self.period
        deviation = sum(abs(value - average) for value in values) / self.period
        if deviation == 0.0:
            return 0.0
        return (float(current) - average) / (0.015 * deviation)


class _StepHMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.fast = _StepWMA(max(int(self.period / 2), 1))
        self.slow = _StepWMA(self.period)
        self.result = _StepWMA(max(int(math.sqrt(self.period)), 1))

    def update(self, value: Any) -> float | None:
        fast = self.fast.update(value)
        slow = self.slow.update(value)
        combined = None if fast is None or slow is None else 2.0 * fast - slow
        return self.result.update(combined)


class _StepBarsSince:
    def __init__(self) -> None:
        self.index = -1
        self.last_true: int | None = None

    def update(self, condition: Any) -> float | None:
        self.index += 1
        if is_condition_true(condition):
            self.last_true = self.index
        return None if self.last_true is None else float(self.index - self.last_true)


class _StepValueWhen:
    def __init__(self, occurrence: int = 0) -> None:
        self.occurrence = max(int(occurrence), 0)
        self.values: deque[Any] = deque(maxlen=self.occurrence + 1)

    def update(self, condition: Any, value: Any) -> Any:
        if is_condition_true(condition):
            self.values.append(value)
        if len(self.values) <= self.occurrence:
            return None
        return self.values[-(self.occurrence + 1)]


class _StepCross:
    def __init__(self, direction: str) -> None:
        self.direction = direction
        self.previous_a: float | None = None
        self.previous_b: float | None = None

    def update(self, a: Any, b: Any) -> bool:
        current_a = _number_or_none(a)
        current_b = _number_or_none(b)
        crossed = False
        if (
            current_a is not None
            and current_b is not None
            and self.previous_a is not None
            and self.previous_b is not None
        ):
            over = current_a > current_b and self.previous_a <= self.previous_b
            under = current_a < current_b and self.previous_a >= self.previous_b
            crossed = over if self.direction == "over" else under if self.direction == "under" else over or under
        self.previous_a = current_a
        self.previous_b = current_b
        return crossed


class _StepVWAP:
    def __init__(self) -> None:
        self.running = False
        self.volume_sum = 0.0
        self.weighted_sum = 0.0
        self.weighted_square_sum = 0.0

    def update(
        self,
        source: Any,
        volume: Any,
        *,
        anchor: Any = False,
        stdev_mult: Any = None,
    ) -> float | None | tuple[float | None, float | None, float | None]:
        if bool(anchor):
            self.running = True
            self.volume_sum = 0.0
            self.weighted_sum = 0.0
            self.weighted_square_sum = 0.0
        if not self.running:
            empty = None
            return (empty, empty, empty) if stdev_mult is not None else empty
        price = _number_or_none(source)
        weight = _number_or_none(volume)
        if price is not None and weight is not None:
            self.volume_sum += weight
            self.weighted_sum += price * weight
            self.weighted_square_sum += price * price * weight
        if self.volume_sum == 0.0:
            empty = None
            return (empty, empty, empty) if stdev_mult is not None else empty
        value = self.weighted_sum / self.volume_sum
        if stdev_mult is None:
            return value
        multiplier = _number_or_none(stdev_mult)
        if multiplier is None:
            return value, None, None
        variance = max(self.weighted_square_sum / self.volume_sum - value * value, 0.0)
        deviation = math.sqrt(variance) * multiplier
        return value, value + deviation, value - deviation


class _StepDMI:
    def __init__(self, period: int = 14, adx_period: int = 14) -> None:
        self.atr = _StepATR(period)
        self.plus = _StepRMA(period)
        self.minus = _StepRMA(period)
        self.adx = _StepRMA(adx_period)
        self.previous_high: float | None = None
        self.previous_low: float | None = None
        self.last_plus_di: float | None = None
        self.last_minus_di: float | None = None

    def update(
        self,
        bar_or_high: Any,
        low: Any = None,
        close: Any = None,
    ) -> tuple[float | None, float | None, float | None]:
        if low is None and close is None:
            high = _number_or_none(getattr(bar_or_high, "high"))
            low_value = _number_or_none(getattr(bar_or_high, "low"))
            close_value = _number_or_none(getattr(bar_or_high, "close"))
        else:
            high = _number_or_none(bar_or_high)
            low_value = _number_or_none(low)
            close_value = _number_or_none(close)
        if high is None or low_value is None:
            atr = self.atr.update(high, low_value, close_value)
            return self.last_plus_di, self.last_minus_di, self.adx.update(None)
        up_move = None if self.previous_high is None else high - self.previous_high
        down_move = None if self.previous_low is None else self.previous_low - low_value
        plus_dm = (
            None
            if up_move is None or down_move is None
            else up_move
            if up_move > down_move and up_move > 0.0
            else 0.0
        )
        minus_dm = (
            None
            if up_move is None or down_move is None
            else down_move
            if down_move > up_move and down_move > 0.0
            else 0.0
        )
        self.previous_high = high
        self.previous_low = low_value
        atr = self.atr.update(high, low_value, close_value)
        plus_smoothed = self.plus.update(plus_dm)
        minus_smoothed = self.minus.update(minus_dm)
        if atr not in {None, 0.0} and plus_smoothed is not None:
            self.last_plus_di = 100.0 * plus_smoothed / atr
        if atr not in {None, 0.0} and minus_smoothed is not None:
            self.last_minus_di = 100.0 * minus_smoothed / atr
        dx = None
        if self.last_plus_di is not None and self.last_minus_di is not None:
            total = self.last_plus_di + self.last_minus_di
            dx = abs(self.last_plus_di - self.last_minus_di) / (1.0 if total == 0.0 else total)
        adx = self.adx.update(dx)
        return self.last_plus_di, self.last_minus_di, None if adx is None else 100.0 * adx


class _StepADX(_StepDMI):
    def update(self, bar_or_high: Any, low: Any = None, close: Any = None) -> float | None:
        return super().update(bar_or_high, low, close)[2]


class _StepSAR:
    def __init__(self, start: float, increment: float, maximum: float) -> None:
        self.start = float(start)
        self.increment = float(increment)
        self.maximum = float(maximum)
        self.index = -1
        self.sar: float | None = None
        self.extreme: float | None = None
        self.acceleration: float | None = None
        self.is_below = False
        self.previous_close: float | None = None
        self.previous_highs: deque[float | None] = deque(maxlen=2)
        self.previous_lows: deque[float | None] = deque(maxlen=2)

    def update(self, bar_or_high: Any, low: Any = None, close: Any = None) -> float | None:
        if low is None and close is None:
            high = _number_or_none(getattr(bar_or_high, "high"))
            low_value = _number_or_none(getattr(bar_or_high, "low"))
            close_value = _number_or_none(getattr(bar_or_high, "close"))
        else:
            high = _number_or_none(bar_or_high)
            low_value = _number_or_none(low)
            close_value = _number_or_none(close)
        self.index += 1
        if high is None or low_value is None or close_value is None:
            self.sar = None
            self.extreme = None
            self.acceleration = None
            self.previous_close = close_value
            self.previous_highs.append(high)
            self.previous_lows.append(low_value)
            return None
        first_trend_bar = False
        if self.sar is None and self.previous_close is not None and self.previous_highs and self.previous_lows:
            if close_value > self.previous_close:
                self.is_below = True
                self.extreme = high
                self.sar = self.previous_lows[-1]
            else:
                self.is_below = False
                self.extreme = low_value
                self.sar = self.previous_highs[-1]
            first_trend_bar = True
            self.acceleration = self.start
        elif self.sar is not None and self.extreme is not None and self.acceleration is not None:
            self.sar = self.sar + self.acceleration * (self.extreme - self.sar)
            if self.is_below and self.sar > low_value:
                first_trend_bar = True
                self.is_below = False
                self.sar = max(high, self.extreme)
                self.extreme = low_value
                self.acceleration = self.start
            elif not self.is_below and self.sar < high:
                first_trend_bar = True
                self.is_below = True
                self.sar = min(low_value, self.extreme)
                self.extreme = high
                self.acceleration = self.start
            if not first_trend_bar:
                if self.is_below and high > self.extreme:
                    self.extreme = high
                    self.acceleration = min(self.acceleration + self.increment, self.maximum)
                elif not self.is_below and low_value < self.extreme:
                    self.extreme = low_value
                    self.acceleration = min(self.acceleration + self.increment, self.maximum)
            if self.is_below:
                for previous in self.previous_lows:
                    if previous is not None:
                        self.sar = min(self.sar, previous)
            else:
                for previous in self.previous_highs:
                    if previous is not None:
                        self.sar = max(self.sar, previous)
        result = self.sar
        self.previous_close = close_value
        self.previous_highs.append(high)
        self.previous_lows.append(low_value)
        return result


class _StepMFI:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.previous_source: float | None = None
        self.positive: deque[float] = deque()
        self.negative: deque[float] = deque()
        self.positive_sum = 0.0
        self.negative_sum = 0.0

    def update(self, source: Any, volume: Any) -> float | None:
        price = _number_or_none(source)
        weight = _number_or_none(volume)
        raw = 0.0 if price is None or weight is None else price * weight
        positive = raw if self.previous_source is not None and price is not None and price > self.previous_source else 0.0
        negative = raw if self.previous_source is not None and price is not None and price < self.previous_source else 0.0
        self.previous_source = price
        self.positive.append(positive)
        self.negative.append(negative)
        self.positive_sum += positive
        self.negative_sum += negative
        if len(self.positive) > self.period:
            self.positive_sum -= self.positive.popleft()
            self.negative_sum -= self.negative.popleft()
        if len(self.positive) < self.period:
            return 100.0
        if self.negative_sum == 0.0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + self.positive_sum / self.negative_sum)


class _StepSupertrend:
    def __init__(self, factor: float, atr_period: int) -> None:
        self.factor = float(factor)
        self.atr = _StepATR(atr_period)
        self.previous_atr: float | None = None
        self.previous_close: float | None = None
        self.previous_upper = 0.0
        self.previous_lower = 0.0
        self.previous_supertrend: float | None = 0.0
        self.index = -1

    def update(
        self,
        bar_or_high: Any,
        low: Any = None,
        close: Any = None,
    ) -> tuple[float | None, float | None]:
        if low is None and close is None:
            high = _number_or_none(getattr(bar_or_high, "high"))
            low_value = _number_or_none(getattr(bar_or_high, "low"))
            close_value = _number_or_none(getattr(bar_or_high, "close"))
        else:
            high = _number_or_none(bar_or_high)
            low_value = _number_or_none(low)
            close_value = _number_or_none(close)
        self.index += 1
        atr = self.atr.update(high, low_value, close_value)
        if high is None or low_value is None or close_value is None or atr is None:
            self.previous_atr = atr
            self.previous_close = close_value
            self.previous_upper = 0.0
            self.previous_lower = 0.0
            return (0.0 if self.index == 0 else None), 1.0

        midpoint = (high + low_value) / 2.0
        upper = midpoint + self.factor * atr
        lower = midpoint - self.factor * atr
        previous_close = self.previous_close
        if not (
            lower > self.previous_lower
            or (previous_close is not None and previous_close < self.previous_lower)
        ):
            lower = self.previous_lower
        if not (
            upper < self.previous_upper
            or (previous_close is not None and previous_close > self.previous_upper)
        ):
            upper = self.previous_upper

        if self.index == 0 or self.previous_atr is None:
            direction = 1.0
        elif self.previous_supertrend == self.previous_upper:
            direction = -1.0 if close_value > upper else 1.0
        else:
            direction = 1.0 if close_value < lower else -1.0
        supertrend = lower if direction == -1.0 else upper

        self.previous_atr = atr
        self.previous_close = close_value
        self.previous_upper = upper
        self.previous_lower = lower
        self.previous_supertrend = supertrend
        return supertrend, direction


class _StepPivotPointLevels:
    def __init__(self, pivot_type: str = "traditional", *, developing: bool = False) -> None:
        self.pivot_type = _normalize_pivot_type(pivot_type)
        self.developing = bool(developing)
        if self.pivot_type == "woodie" and self.developing:
            raise ValueError(
                "ctx.ta.pivot_point_levels() does not allow developing=True with Woodie"
            )
        self.fixed_levels = tuple([None] * 11)
        self.period_open: float | None = None
        self.period_high: float | None = None
        self.period_low: float | None = None
        self.period_close: float | None = None

    def update(
        self,
        bar: Any,
        *,
        anchor: Any = False,
        developing: bool | None = None,
        pivot_type: str | None = None,
    ) -> tuple[float | None, ...]:
        selected_type = self.pivot_type if pivot_type is None else _normalize_pivot_type(pivot_type)
        selected_developing = self.developing if developing is None else bool(developing)
        if selected_type == "woodie" and selected_developing:
            raise ValueError(
                "ctx.ta.pivot_point_levels() does not allow developing=True with Woodie"
            )
        current_open = _number_or_none(getattr(bar, "open"))
        high = _number_or_none(getattr(bar, "high"))
        low = _number_or_none(getattr(bar, "low"))
        close = _number_or_none(getattr(bar, "close"))

        if bool(anchor):
            if self.period_open is not None:
                self.fixed_levels = _optional_levels(
                    _pivot_level_values(
                        selected_type,
                        period_open=_nan(self.period_open),
                        period_high=_nan(self.period_high),
                        period_low=_nan(self.period_low),
                        period_close=_nan(self.period_close),
                        current_open=_nan(current_open),
                    )
                )
            else:
                self.fixed_levels = tuple([None] * 11)
            self.period_open = None
            self.period_high = None
            self.period_low = None
            self.period_close = None

        if self.period_open is None:
            self.period_open = current_open
        if high is not None:
            self.period_high = high if self.period_high is None else max(self.period_high, high)
        if low is not None:
            self.period_low = low if self.period_low is None else min(self.period_low, low)
        if close is not None:
            self.period_close = close

        if not selected_developing:
            return self.fixed_levels
        return _optional_levels(
            _pivot_level_values(
                selected_type,
                period_open=_nan(self.period_open),
                period_high=_nan(self.period_high),
                period_low=_nan(self.period_low),
                period_close=_nan(self.period_close),
                current_open=_nan(current_open),
            )
        )


class IncrementalTaNamespace:
    """Stateful TA helper namespace available as ``ctx.ta``."""

    def __init__(self, limits: _LimitTracker | None = None) -> None:
        self._helpers: dict[str, Any] = {}
        self._limits = limits or _LimitTracker(IncrementalLimits(enabled=False))

    def sma(self, name: str, period: int | None = None) -> _StepSMA:
        key = f"sma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.sma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepSMA(period)
        return self._helpers[key]

    def ema(self, name: str, period: int | None = None) -> _StepEMA:
        key = f"ema:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.ema('{name}') has not been initialized")
            self._helpers[key] = _StepEMA(period)
        return self._helpers[key]

    def rma(self, name: str, period: int | None = None) -> _StepRMA:
        key = f"rma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.rma('{name}') has not been initialized")
            self._helpers[key] = _StepRMA(period)
        return self._helpers[key]

    def wma(self, name: str, period: int | None = None) -> _StepWMA:
        key = f"wma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.wma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepWMA(period)
        return self._helpers[key]

    def vwma(self, name: str, period: int | None = None) -> _StepVWMA:
        key = f"vwma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.vwma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepVWMA(period)
        return self._helpers[key]

    def variance(
        self,
        name: str,
        period: int | None = None,
        *,
        biased: bool = True,
    ) -> _StepVariance:
        key = f"variance:{name}:{int(bool(biased))}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.variance('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepVariance(period, biased=biased)
        return self._helpers[key]

    def stdev(self, name: str, period: int | None = None) -> _StepStdev:
        key = f"stdev:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.stdev('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepStdev(period)
        return self._helpers[key]

    def change(self, name: str, period: int | None = None) -> _StepChange:
        key = f"change:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.change('{name}') has not been initialized")
            period = require_positive_period(period)
            self._limits.reserve_window(int(period) + 1, label=key)
            self._helpers[key] = _StepChange(period)
        return self._helpers[key]

    def highestbars(self, name: str, period: int | None = None) -> _StepExtremeBars:
        return self._extreme_bars(name, period, highest=True)

    def lowestbars(self, name: str, period: int | None = None) -> _StepExtremeBars:
        return self._extreme_bars(name, period, highest=False)

    def _extreme_bars(
        self,
        name: str,
        period: int | None,
        *,
        highest: bool,
    ) -> _StepExtremeBars:
        family = "highestbars" if highest else "lowestbars"
        key = f"{family}:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.{family}('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepExtremeBars(period, highest=highest)
        return self._helpers[key]

    def pivothigh(
        self,
        name: str,
        left: int | None = None,
        right: int | None = None,
    ) -> _StepPivot:
        return self._pivot(name, left, right, highest=True)

    def pivotlow(
        self,
        name: str,
        left: int | None = None,
        right: int | None = None,
    ) -> _StepPivot:
        return self._pivot(name, left, right, highest=False)

    def _pivot(
        self,
        name: str,
        left: int | None,
        right: int | None,
        *,
        highest: bool,
    ) -> _StepPivot:
        family = "pivothigh" if highest else "pivotlow"
        key = f"{family}:{name}"
        if key not in self._helpers:
            if left is None:
                raise ValueError(f"ctx.ta.{family}('{name}') has not been initialized")
            selected_right = int(left) if right is None else int(right)
            self._limits.reserve_window(int(left) + selected_right + 1, label=key)
            self._helpers[key] = _StepPivot(left, selected_right, highest=highest)
        return self._helpers[key]

    def tr(self, name: str) -> _StepTrueRange:
        key = f"tr:{name}"
        if key not in self._helpers:
            self._helpers[key] = _StepTrueRange()
        return self._helpers[key]

    def cum(self, name: str) -> _StepCum:
        key = f"cum:{name}"
        if key not in self._helpers:
            self._helpers[key] = _StepCum()
        return self._helpers[key]

    def swma(self, name: str) -> _StepSWMA:
        key = f"swma:{name}"
        if key not in self._helpers:
            self._limits.reserve_window(4, label=key)
            self._helpers[key] = _StepSWMA()
        return self._helpers[key]

    def alma(
        self,
        name: str,
        period: int | None = None,
        offset: float = 0.85,
        sigma: float = 6.0,
    ) -> _StepALMA:
        key = f"alma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.alma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepALMA(period, offset, sigma)
        return self._helpers[key]

    def dev(self, name: str, period: int | None = None) -> _StepDev:
        key = f"dev:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.dev('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepDev(period)
        return self._helpers[key]

    def boll(self, name: str, period: int | None = None, multiplier: float = 2.0) -> _StepBOLL:
        key = f"boll:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.boll('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepBOLL(period, multiplier)
        return self._helpers[key]

    def bb(self, name: str, period: int | None = None, mult: float = 2.0) -> _StepBB:
        key = f"bb:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.bb('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepBB(period, mult)
        return self._helpers[key]

    def macd(
        self,
        name: str,
        fast: int | None = None,
        slow: int = 26,
        signal: int = 9,
    ) -> _StepMACD:
        key = f"macd:{name}"
        if key not in self._helpers:
            if fast is None:
                raise ValueError(f"ctx.ta.macd('{name}') has not been initialized")
            self._helpers[key] = _StepMACD(fast, slow, signal)
        return self._helpers[key]

    def rsi(self, name: str, period: int | None = None) -> _StepRSI:
        key = f"rsi:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.rsi('{name}') has not been initialized")
            self._helpers[key] = _StepRSI(period)
        return self._helpers[key]

    def atr(self, name: str, period: int | None = None) -> _StepATR:
        key = f"atr:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.atr('{name}') has not been initialized")
            self._helpers[key] = _StepATR(period)
        return self._helpers[key]

    def highest(self, name: str, period: int | None = None) -> _StepMonotonic:
        key = f"highest:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.highest('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepMonotonic(period, highest=True)
        return self._helpers[key]

    def lowest(self, name: str, period: int | None = None) -> _StepMonotonic:
        key = f"lowest:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.lowest('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepMonotonic(period, highest=False)
        return self._helpers[key]

    def stoch(self, name: str, period: int | None = None) -> _StepStoch:
        key = f"stoch:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.stoch('{name}') has not been initialized")
            self._limits.reserve_window(period * 2, label=key)
            self._helpers[key] = _StepStoch(period)
        return self._helpers[key]

    def cci(self, name: str, period: int | None = None) -> _StepCCI:
        key = f"cci:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.cci('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepCCI(period)
        return self._helpers[key]

    def hma(self, name: str, period: int | None = None) -> _StepHMA:
        key = f"hma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.hma('{name}') has not been initialized")
            half = max(int(period / 2), 1)
            root = max(int(math.sqrt(period)), 1)
            self._limits.reserve_window(half + int(period) + root, label=key)
            self._helpers[key] = _StepHMA(period)
        return self._helpers[key]

    def barssince(self, name: str) -> _StepBarsSince:
        key = f"barssince:{name}"
        if key not in self._helpers:
            self._helpers[key] = _StepBarsSince()
        return self._helpers[key]

    def valuewhen(self, name: str, occurrence: int | None = None) -> _StepValueWhen:
        key = f"valuewhen:{name}"
        if key not in self._helpers:
            if occurrence is None:
                raise ValueError(f"ctx.ta.valuewhen('{name}') has not been initialized")
            self._limits.reserve_window(max(int(occurrence), 0) + 1, label=key)
            self._helpers[key] = _StepValueWhen(occurrence)
        return self._helpers[key]

    def crossover(self, name: str) -> _StepCross:
        return self._cross(name, "over")

    def crossunder(self, name: str) -> _StepCross:
        return self._cross(name, "under")

    def cross(self, name: str) -> _StepCross:
        return self._cross(name, "either")

    def _cross(self, name: str, direction: str) -> _StepCross:
        key = f"cross:{direction}:{name}"
        if key not in self._helpers:
            self._helpers[key] = _StepCross(direction)
        return self._helpers[key]

    def vwap(self, name: str) -> _StepVWAP:
        key = f"vwap:{name}"
        if key not in self._helpers:
            self._helpers[key] = _StepVWAP()
        return self._helpers[key]

    def dmi(
        self,
        name: str,
        period: int | None = None,
        adx_period: int = 14,
    ) -> _StepDMI:
        key = f"dmi:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.dmi('{name}') has not been initialized")
            self._helpers[key] = _StepDMI(period, adx_period)
        return self._helpers[key]

    def adx(
        self,
        name: str,
        period: int | None = None,
        adx_period: int | None = None,
    ) -> _StepADX:
        key = f"adx:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.adx('{name}') has not been initialized")
            self._helpers[key] = _StepADX(period, period if adx_period is None else adx_period)
        return self._helpers[key]

    def sar(
        self,
        name: str,
        start: float | None = None,
        increment: float = 0.02,
        maximum: float = 0.2,
    ) -> _StepSAR:
        key = f"sar:{name}"
        if key not in self._helpers:
            if start is None:
                raise ValueError(f"ctx.ta.sar('{name}') has not been initialized")
            self._limits.reserve_window(4, label=key)
            self._helpers[key] = _StepSAR(start, increment, maximum)
        return self._helpers[key]

    def mfi(self, name: str, period: int | None = None) -> _StepMFI:
        key = f"mfi:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.mfi('{name}') has not been initialized")
            self._limits.reserve_window(int(period) * 2, label=key)
            self._helpers[key] = _StepMFI(period)
        return self._helpers[key]

    def supertrend(
        self,
        name: str,
        factor: float | None = None,
        atr_period: int = 10,
    ) -> _StepSupertrend:
        key = f"supertrend:{name}"
        if key not in self._helpers:
            if factor is None:
                raise ValueError(f"ctx.ta.supertrend('{name}') has not been initialized")
            self._helpers[key] = _StepSupertrend(factor, atr_period)
        return self._helpers[key]

    def pivot_point_levels(
        self,
        name: str,
        pivot_type: str | None = None,
        *,
        developing: bool = False,
    ) -> _StepPivotPointLevels:
        key = f"pivot_point_levels:{name}"
        if key not in self._helpers:
            if pivot_type is None:
                raise ValueError(
                    f"ctx.ta.pivot_point_levels('{name}') has not been initialized"
                )
            self._helpers[key] = _StepPivotPointLevels(
                pivot_type,
                developing=developing,
            )
        return self._helpers[key]

def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 0.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number


def _nan(value: float | None) -> float:
    return math.nan if value is None else float(value)


def _optional_levels(values: Any) -> tuple[float | None, ...]:
    return tuple(
        None if not math.isfinite(float(value)) else float(value)
        for value in values
    )
