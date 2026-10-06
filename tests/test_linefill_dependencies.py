"""Line deletion visits only its fills, preserving replay and event ordering."""
import pytest

import pyne_runtime as pn
from pyne_runtime.incremental.context import IncrementalContext
from pyne_runtime.plot import OutputCollector, create_plot_functions


class CountedEntries(dict):
    visits = 0

    def items(self):
        for pair in super().items():
            self.visits += 1
            yield pair


@pytest.mark.parametrize("incremental", [False, True])
@pytest.mark.parametrize("count", [128, 256, 512])
def test_clear_disjoint_dependencies_has_linear_bucket_work(incremental, count):
    owner = IncrementalContext(params={}) if incremental else OutputCollector([])
    if incremental:
        new, fill, delete = owner.line_new, owner.linefill_new, owner.line_delete
    else:
        functions = create_plot_functions(owner)
        new, fill, delete = functions["line"].new, functions["linefill"].new, functions["line"].delete
    firsts = []
    for i in range(count):
        first, second = new(i, 0, i, 1), new(i, 1, i, 2)
        firsts.append(first)
        fill(first, second)
    # Model a plain authoritative bucket obtained from portable decoding.
    entries = CountedEntries(owner._object_linefills)
    owner._object_linefills = entries
    for first in firsts:
        delete(first)
    assert not owner._object_linefills
    assert len(owner._object_lines) == count
    assert entries.visits <= count


def test_batch_shared_and_same_line_fill_dependencies_clean_up_once():
    result = pn.run('''a = line.new(0, 0, 1, 1)
b = line.new(0, 1, 1, 2)
c = line.new(0, 2, 1, 3)
deleted = linefill.new(a, b)
linefill.delete(deleted)
linefill.new(a, a)
linefill.new(a, c)
survivor = linefill.new(b, c, color="green")
line.delete(a)
line.delete(a)
linefill.set_color(deleted, "red")
''', [dict(time=1, open=1, high=1, low=1, close=1, volume=1)])
    assert result.ok, result.error
    assert [item["id"] for item in result.output["objects"]["lines"]] == ["line_2", "line_3"]
    assert [item["id"] for item in result.output["objects"]["linefills"]] == ["linefill_7"]


SCRIPT = '''indicator("Dependency continuation", mode="incremental")
def on_bar(ctx, bar):
    refs = ctx.state("refs", [])
    if ctx.bar_index == 0:
        a, b, c = line.new(0, 0, 1, 1), line.new(0, 1, 1, 2), line.new(0, 2, 1, 3)
        doomed = linefill.new(a, b)
        linefill.delete(doomed)
        linefill.new(a, a)
        linefill.new(a, c)
        linefill.new(b, c)
        refs.value = [a, b, c]
    else:
        line.delete(refs.value[ctx.bar_index - 1])
'''
BARS = [dict(time=i+1, open=1, high=1, low=1, close=1, volume=1) for i in range(3)]


@pytest.mark.parametrize("mode", ["local", "state", "replay"])
def test_dependency_index_survives_restore_and_preview(mode):
    original = pn.PyneIncrementalSession(script=SCRIPT)
    original.seed(BARS[:1])
    restored = (pn.PyneIncrementalSession.from_snapshot(original.snapshot_state(), script=SCRIPT)
        if mode == "local" else pn.PyneIncrementalSession.from_portable_snapshot(
            original.snapshot_portable(mode=mode), script=SCRIPT))
    before = restored.snapshot_portable_state()
    restored.on_bar_updated(BARS[1])
    original.on_bar_updated(BARS[1])
    assert restored.snapshot_portable_state() == before
    assert restored.snapshot_result() == original.snapshot_result()
    for bar in BARS[1:]:
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
    result = restored.snapshot_result()
    assert not result.output["objects"].get("linefills")
    assert [entry["id"] for entry in result.output["objects"]["lines"]] == ["line_3"]
    deletes = [(event["kind"], event["id"]) for event in result.output["object_events"]
               if event["action"] == "delete"]
    assert deletes == [("linefill", "linefill_4"), ("linefill", "linefill_5"),
                       ("linefill", "linefill_6"), ("line", "line_1"),
                       ("linefill", "linefill_7"), ("line", "line_2")]
