# ruff: noqa: F821
"""First-party workload: repeated create/update/delete of state-held handles."""

indicator("Drawings", mode="incremental", overlay=True)


def on_bar(ctx, bar):
    level = ctx.state("level")
    note = ctx.state("note")
    phase = ctx.bar_index % 4
    if phase == 0:
        level.value = line.new(ctx.bar_index, bar.low, ctx.bar_index, bar.high)
        note.value = label.new(ctx.bar_index, bar.high, "start")
    elif phase == 3:
        line.delete(level.value)
        label.delete(note.value)
        level.value = None
        note.value = None
    else:
        line.set_xy2(level.value, ctx.bar_index, bar.high)
        label.set_xy(note.value, ctx.bar_index, bar.high)
        label.set_text(note.value, str(ctx.bar_index))
    ctx.plot("Phase", phase)
