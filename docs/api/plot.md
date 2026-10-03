# Plot API

Plot helpers are injected into scripts.

Calculation values in line, histogram, candle, marker, drawing-coordinate and
signal-price payloads preserve their binary64 precision. `indicator(precision=2)`
and `plot(precision=0)` supply display hints; they do not round calculation data.
JSON round trips retain ordinary finite float values. Existing missing-value
filtering and output shapes remain unchanged. Hosts choose how to render values.
This contract does not provide arbitrary-precision arithmetic or remove the
strategy ledger/report's existing eight-decimal formatting.

```python
indicator("Bands", overlay=True, format=format.price, scale=scale.right)

p1 = plot(upper, "Upper", color=color.blue)
plot(mid, "Middle", color=color.orange, display=display.all)
p2 = plot(lower, "Lower", color=color.blue)
fill(p1, p2, color="rgba(59,130,246,0.08)")
plotshape(close > open, title="Up", style=shape.triangleup, location=location.abovebar)
plotchar(close > open, title="Up Char", char="*", location=location.abovebar)
plotarrow(close - open, title="Body Direction")
marker(close > open, shape=shape.triangleup, location=location.abovebar, size=size.small)
```

Common outputs:

- `plot()`
- `bar()`
- `hline()`
- `fill()`
- `plotshape()`
- `plotchar()`
- `plotarrow()`
- `marker()`
- `bgcolor()`
- `barcolor()`
- `emit_signal()`
- `alertcondition()`
- `line.new()` / `line.set_*()` / `line.delete()`
- `label.new()` / `label.set_*()` / `label.delete()`
- `box.new()` / `box.set_*()` / `box.delete()`
- `table.new()` / `table.cell()` / `table.delete()`

`label("text")` remains available as a compact legacy helper for fixed-position
layout labels. Use `label.new()` when you need a Pine-like mutable label object
anchored to a bar or price.

## Shape Plots

`plotshape()` is the Pine-like wrapper for marker output. It accepts Pine-style
argument names while serializing to the same `output["markers"]` schema used by
`marker()`.

```python
plotshape(
    close > open,
    title="Close Up",
    style=shape.triangleup,
    location=location.belowbar,
    color=color.green,
    text="BUY",
    textcolor=color.white,
    size=size.small,
)
```

Supported arguments include `title`, `style`, `location`, `color`, `offset`,
`text`, `textcolor`, `size`, `show_last`, `display`, and `force_overlay`.
When `location=location.absolute`, numeric series values are emitted as marker
`value` fields so the host can place the marker at a price-like coordinate.

`plotchar()` follows the same output path, but uses `shape="char"` and carries
the requested character in both the marker `char` field and the marker text.

```python
plotchar(
    close > open,
    title="Close Up",
    char="*",
    location=location.abovebar,
    color=color.blue,
    textcolor=color.white,
    size=size.tiny,
)
```

Supported arguments include `title`, `char`, `location`, `color`, `offset`,
`text`, `textcolor`, `size`, `show_last`, `display`, and `force_overlay`.

`plotarrow()` maps a signed numeric series to directional arrow markers.
Positive values emit upward arrows, negative values emit downward arrows, and
zero or missing values are skipped.

```python
plotarrow(
    close - open,
    title="Body Direction",
    colorup=color.green,
    colordown=color.red,
    minheight=10,
    maxheight=30,
)
```

Supported arguments include `title`, `colorup`, `colordown`, `offset`,
`minheight`, `maxheight`, `show_last`, `display`, and `force_overlay`.
Each emitted point includes `direction`, `value`, and a scaled `height`.

## Drawing Objects

`line`, `label`, `box`, and `table` are Pine-like object namespaces.
Constructors return opaque handles that can be passed to setter functions. Pyne
serializes the final object snapshot under `output["objects"]`. Incremental
scripts also emit create/update/delete records under `output["object_events"]`.

