"""Smoke test an installed Pyne Runtime wheel in an isolated virtualenv."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dist-dir",
        required=True,
        help="Directory containing built pyne_runtime wheel artifacts.",
    )
    parser.add_argument(
        "--repo-root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Repository root containing examples used by the smoke test.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter used to create the temporary virtualenv.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Create the smoke virtualenv with system site packages and install "
            "the wheel without resolving dependencies from an index."
        ),
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    wheel = _find_wheel(Path(args.dist_dir))

    with tempfile.TemporaryDirectory(prefix="pyne-runtime-smoke-") as tmp:
        tmp_path = Path(tmp)
        venv_dir = tmp_path / "venv"
        clean_env = _sanitized_env()
        if args.offline:
            clean_env = _offline_env(clean_env)
        _run(
            _venv_create_command(args.python, venv_dir, offline=args.offline),
            cwd=tmp_path,
            env=clean_env,
        )
        python = _venv_python(venv_dir)
        if not args.offline:
            _run(
                [str(python), "-m", "pip", "install", "--upgrade", "pip"],
                cwd=tmp_path,
                env=clean_env,
            )
        _run(
            _wheel_install_command(python, wheel, offline=args.offline),
            cwd=tmp_path,
            env=clean_env,
        )

        _run(_type_marker_check_command(python), cwd=tmp_path, env=clean_env)
        _run(
            _wheel_import_check_command(python, venv_dir, repo_root),
            cwd=tmp_path,
            env=clean_env,
        )
        _run(
            [str(python), "-m", "pyne_runtime", "--version"],
            cwd=tmp_path,
            env=clean_env,
        )
        pyne = _venv_console_script(venv_dir)
        _run([str(pyne), "--version"], cwd=tmp_path, env=clean_env)
        schema = _run_json(
            [str(pyne), "schema"],
            cwd=tmp_path,
            env=clean_env,
        )
        if schema["output"]["schemaVersion"] != 2:
            raise RuntimeError("unexpected output schema version")
        source_schema = _run_json(
            [str(python), "-m", "pyne_runtime", "schema"],
            cwd=repo_root,
            env=_source_schema_env(clean_env, repo_root),
        )
        if schema != source_schema:
            raise RuntimeError("installed-wheel schema does not match repository source")

        script = repo_root / "examples" / "host_output_contract.py"
        ohlcv = repo_root / "examples" / "sample_ohlcv.csv"
        _run([str(pyne), "validate", str(script)], cwd=tmp_path, env=clean_env)
        _run(
            [str(pyne), "inspect", str(script), "--runtime-mode", "batch"],
            cwd=tmp_path,
            env=clean_env,
        )

        out = tmp_path / "result.json"
        _run([
            str(pyne),
            "run",
            str(script),
            "--ohlcv",
            str(ohlcv),
            "--executor-mode",
            "inline",
            "--out",
            str(out),
        ], cwd=tmp_path, env=clean_env)
        payload = json.loads(out.read_text(encoding="utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(f"smoke run failed: {payload.get('error')}")
        if "signals" not in payload.get("output", {}):
            raise RuntimeError("smoke run did not emit host signal output")

        _run(
            _installed_acceptance_command(python, repo_root, venv_dir),
            cwd=tmp_path,
            env=clean_env,
        )

    return 0


def _find_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.resolve().glob("pyne_runtime-*.whl"))
    if not wheels:
        raise FileNotFoundError(f"No pyne_runtime wheel found in {dist_dir}")
    return wheels[-1]


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_console_script(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "pyne.exe"
    return venv_dir / "bin" / "pyne"


def _venv_create_command(python: str, venv_dir: Path, *, offline: bool) -> list[str]:
    command = [python, "-m", "venv"]
    if offline:
        command.append("--system-site-packages")
    command.append(str(venv_dir))
    return command


def _wheel_install_command(python: Path, wheel: Path, *, offline: bool) -> list[str]:
    command = [str(python), "-m", "pip", "install"]
    if offline:
        command.append("--no-deps")
    command.append(str(wheel))
    return command


def _type_marker_check_command(python: Path) -> list[str]:
    return [
        str(python),
        "-c",
        (
            "from importlib.resources import files; "
            "raise SystemExit(0 if files('pyne_runtime').joinpath('py.typed').is_file() else 1)"
        ),
    ]


def _installed_acceptance_command(
    python: Path,
    repo_root: Path,
    venv_dir: Path,
) -> list[str]:
    helper = repo_root / "scripts" / "installed_runtime_acceptance.py"
    return [
        str(python),
        str(helper),
        "--repo-root",
        str(repo_root),
        "--expected-prefix",
        str(venv_dir.resolve()),
    ]


def _wheel_import_check_command(
    python: Path,
    venv_dir: Path,
    repo_root: Path,
) -> list[str]:
    return [
        str(python),
        "-c",
        (
            "from pathlib import Path\n"
            "import pyne_runtime\n"
            "module = Path(pyne_runtime.__file__).resolve()\n"
            f"venv = Path({str(venv_dir.resolve())!r})\n"
            f"source = Path({str((repo_root / 'src').resolve())!r})\n"
            "if not module.is_relative_to(venv):\n"
            "    raise SystemExit(f'wheel import escaped smoke venv: {module}')\n"
            "if module.is_relative_to(source):\n"
            "    raise SystemExit(f'wheel smoke imported repository source: {module}')\n"
        ),
    ]


def _sanitized_env(source: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    for key in ("PYTHONHOME", "PYTHONOPTIMIZE", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    return env


def _source_schema_env(clean_env: dict[str, str], repo_root: Path) -> dict[str, str]:
    env = dict(clean_env)
    env["PYTHONPATH"] = str((repo_root / "src").resolve())
    return env


def _offline_env(clean_env: dict[str, str]) -> dict[str, str]:
    env = dict(clean_env)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, cwd=cwd, env=env)


def _run_json(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("expected JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
