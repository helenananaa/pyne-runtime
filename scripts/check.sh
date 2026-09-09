#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
  elif [ -f "$ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON="$ROOT/.venv/Scripts/python.exe"
  else
    PYTHON="python"
  fi
fi
CHECK_TMP_ROOT="${PYNE_CHECK_TMP:-$ROOT/.pyne-check-tmp}"
mkdir -p "$CHECK_TMP_ROOT"
CHECK_TMP_ROOT="$(CDPATH= cd -- "$CHECK_TMP_ROOT" && pwd)"
CHECK_TMP="$(mktemp -d "$CHECK_TMP_ROOT/run.XXXXXX")"
PYTEST_TMP="$CHECK_TMP/pytest"
DIST="$CHECK_TMP/dist"

cleanup() {
  case "$CHECK_TMP" in
    "$CHECK_TMP_ROOT"/run.*) rm -rf -- "$CHECK_TMP" ;;
    *)
      echo "refusing to clean unexpected check temp directory: $CHECK_TMP" >&2
      return 1
      ;;
  esac
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$ROOT"
mkdir -p "$PYTEST_TMP"
export TMPDIR="$CHECK_TMP"
"$PYTHON" -m compileall src tests -q
"$PYTHON" -m ruff check .
"$PYTHON" scripts/project_status.py --check
git diff --check
"$PYTHON" -m pytest -p no:cacheprovider --basetemp "$PYTEST_TMP/run"
"$PYTHON" scripts/performance_smoke.py --check
"$PYTHON" scripts/incremental_stability_smoke.py --check
"$PYTHON" scripts/strategy_capture_scaffold.py --check
"$PYTHON" scripts/strategy_capture_diff.py --assertion parity
"$PYTHON" scripts/ta_capture_diff.py --assertion parity
"$PYTHON" scripts/request_capture_diff.py --assertion parity
"$PYTHON" -m build --no-isolation --outdir "$DIST"
"$PYTHON" -m twine check "$DIST"/*
"$PYTHON" scripts/package_smoke.py --dist-dir "$DIST" --offline
