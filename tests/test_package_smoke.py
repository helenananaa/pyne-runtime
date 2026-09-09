from __future__ import annotations

import os
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "package_smoke.py"


def test_package_smoke_help() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--dist-dir" in result.stdout
    assert "--repo-root" in result.stdout
    assert "--offline" in result.stdout


def test_package_smoke_finds_built_wheel(tmp_path: Path) -> None:
    module = _load_package_smoke()
    old_wheel = tmp_path / "pyne_runtime-0.1.0-py3-none-any.whl"
    new_wheel = tmp_path / "pyne_runtime-0.2.0-py3-none-any.whl"
    old_wheel.write_text("", encoding="utf-8")
    new_wheel.write_text("", encoding="utf-8")

    assert module._find_wheel(tmp_path) == new_wheel


def test_package_smoke_checks_installed_type_marker() -> None:
    module = _load_package_smoke()

    command = module._type_marker_check_command(Path("python"))

    assert command[:2] == ["python", "-c"]
    assert "py.typed" in command[2]
    assert "pyne_runtime" in command[2]


def test_package_smoke_offline_commands_reuse_local_dependencies() -> None:
    module = _load_package_smoke()
    wheel = Path("dist/pyne_runtime-0.1.0-py3-none-any.whl")

    assert module._venv_create_command(
        "python",
        Path("venv"),
        offline=True,
    ) == ["python", "-m", "venv", "--system-site-packages", "venv"]
    assert module._wheel_install_command(
        Path("python"),
        wheel,
        offline=True,
    ) == [
        "python",
        "-m",
        "pip",
        "install",
        "--no-deps",
        str(wheel),
    ]


def test_package_smoke_sanitizes_source_import_environment() -> None:
    module = _load_package_smoke()

    env = module._sanitized_env({
        "PATH": "bin",
        "PYTHONPATH": "repo/src",
        "PYTHONHOME": "host-python",
        "PYTHONOPTIMIZE": "2",
        "VIRTUAL_ENV": "repo/.venv",
    })

    assert env["PATH"] == "bin"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONSAFEPATH"] == "1"
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert "PYTHONOPTIMIZE" not in env
    assert "VIRTUAL_ENV" not in env


def test_package_smoke_uses_repo_source_only_for_schema_identity() -> None:
    module = _load_package_smoke()
    clean_env = module._sanitized_env({"PATH": "bin", "PYTHONPATH": "outside"})

    source_env = module._source_schema_env(clean_env, ROOT)

    assert "PYTHONPATH" not in clean_env
    assert source_env["PYTHONPATH"] == str((ROOT / "src").resolve())
    assert source_env["PYTHONNOUSERSITE"] == "1"


def test_package_smoke_offline_environment_disables_index_access() -> None:
    module = _load_package_smoke()

    env = module._offline_env(module._sanitized_env({"PATH": "bin"}))

    assert env["PIP_NO_INDEX"] == "1"
    assert env["PIP_DISABLE_PIP_VERSION_CHECK"] == "1"


def test_package_smoke_checks_wheel_import_location(tmp_path: Path) -> None:
    module = _load_package_smoke()

    command = module._wheel_import_check_command(
        Path("python"),
        tmp_path / "venv",
        ROOT,
    )

    assert command[:2] == ["python", "-c"]
    assert "pyne_runtime.__file__" in command[2]
    assert "wheel import escaped smoke venv" in command[2]
    assert repr(str((ROOT / "src").resolve())) in command[2]
    assert "assert " not in command[2]
    assert "raise SystemExit" in command[2]


