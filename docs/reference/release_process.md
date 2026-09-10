# Release Process

Pyne Runtime is currently pre-1.0. Releases should still be predictable for
host applications and script authors, especially around root imports, schema
contracts, CLI behavior, and packaged typing metadata.

## Version Policy

- Patch releases should not break public root imports, documented CLI commands,
  or existing schema contracts.
- Minor releases may add public APIs, script namespace helpers, schema fields,
  and provider capabilities.
- Any breaking change must include a version bump appropriate to the affected
  contract, a changelog entry, migration documentation, and focused tests.
- Schema contracts use independent schema versions. A package version bump does
  not replace `schemaVersion` checks in host applications.

## Release Checklist

Before cutting a release candidate:

1. Confirm `pyproject.toml` and [CHANGELOG.md](../../CHANGELOG.md) describe
   the intended release.
2. Run the full quality gate:

   ```bash
   scripts/check.ps1
   ```

   On POSIX shells:

   ```bash
   scripts/check.sh
   ```

   The check scripts use per-run subdirectories under the repository-local
   ignored `.pyne-check-tmp` directory for pytest and build artifacts. Set
   `PYNE_CHECK_TMP` to override that temporary root.
   They build with `python -m build --no-isolation`, so run the release gate
   from an environment that already has the project dev dependencies installed.
   The package smoke step runs in offline mode, reusing local site packages for
   dependencies while installing the built Pyne wheel itself.

3. Confirm the package smoke gate installs the built wheel and checks:
   - `pyne_runtime/py.typed` is present;
   - `pyne_runtime` imports from the temporary wheel environment, not the
     repository `src` tree or an inherited `PYTHONPATH`;
   - `python -m pyne_runtime --version` works;
   - the installed console entry point runs `pyne --version`, `pyne schema`,
     and `pyne validate` successfully;
   - `pyne run` writes a successful result payload.
4. Confirm public API changes are reflected in:
   - [Public API](../api/public_api.md);
   - [Pine-Like API Matrix](pine_like_api_matrix.md), when script behavior
     changes;
   - [Schema Migrations](schema_migrations.md), when host-facing schema
     contracts change.
5. Confirm no unrelated generated files or local artifacts are staged.
6. Merge the release commit to `main` and confirm the `CI` workflow is green,
   including the nine installed-wheel jobs that consume the single built
   `pyne-runtime-dist` artifact.
7. Create and push an annotated tag that exactly matches `v` plus the package
   version. For example:

   ```bash
   git tag -a v0.4.0 -m "pyne-runtime 0.4.0"
   git push origin v0.4.0
   ```

8. Wait for `.github/workflows/release.yml` to finish, then verify the GitHub
   Release contains the wheel, source distribution, and `SHA256SUMS`.

## GitHub Release Assets

GitHub Releases are the host-application distribution channel. A release tag
must match `project.version` exactly and the tagged commit must be contained in
`main`; the release workflow fails closed when either condition is false.

The workflow builds once in a clean runner, checks both distributions with
Twine, and uploads a single `pyne-runtime-dist` artifact. Nine jobs then
download that same artifact and run `scripts/package_smoke.py --dist-dir dist`
on Linux, Windows, and macOS for Python 3.11, 3.12, and 3.13. The publish job
depends on every smoke job, downloads the same artifact without rebuilding, and
only then publishes:

- `pyne_runtime-<version>-py3-none-any.whl`;
- `pyne_runtime-<version>.tar.gz`;
- `SHA256SUMS` covering both artifacts.

Release notes come from the matching dated section in
[CHANGELOG.md](../../CHANGELOG.md). Versions containing `a`, `b`, `rc`, or
`dev` are marked as GitHub prereleases.

Host applications should pin the tag, exact wheel filename, and SHA-256 rather
than follow a moving `latest` URL. For example:

```bash
python -m pip install "https://github.com/helenananaa/pyne-runtime/releases/download/v0.4.0/pyne_runtime-0.4.0-py3-none-any.whl"
```

`project.version` identifies the source/build candidate. The latest actually
published GitHub Release is recorded separately as
`tool.pyne-runtime.published-version`; README install instructions must follow
that published value until the new tag and verified assets exist. During
development, new notes stay under `Unreleased`. The release commit moves them
into a dated section matching `project.version`. Keep `published-version` and
README installation links on the last verified release until the new tag's
assets actually exist and their hashes have been verified. Update that published
record and the README together in the post-publication documentation change;
preparing a candidate or pushing a tag does not by itself prove publication.

## Changelog Rules

Update [CHANGELOG.md](../../CHANGELOG.md) when a change affects any of these:

- public package-root imports;
- script-visible namespaces or helper behavior;
- CLI commands, flags, output shape, or exit codes;
- schema versions or schema fields;
- packaged examples or host integration fixtures;
- quality gates, build metadata, or release process.

Internal refactors with no public behavior change may be grouped, but should
still be mentioned when they affect maintenance or release risk.
