# ruff: noqa: F821
"""First-party workload: nested cache aliases, explicit state and rolling TA."""

indicator("State cache", mode="incremental")
ledger = cache("ledger", lambda: {"total": 0, "tail": []})


def init(ctx):
    ctx.ta.sma("mean", 3)


def on_bar(ctx, bar):
    count = ctx.state("count", 0)
    count.value += 1
    current = cache("ledger", lambda: {"total": 0, "tail": []})
    current["total"] += bar.close
    current["tail"].append(bar.close)
    if len(current["tail"]) > 3:
        current["tail"].pop(0)
    ctx.plot("Count", count.value)
    ctx.plot("Total", ledger["total"])
    ctx.plot("Tail sum", sum(ledger["tail"]))
    ctx.plot("Mean", ctx.ta.sma("mean").update(bar.close))