def test_package_smoke_import_check_cannot_be_disabled_by_optimization(
    tmp_path: Path,
) -> None:
    module = _load_package_smoke()
    outside = tmp_path / "outside"
    package = outside / "pyne_runtime"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    command = module._wheel_import_check_command(
        Path(sys.executable),
        tmp_path / "venv",
        tmp_path / "repo",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(outside)
    env["PYTHONOPTIMIZE"] = "2"

    completed = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "wheel import escaped smoke venv" in completed.stderr


def test_installed_acceptance_rejects_escaped_import_under_optimize(
    tmp_path: Path,
) -> None:
    helper = ROOT / "scripts" / "installed_runtime_acceptance.py"
    outside = tmp_path / "outside"
    package = outside / "pyne_runtime"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("code = 'escaped'\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(outside)
    env["PYTHONOPTIMIZE"] = "1"
    env.pop("PYTHONHOME", None)

    completed = subprocess.run(
        [
            sys.executable,
            str(helper),
            "--repo-root",
            str(ROOT),
            "--expected-prefix",
            str(tmp_path / "venv"),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    combined = completed.stderr + completed.stdout
    assert "acceptance import escaped expected prefix" in combined
    assert "assert " not in helper.read_text(encoding="utf-8").split("def _require_installed_origin")[1].split("def ")[0]


def test_package_smoke_invokes_installed_acceptance_with_wheel_python(
    tmp_path: Path,
) -> None:
    module = _load_package_smoke()
    python = tmp_path / "venv" / "Scripts" / "python.exe"
    command = module._installed_acceptance_command(python, ROOT, tmp_path / "venv")

    assert command[0] == str(python)
    assert command[1] == str(ROOT / "scripts" / "installed_runtime_acceptance.py")
    assert command[2:6] == [
        "--repo-root",
        str(ROOT),
        "--expected-prefix",
        str((tmp_path / "venv").resolve()),
    ]


def test_package_smoke_resolves_console_entry_point(tmp_path: Path) -> None:
    module = _load_package_smoke()

    path = module._venv_console_script(tmp_path / "venv")

    if sys.platform == "win32":
        assert path == tmp_path / "venv" / "Scripts" / "pyne.exe"
    else:
        assert path == tmp_path / "venv" / "bin" / "pyne"


def test_write_offline_parent_site_pth_exposes_deps_without_parent_hooks(
    tmp_path: Path,
) -> None:
    module = _load_package_smoke()
    parent_site = tmp_path / "parent-site"
    parent_site.mkdir()
    (parent_site / "offline_dep.py").write_text("marker = 'parent-dep'\n", encoding="utf-8")
    parent_pkg = parent_site / "pyne_runtime"
    parent_pkg.mkdir()
    (parent_pkg / "__init__.py").write_text("origin = 'parent'\n", encoding="utf-8")
    sentinel = tmp_path / "parent-hook-sentinel"
    (parent_site / "parent_hook.pth").write_text("import parent_hook\n", encoding="utf-8")
    (parent_site / "parent_hook.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('hooked', encoding='utf-8')\n",
        encoding="utf-8",
    )

    venv_dir = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    child_python = module._venv_python(venv_dir)
    child_purelib, _child_platlib = module._query_sysconfig_paths(
        child_python,
        env=module._sanitized_env(),
    )
    child_pkg = child_purelib / "pyne_runtime"
    child_pkg.mkdir(parents=True)
    (child_pkg / "__init__.py").write_text("origin = 'child'\n", encoding="utf-8")

    written = module._write_offline_parent_site_pth(
        parent_purelib=parent_site,
        parent_platlib=parent_site,
        child_purelib=child_purelib,
        venv_dir=venv_dir,
    )
    assert written is not None
    assert written.is_relative_to(venv_dir)
    assert written.read_text(encoding="utf-8") == f"{parent_site.resolve()}\n"

    completed = subprocess.run(
        [
            str(child_python),
            "-c",
            (
                "import offline_dep, pyne_runtime\n"
                "print(offline_dep.marker)\n"
                "print(pyne_runtime.origin)\n"
                "print(pyne_runtime.__file__)\n"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=module._sanitized_env(),
        cwd=tmp_path,
    )
    lines = completed.stdout.splitlines()
    assert lines[0] == "parent-dep"
    assert lines[1] == "child"
    assert Path(lines[2]).resolve().is_relative_to(venv_dir.resolve())
    assert not sentinel.exists()


def test_write_offline_parent_site_pth_rejects_newline_paths(tmp_path: Path) -> None:
    module = _load_package_smoke()
    child_purelib = tmp_path / "venv" / "site-packages"
    child_purelib.mkdir(parents=True)
    parent = tmp_path / "parent\nsite"

    try:
        module._write_offline_parent_site_pth(
            parent_purelib=parent,
            parent_platlib=parent,
            child_purelib=child_purelib,
            venv_dir=tmp_path / "venv",
        )
    except RuntimeError as exc:
        assert "newline" in str(exc)
    else:
        raise AssertionError("expected newline path rejection")


def test_write_offline_parent_site_pth_rejects_child_outside_venv(tmp_path: Path) -> None:
    module = _load_package_smoke()
    try:
        module._write_offline_parent_site_pth(
            parent_purelib=tmp_path / "parent",
            parent_platlib=tmp_path / "parent",
            child_purelib=tmp_path / "other" / "site-packages",
            venv_dir=tmp_path / "venv",
        )
    except RuntimeError as exc:
        assert "outside smoke venv" in str(exc)
    else:
        raise AssertionError("expected child purelib rejection")


def test_query_sysconfig_paths_uses_supplied_python(tmp_path: Path, monkeypatch) -> None:
    module = _load_package_smoke()
    recorded: list[str] = []

    def fake_run(command, **kwargs):
        recorded.extend(command[:1])
        class Result:
            stdout = '{"purelib": "P", "platlib": "L"}'
        return Result()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    python = tmp_path / "override" / "python"
    purelib, platlib = module._query_sysconfig_paths(
        python,
        env=module._sanitized_env({"PATH": "bin"}),
    )
    assert recorded == [str(python)]
    assert purelib == Path("P").resolve()
    assert platlib == Path("L").resolve()


def _load_package_smoke() -> ModuleType:
    spec = spec_from_file_location("package_smoke", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
