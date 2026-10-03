from __future__ import annotations

import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import pyne_runtime as pn


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CURRENT_STATUS = DOCS / "reference" / "current_status.md"
API_MATRIX = DOCS / "reference" / "pine_like_api_matrix.md"
INCREMENTAL_GUIDE = DOCS / "concepts" / "incremental_runtime.md"
PINE_LIBRARIES_DOC = DOCS / "api" / "pine_libraries.md"
CAPABILITIES_DOC = DOCS / "api" / "capabilities.md"
TA_DOC = DOCS / "api" / "ta.md"
CORPUS_DOC = DOCS / "reference" / "pine_corpus_compatibility.md"
COMPLETION_PLAN = DOCS / "development" / "capability_completion_execution_plan_zh.md"
DEMAND_BACKLOG = DOCS / "development" / "capability_demand_backlog_zh.md"
PYPROJECT = ROOT / "pyproject.toml"
TA_CAPTURE_DIFF = ROOT / "scripts" / "ta_capture_diff.py"

INCREMENTAL_HELPER_LIST_RE = re.compile(
    r"The currently promoted incremental TA helpers are (.+?)\.\s+Query",
    re.DOTALL,
)
TA_CAPTURE_COUNT_RE = re.compile(
    r"All (\d+) committed TA capture fixtures retain imported TradingView records "
    r"across (\d{1,3}(?:,\d{3})*) plots and "
    r"(\d{1,3}(?:,\d{3})*) checked points"
)
TA_DOC_CAPTURE_COUNT_RE = re.compile(
    r"All (\d+) committed TA capture fixtures keep a `pine_equivalent` script "
    r"beside\nthe Pyne script and contain imported TradingView output\. "
    r"The parity gate\ncurrently checks (\d{1,3}(?:,\d{3})*) plots and "
    r"(\d{1,3}(?:,\d{3})*) points"
)
LIBRARY_IDENTIFIER_RE = re.compile(r'pine_library\("([^"]+)"\)')
LIBRARY_MEMBER_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)\(\)`")
SCALAR_HELPER_COUNT_RE = re.compile(r"(\d+) scalar helpers")
INCREMENTAL_SURFACE_RE = re.compile(r"(\d+)-member incremental surface")


def _load_script(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _markdown_table_row(body: str, feature: str) -> tuple[str, ...]:
    prefix = f"| {feature} |"
    line = next(line for line in body.splitlines() if line.startswith(prefix))
    cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
    assert cells[0] == feature
    assert len(cells) >= 4
    return cells


def _backtick_names(text: str) -> list[str]:
    return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", text)


def _parse_int(raw: str) -> int:
    return int(raw.replace(",", ""))


def _slash_members(api_cell: str, prefix: str) -> list[str]:
    inner = api_cell.strip("`")
    assert inner.startswith(prefix), api_cell
    return inner[len(prefix) :].split("/")


def _project_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def _live_ta_capture_counts() -> tuple[int, int, int]:
    ta_capture_diff = _load_script(TA_CAPTURE_DIFF)
    fixtures = sorted((ROOT / "tests" / "golden").glob("ta_*_indicators.json"))
    report = ta_capture_diff.build_report(fixtures, set(), "parity")
    counts = report["counts"]
    assert counts["unexpected_differences"] == 0
    assert counts["runtime_errors"] == 0
    return counts["captured_fixtures"], counts["plots"], counts["points"]


def test_current_status_source_version_matches_pyproject() -> None:
    version = _project_version()
    body = CURRENT_STATUS.read_text(encoding="utf-8")

    # Source version is pyproject.toml; pn.__version__ reports the installed
    # distribution and may still be the published 0.2.x artifact.
    assert f"Package version from `pyproject.toml`: **{version}**" in body


def test_incremental_guide_lists_live_incremental_ta_members() -> None:
    capabilities = pn.runtime_capabilities()
    expected = list(capabilities["modes"]["incremental"]["ta"])
    body = INCREMENTAL_GUIDE.read_text(encoding="utf-8")
    match = INCREMENTAL_HELPER_LIST_RE.search(body)

    assert match is not None, "incremental guide is missing the promoted helper list"
    assert "27 scalar helpers" not in body
    listed = _backtick_names(match.group(1))
    assert listed == expected