```python
indicator("Objects", overlay=True)

trend = line.new(bar_index[2], close[2], bar_index, close, color=color.orange, xloc=xloc.bar_index)
line.set_color(trend, color.blue)
line.set_width(trend, 3)

note = label.new(bar_index, high, text="Breakout", color=color.green, yloc=yloc.abovebar)
label.set_text(note, "Confirmed")

zone = box.new(bar_index[2], high[2], bar_index, low)
box.set_bgcolor(zone, color.new(color.green, 85))

summary = table.new(position.top_right, 2, 1)
table.cell(summary, 0, 0, "Close")
table.cell(summary, 1, 0, close)
```

The `chart.point` namespace creates mutable coordinate objects:

```python
start = chart.point.from_index(bar_index[2], high[2])
finish = chart.point.now(close)
trend = line.new(start, finish)

finish.price = high
line.set_second_point(trend, finish)
```

Available constructors are `chart.point.new(time, index, price)`,
`chart.point.now(price)`, `chart.point.from_index(index, price)`,
`chart.point.from_time(time, price)`, and `chart.point.copy(point)`. Drawing
point overloads select `point.index` for `xloc.bar_index` and `point.time` for
`xloc.bar_time`.

For object coordinates, series arguments are resolved to their latest valid
value. This makes history references such as `bar_index[2]` and `close[2]`
usable in batch execution.

In incremental execution, object coordinates are ordinary scalar callback
values such as `ctx.bar_index`, `bar.time`, `bar.high`, or `bar.close`.
`on_bar_closed()` returns events for the committed bar; `on_bar_updated()`
returns preview events from a cloned context without mutating the persistent
session.

Supported `line` methods:

- `line.new(x1, y1, x2, y2, color="#2196f3", width=1, style="solid", extend="none")`
- `line.new(first_point, second_point, xloc=xloc.bar_index)`
- `line.set_first_point(ref, point)` / `line.set_second_point(ref, point)`
- `line.set_xy1(ref, x, y)`
- `line.set_xy2(ref, x, y)`
- `line.set_x1(ref, x)`
- `line.set_y1(ref, y)`
- `line.set_x2(ref, x)`
- `line.set_y2(ref, y)`
- `line.set_color(ref, color)`
- `line.set_width(ref, width)`
- `line.set_style(ref, style)`
- `line.set_extend(ref, extend)`
- `line.get_x1(ref)` / `line.get_y1(ref)`
- `line.get_x2(ref)` / `line.get_y2(ref)`
- `line.delete(ref)`
- `line.all` returns a fresh oldest-first array of live handles

Supported `label` methods:

- `label.new(x, y, text="", color="#ffffff", textcolor="#000000")`
- `label.new(point, text="", color="#ffffff", textcolor="#000000")`
- `label.set_point(ref, point)`
- `label.set_xy(ref, x, y)`
- `label.set_x(ref, x)`
- `label.set_y(ref, y)`
- `label.set_text(ref, text)`
- `label.set_color(ref, color)`
- `label.set_textcolor(ref, textcolor)`
- `label.set_style(ref, style)`
- `label.set_size(ref, size)`
- `label.set_tooltip(ref, tooltip)`
- `label.get_x(ref)` / `label.get_y(ref)` / `label.get_text(ref)`
- `label.delete(ref)`

Supported `box` methods:

