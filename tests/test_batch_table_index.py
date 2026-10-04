from __future__ import annotations

import pytest

from pyne_runtime.plot import OutputCollector, create_plot_functions
from pyne_runtime.security import PyneSecurityError


class _NoScanCells(list):
    def __iter__(self):
        raise AssertionError("table mutation must not scan live cells")

    def sort(self, *args, **kwargs):
        raise AssertionError("table mutation must not sort live cells")


def test_exported_table_coordinates_cannot_invalidate_live_cell_indices() -> None:
    collector = OutputCollector([1])
    table = create_plot_functions(collector)["table"]
    ref = table.new(columns=2, rows=1)
    table.cell(ref, 0, 0, "original")
    exported = collector.to_dict()["objects"]["tables"][0]
    exported["cells"][0].update(column=1, row=7, text="caller mutation")
    table.cell(ref, 0, 0, "updated")
    table.cell(ref, 1, 0, "second")
    cells = collector.to_dict()["objects"]["tables"][0]["cells"]
    assert [(cell["column"], cell["row"], cell["text"]) for cell in cells] == [
        (0, 0, "updated"), (1, 0, "second")]
    assert collector._table_cell_count == 2


def test_batch_table_mutation_does_not_scan_or_sort_live_cells() -> None:
    collector = OutputCollector([1], max_table_cells=4)
    table = create_plot_functions(collector)["table"]
    ref = table.new(columns=4, rows=2)
    table.cell(ref, 2, 1, "first")
    entry = collector._object_tables[ref.id]
    entry["cells"] = _NoScanCells(entry["cells"])

    table.cell(ref, 0, 0, "second")
    table.cell(ref, 2, 1, "updated")
    table.cell(ref, 1, 1, "third")

    assert len(entry["cells"]) == 3
    assert entry["cells"][0]["text"] == "updated"
    assert collector._table_cell_count == 3
    table.clear(ref)
    assert collector._table_cell_count == 0
    table.cell(ref, 2, 1, "after clear")
    assert entry["cells"][0]["text"] == "after clear"
    table.delete(ref)
    assert collector._table_cell_count == 0
    assert ref.id not in collector._table_cell_indices


def test_batch_table_export_is_sorted_without_invalidating_mutation_indices() -> None:
    collector = OutputCollector([1])
    table = create_plot_functions(collector)["table"]
    ref = table.new(columns=3, rows=2)
    table.cell(ref, 2, 1, "last")
    table.cell(ref, 1, 0, "middle")
    table.cell(ref, 0, 0, "first")

    exported = collector.to_dict()["objects"]["tables"][0]["cells"]
    assert [cell["text"] for cell in exported] == ["first", "middle", "last"]
    table.cell(ref, 2, 1, "updated")
    exported = collector.to_dict()["objects"]["tables"][0]["cells"]
    assert [cell["text"] for cell in exported] == ["first", "middle", "updated"]


def test_batch_table_quota_counts_live_cells_across_tables() -> None:
    collector = OutputCollector([1], max_table_cells=1)
    table = create_plot_functions(collector)["table"]
    first = table.new(columns=2)
    second = table.new(columns=2)
    table.cell(first, 0, 0, "one")
    table.cell(first, 0, 0, "update")
    with pytest.raises(PyneSecurityError, match="Table cells"):
        table.cell(second, 0, 0, "two")
    assert collector._object_tables[second.id]["cells"] == []
    table.clear(first)
    table.cell(second, 0, 0, "two")
    table.delete(second)
    table.delete(second)
    table.cell(first, 1, 0, "three")
    assert collector._table_cell_count == 1