def test_api_matrix_incremental_ta_matches_capability_contract() -> None:
    capabilities = pn.runtime_capabilities()
    expected = list(capabilities["modes"]["incremental"]["ta"])
    cells = _markdown_table_row(API_MATRIX.read_text(encoding="utf-8"), "Incremental TA")
    listed = _slash_members(cells[1], "ctx.ta.")
    count_match = SCALAR_HELPER_COUNT_RE.search(cells[3])

    assert listed == expected
    assert count_match is not None
    assert int(count_match.group(1)) == len(expected)


def test_api_matrix_and_library_docs_match_external_library_contract() -> None:
    capabilities = pn.runtime_capabilities()
    libraries = capabilities["externalLibraries"]
    assert len(libraries) == 1
    library = libraries[0]
    expected_members = list(library["members"])
    expected_modes = list(library["modes"])

    matrix_cells = _markdown_table_row(
        API_MATRIX.read_text(encoding="utf-8"),
        "Pinned external library",
    )
    identifier_match = LIBRARY_IDENTIFIER_RE.search(matrix_cells[1])
    assert identifier_match is not None
    listed_members = _slash_members(
        matrix_cells[1][identifier_match.end() :],
        ".",
    )

    assert identifier_match.group(1) == library["identifier"]
    assert listed_members == expected_members
    assert "batch-only" in matrix_cells[3]
    assert expected_modes == ["batch"]

    library_doc = PINE_LIBRARIES_DOC.read_text(encoding="utf-8")
    assert f'pine_library("{library["identifier"]}")' in library_doc
    assert "batch-runtime" in library_doc
    assert "batch-only" in library_doc
    documented_members = LIBRARY_MEMBER_RE.findall(
        library_doc.split("The pinned adapter is currently a batch-runtime surface.", 1)[1]
    )
    # Keep the explicit allowlist paragraph aligned with the live registry.
    first_allowlist = documented_members[: len(expected_members)]
    assert first_allowlist == expected_members


def test_current_status_and_corpus_docs_use_live_incremental_count() -> None:
    expected_count = len(pn.runtime_capabilities()["modes"]["incremental"]["ta"])
    status = CURRENT_STATUS.read_text(encoding="utf-8")
    corpus = CORPUS_DOC.read_text(encoding="utf-8")
    status_match = re.search(
        r"\*\*Expanded incremental TA:\*\* (\d+) scalar helpers",
        status,
    )
    corpus_match = INCREMENTAL_SURFACE_RE.search(corpus)

    assert status_match is not None
    assert int(status_match.group(1)) == expected_count
    assert "27 scalar helpers" not in status
    assert corpus_match is not None
    assert int(corpus_match.group(1)) == expected_count
    assert "27-member incremental surface" not in corpus


def test_ta_capture_counts_in_docs_match_live_parity_gate() -> None:
    fixtures, plots, points = _live_ta_capture_counts()
    matrix_cells = _markdown_table_row(API_MATRIX.read_text(encoding="utf-8"), "Core TA")
    matrix_match = TA_CAPTURE_COUNT_RE.search(matrix_cells[3])
    ta_match = TA_DOC_CAPTURE_COUNT_RE.search(TA_DOC.read_text(encoding="utf-8"))

    assert matrix_match is not None
    assert ta_match is not None
    assert int(matrix_match.group(1)) == fixtures
    assert _parse_int(matrix_match.group(2)) == plots
    assert _parse_int(matrix_match.group(3)) == points
    assert int(ta_match.group(1)) == fixtures
    assert _parse_int(ta_match.group(2)) == plots
    assert _parse_int(ta_match.group(3)) == points


def test_capabilities_doc_declares_runtime_capabilities_as_source_of_truth() -> None:
    body = CAPABILITIES_DOC.read_text(encoding="utf-8")

    assert "pn.runtime_capabilities()" in body
    assert "checked source of truth" in body
    assert 'pn.schema()["runtimeCapabilities"]' in body


def test_current_completion_docs_keep_product_adapters_out_of_runtime_scope() -> None:
    plan = COMPLETION_PLAN.read_text(encoding="utf-8")
    backlog = DEMAND_BACKLOG.read_text(encoding="utf-8")
    status = CURRENT_STATUS.read_text(encoding="utf-8")

    for body in (plan, backlog, status):
        assert "CandleScope" not in body

    assert "不读取或修改任何产品适配仓库" in plan
    assert "Product-specific bridges" in status
    assert "packaged examples" in backlog
