# ruff: noqa: F821
"""First-party workload: HTF confirmed close, LTF groups, chained TA."""

indicator("Requests", mode="incremental")


def init(ctx):
    ctx.ta.sma("local", 3)


def on_bar(ctx, bar):
    higher = ctx.request.security("TEST:ASSET", "30S", "close")
    lower = ctx.request.security_lower_tf("TEST:ASSET", "5S", "close")
    average = ctx.ta.sma("local").update(bar.close)
    ctx.plot("HTF", higher)
    ctx.plot("LTF count", lower.size())
    ctx.plot("LTF last", lower.last())
    ctx.plot("Spread", None if average is None or higher is None else average - higher)
