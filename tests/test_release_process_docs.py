from __future__ import annotations

import re
import shlex
import tomllib
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"
RELEASE_DOC = ROOT / "docs" / "reference" / "release_process.md"
PINE_LIKE_API_MATRIX = ROOT / "docs" / "reference" / "pine_like_api_matrix.md"
PROVIDER_CONTRACT_EXAMPLE = ROOT / "examples" / "request_provider_contract.py"
CHECK_PS1 = ROOT / "scripts" / "check.ps1"
CHECK_SH = ROOT / "scripts" / "check.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
README = ROOT / "README.md"

COMMON_PYTHON_GATE_PREFIXES = (
    ("-m", "compileall", "src", "tests", "-q"),
    ("-m", "ruff", "check", "."),
    ("scripts/project_status.py", "--check"),
    ("-m", "pytest"),
    ("scripts/performance_smoke.py", "--check"),
    ("scripts/incremental_stability_smoke.py", "--check"),
    ("scripts/strategy_capture_scaffold.py", "--check"),
    ("scripts/strategy_capture_diff.py", "--assertion", "parity"),
    ("scripts/ta_capture_diff.py", "--assertion", "parity"),
    ("scripts/request_capture_diff.py", "--assertion", "parity"),
)


def _markdown_h2_sections(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## ([^\n]+)$", body, flags=re.MULTILINE))
    return {
        match.group(1).strip(): body[
            match.end() : matches[index + 1].start() if index + 1 < len(matches) else None
        ].strip()
        for index, match in enumerate(matches)
    }


def _markdown_h2_headings(body: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"^## ([^\n]+)$", body, flags=re.MULTILINE)
    ]


def _markdown_table_row(body: str, feature: str) -> tuple[str, ...]:
    prefix = f"| {feature} |"
    line = next(line for line in body.splitlines() if line.startswith(prefix))
    cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
    assert cells[0] == feature
    assert len(cells) >= 4
    return cells


def _powershell_python_commands(body: str) -> list[tuple[str, ...]]:
    blocks = re.findall(
        r"Invoke-PyneCheck\s+-Arguments\s+@\((.*?)\)",
        body,
        flags=re.DOTALL,
    )
    return [tuple(re.findall(r'"([^"]*)"', block)) for block in blocks]