- `box.new(left, top, right, bottom, bgcolor="rgba(0,0,0,0)")`
- `box.new(top_left_point, bottom_right_point, bgcolor="rgba(0,0,0,0)")`
- `box.set_top_left_point(ref, point)`
- `box.set_bottom_right_point(ref, point)`
- `box.set_left(ref, left)`
- `box.set_top(ref, top)`
- `box.set_right(ref, right)`
- `box.set_bottom(ref, bottom)`
- `box.set_lefttop(ref, left, top)`
- `box.set_rightbottom(ref, right, bottom)`
- `box.set_bgcolor(ref, bgcolor)`
- `box.set_border_color(ref, border_color)`
- `box.set_border_width(ref, border_width)`
- `box.set_border_style(ref, border_style)`
- `box.set_extend(ref, extend)`
- `box.set_text(ref, text)`
- `box.set_text_color(ref, color)`
- `box.set_text_size(ref, size)`
- `box.set_text_halign(ref, alignment)`
- `box.set_text_valign(ref, alignment)`
- `box.get_left(ref)` / `box.get_top(ref)`
- `box.get_right(ref)` / `box.get_bottom(ref)`
- `box.copy(ref)`
- `box.delete(ref)`
- `box.all` returns a fresh oldest-first array of live handles

Supported `table` methods:

- `table.new(position=position.top_right, columns=1, rows=1)`
- `table.cell(ref, column, row, text="", text_color="#000000")`
- `table.clear(ref)`
- `table.merge_cells(ref, start_column, start_row, end_column, end_row)`
- `table.set_position(ref, position)`
- `table.set_bgcolor(ref, bgcolor)`
- `table.set_frame_color(ref, frame_color)`
- `table.set_border_color(ref, border_color)`
- `table.delete(ref)`

Merged regions are bounds-checked and cannot overlap. They are serialized in
`output.objects.tables[*].merges` under output schema v2.

Output schema v2 also exposes:

- `plotcandle(open, high, low, close, ...)` under `output.candles`.
- `linefill.new(line1, line2, color=...)`, `linefill.set_color`, and
  `linefill.delete` under `output.objects.linefills`.
- `polyline.new(points, ...)` and `polyline.delete` under
  `output.objects.polylines`. Points must be `chart.point` values.

Table placement constants are available under `position.*`, including
`position.top_right`, `position.middle_center`, and `position.bottom_left`.

## Enum Namespaces

Pyne exposes Pine-like enum namespaces as script globals. They resolve to plain
strings in the serialized output, so host renderers can keep their existing
contracts.

Common plotting and drawing constants:

- `plot.style_line`, `plot.style_histogram`, `plot.style_columns`
- `hline.style_solid`, `hline.style_dashed`, `hline.style_dotted`
- `shape.xcross`, `shape.cross`, `shape.circle`, `shape.triangleup`,
  `shape.triangledown`, `shape.flag`, `shape.arrowup`, `shape.arrowdown`,
  `shape.labelup`, `shape.labeldown`, `shape.square`, `shape.diamond`
- `location.abovebar`, `location.belowbar`, `location.top`,
  `location.bottom`, `location.absolute`
- `size.auto`, `size.tiny`, `size.small`, `size.normal`, `size.large`, `size.huge`
- `display.none`, `display.all`, `display.pane`, `display.data_window`,
  `display.status_line`
- `format.inherit`, `format.mintick`, `format.price`, `format.volume`,
  `format.percent`
- `scale.left`, `scale.right`, `scale.none`
- `xloc.bar_index`, `xloc.bar_time`
- `yloc.price`, `yloc.abovebar`, `yloc.belowbar`
- `extend.none`, `extend.left`, `extend.right`, `extend.both`
- `text.align_left`, `text.align_center`, `text.align_right`,
  `text.align_top`, `text.align_middle`, `text.align_bottom`
- `line.style_solid`, `line.style_dashed`, `line.style_dotted`
- `line.extend_none`, `line.extend_left`, `line.extend_right`,
  `line.extend_both`
- `label.style_label_up`, `label.style_label_down`, `label.style_label_left`,
  `label.style_label_right`, `label.style_label_center`
- `box.border_style_solid`, `box.border_style_dashed`,
  `box.border_style_dotted`
- `position.top_left`, `position.top_center`, `position.top_right`,
  `position.middle_left`, `position.middle_center`, `position.middle_right`,
  `position.bottom_left`, `position.bottom_center`, `position.bottom_right`