def _shell_commands(body: str) -> list[tuple[str, ...]]:
    commands: list[tuple[str, ...]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith('"$PYTHON" ') or line == "git diff --check":
            commands.append(tuple(shlex.split(line)))
    return commands


def _workflow_run_commands(body: str) -> list[tuple[str, ...]]:
    lines = body.splitlines()
    commands: list[tuple[str, ...]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped.startswith("run:"):
            index += 1
            continue

        indent = len(line) - len(line.lstrip())
        value = stripped.removeprefix("run:").strip()
        if value and value != "|":
            commands.append(tuple(shlex.split(value)))
            index += 1
            continue

        index += 1
        while index < len(lines):
            candidate = lines[index]
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate.strip() and candidate_indent <= indent:
                break
            if candidate.strip():
                commands.append(tuple(shlex.split(candidate.strip())))
            index += 1
    return commands


def _assert_command_prefixes(
    commands: list[tuple[str, ...]],
    prefixes: tuple[tuple[str, ...], ...],
) -> None:
    for prefix in prefixes:
        assert any(command[: len(prefix)] == prefix for command in commands), prefix


def test_release_process_documents_version_policy_and_gates() -> None:
    sections = _markdown_h2_sections(RELEASE_DOC.read_text(encoding="utf-8"))
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    version_policy = sections["Version Policy"]
    for required in (
        "Patch releases should not break public root imports",
        "Minor releases may add public APIs",
        "Any breaking change must include",
    ):
        assert required in version_policy

    release_checklist = sections["Release Checklist"]
    for required in (
        "scripts/check.ps1",
        "scripts/check.sh",
        "pyne_runtime/py.typed",
        "temporary wheel environment",
        "pyne schema",
        "CHANGELOG.md",
        ".github/workflows/release.yml",
        "SHA256SUMS",
    ):
        assert required in release_checklist

    assert "quality gates" in sections["Changelog Rules"]
    assert "hatchling>=1.25" in project["project"]["optional-dependencies"]["dev"]


def test_github_release_workflow_publishes_verified_distribution_assets() -> None:
    body = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    for required in (
        'tags:\n      - "v*"',
        "contents: write",
        "git merge-base --is-ancestor",
        "python -m build",
        "python -m twine check dist/*",
        "python scripts/package_smoke.py --dist-dir dist",
        "python scripts/release_assets.py",
        "dist/*.whl dist/*.tar.gz dist/SHA256SUMS",
        "gh release create",
        "--verify-tag",
        "--prerelease",
    ):
        assert required in body


def test_workflows_use_current_node_24_official_actions() -> None:
    for workflow in (CI, RELEASE_WORKFLOW):
        body = workflow.read_text(encoding="utf-8")
        assert "actions/checkout@v7.0.0" in body
        assert "actions/setup-python@v7.0.0" in body
        assert "actions/checkout@v4" not in body
        assert "actions/setup-python@v5" not in body


def test_readme_installs_the_published_release_wheel_without_a_source_checkout() -> None:
    body = README.read_text(encoding="utf-8")
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = project["tool"]["pyne-runtime"]["published-version"]
    wheel_url = (
        "https://github.com/helenananaa/pyne-runtime/releases/download/"
        f"v{version}/pyne_runtime-{version}-py3-none-any.whl"
    )

    assert wheel_url in body
    assert "currently distributed from source" not in body
    assert "SHA256SUMS" in body


def test_release_process_links_to_contract_docs() -> None:
    checklist = _markdown_h2_sections(RELEASE_DOC.read_text(encoding="utf-8"))[
        "Release Checklist"
    ]

    for required in (
        "../api/public_api.md",
        "pine_like_api_matrix.md",
        "schema_migrations.md",
        "../../CHANGELOG.md",
    ):
        assert f"]({required})" in checklist


def test_changelog_separates_unreleased_work_from_the_published_release() -> None:
    changelog = CHANGELOG.read_text(encoding="utf-8")
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    source_version = project["project"]["version"]
    published_version = project["tool"]["pyne-runtime"]["published-version"]
    headings = _markdown_h2_headings(changelog)
    sections = _markdown_h2_sections(changelog)

    assert re.fullmatch(
        r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)rc(?:0|[1-9]\d*)",
        source_version,
    )
    assert headings[0] == "Unreleased"
    if source_version == published_version:
        assert sections["Unreleased"] == ""
    else:
        assert re.search(r"^- ", sections["Unreleased"], flags=re.MULTILINE)

    current_release = re.fullmatch(
        rf"{re.escape(published_version)} - (\d{{4}}-\d{{2}}-\d{{2}})",
        headings[1],
    )
    assert current_release is not None
    date.fromisoformat(current_release.group(1))
    assert re.search(r"^- ", sections[headings[1]], flags=re.MULTILINE)

    assert "0.1.0" in headings
    assert "Initial standalone Pyne Runtime package scaffold" in sections["0.1.0"]


def test_released_changelog_records_package_maturity_contracts() -> None:
    changelog = CHANGELOG.read_text(encoding="utf-8")
    headings = _markdown_h2_headings(changelog)
    sections = _markdown_h2_sections(changelog)
    released_notes = "\n".join(sections[heading] for heading in headings[1:])

    for required in (
        "schema contracts",
        "schema migration policy",
        "release process guidance",
        "host integration guide",
        "package smoke coverage",
        "py.typed",
    ):
        assert required in released_notes


def test_pine_like_api_matrix_tracks_completed_capture_gates_by_row() -> None:
    body = PINE_LIKE_API_MATRIX.read_text(encoding="utf-8")
    sections = _markdown_h2_sections(body)
    request_row = _markdown_table_row(body, "Multi-context data")
    strategy_row = _markdown_table_row(body, "Strategy events")

    assert request_row[2] == "Partial"
    assert "21/21 captured fixtures with 0 diff" in request_row[3]
    assert "provider contract is exposed" in request_row[3].lower()
    assert strategy_row[2] == "Partial"
    assert "all 27 strategy pine-equivalent cases are TradingView parity-gated" in strategy_row[3]
    assert PROVIDER_CONTRACT_EXAMPLE.is_file()

    planned_gaps = sections["Planned Gaps"]
    assert "Host-facing request provider contract examples" not in planned_gaps
    assert "Additional request-context TradingView captures" not in planned_gaps


def test_full_check_scripts_use_repo_local_temp_root() -> None:
    powershell_body = CHECK_PS1.read_text(encoding="utf-8")
    shell_body = CHECK_SH.read_text(encoding="utf-8")

    for required in (
        ".pyne-check-tmp",
        "PYNE_CHECK_TMP",
        "no:cacheprovider",
        "--basetemp",
        "--no-isolation",
        "--offline",
    ):
        assert required in powershell_body
        assert required in shell_body

    assert "mktemp -d" in shell_body
    assert 'case "$CHECK_TMP" in' in shell_body
    assert '"$CHECK_TMP_ROOT"/run.*' in shell_body
    assert "trap cleanup EXIT" in shell_body
    assert 'rm -rf -- "$CHECK_TMP"' in shell_body
    assert 'rm -rf "$CHECK_TMP_ROOT"' not in shell_body


def test_local_and_ci_gates_share_the_core_command_contract() -> None:
    powershell_body = CHECK_PS1.read_text(encoding="utf-8")
    powershell_commands = _powershell_python_commands(powershell_body)
    shell_commands = _shell_commands(CHECK_SH.read_text(encoding="utf-8"))
    workflow_commands = _workflow_run_commands(CI.read_text(encoding="utf-8"))

    shell_python_commands = [command[1:] for command in shell_commands if command[0] == "$PYTHON"]
    ci_python_commands = [command[1:] for command in workflow_commands if command[0] == "python"]

    _assert_command_prefixes(powershell_commands, COMMON_PYTHON_GATE_PREFIXES)
    _assert_command_prefixes(shell_python_commands, COMMON_PYTHON_GATE_PREFIXES)
    _assert_command_prefixes(ci_python_commands, COMMON_PYTHON_GATE_PREFIXES)

    assert re.search(r"^\s*& git diff --check\s*$", powershell_body, flags=re.MULTILINE)
    assert ("git", "diff", "--check") in shell_commands
    assert ("git", "diff", "--check") in workflow_commands

    _assert_command_prefixes(powershell_commands, (("-m", "build", "--no-isolation"),))
    _assert_command_prefixes(shell_python_commands, (("-m", "build", "--no-isolation"),))
    _assert_command_prefixes(
        workflow_commands,
        (
            ("python", "-m", "build"),
            ("python", "-m", "twine", "check"),
            ("python", "scripts/package_smoke.py", "--dist-dir", "dist"),
        ),
    )
