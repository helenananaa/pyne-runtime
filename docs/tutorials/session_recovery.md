# Recovering an incremental session

Choose recovery based on what information you retained. A checkpoint records
committed state; an active preview is not a durable checkpoint.

| Situation | Recovery |
| --- | --- |
| Same script/settings and compatible semantics, portable typed-state snapshot | Restore state-v2, reattach the host provider if required, then submit the next uncommitted bar |
| Complete bounded closed history, script independent of preview visitation | Replay-v1 can rebuild that closed-bar computation |
| `PYNE_SNAPSHOT_SEMANTICS_MISMATCH` | Start a new session and recompute from authoritative host OHLCV under the new semantics |
| Missing/corrupt snapshot, different script or settings | Diagnose the specific error; do not treat every failure as a semantics upgrade |
| Provider/callback failure poisons a live session | Recover the last known committed checkpoint with a healthy provider; do not retry commits on the poisoned object |

Do not change a snapshot's semantics version or checksum to force an upgrade.
The package version and the snapshot wire-format version are separate from
computation semantics. See [Schema Migrations](../reference/schema_migrations.md).

## Rebuilding after a semantics upgrade

The host supplies the original script, settings, parameters, and authoritative
OHLCV. Keep these identities with the checkpoint. For a history within the
configured seed limit, the recovery sequence is:

```python
import pyne_runtime as pn

try:
    session = pn.PyneIncrementalSession.from_portable_snapshot(
        checkpoint_bytes, script=script, settings=settings
    )
except pn.PynePortableSnapshotError as error:
    if error.code != "PYNE_SNAPSHOT_SEMANTICS_MISMATCH":
        raise
    session = pn.PyneIncrementalSession(
        script=script, settings=settings, params=params
    )
    session.seed(authoritative_closed_bars)

# Checkpoint the newly computed state before proceeding with new input.
replacement_checkpoint = session.snapshot_portable_state()
```

The host persists `replacement_checkpoint` atomically using its own storage.
Successful restore uses the parameters embedded in the snapshot; `params` in
the rebuild branch must be the host's original parameter values.
For history exceeding the seed limit, seed a permitted prefix and advance the
remaining closed bars through `on_bar_closed()` in timestamp order. Do not
truncate the input merely to fit the seed limit: recursive indicators can depend
on earlier input. A semantic upgrade can intentionally change historical output;
rebuilding is not a promise to reproduce an old implementation's results.

## Preview visitation cannot be reconstructed from OHLCV

A script may branch on `ctx.barstate.isnew` or otherwise depend on visits within
one bar. Suppose it increments a committed counter only when `isnew` is true:
after two seeded closes, previewing then confirming the third bar produces
counts `[1, 2, 2]`. State-v2 preserves these committed counts, including across a
process restart. Replay-v1 sees three closed bars and produces `[1, 2, 3]`.
The next close produces `3` and `4` respectively.

This difference is expected under the declared lifecycle. Comparing only output
schemas or excluding `isnew` metadata cannot establish calculation equivalence.
Use compatible state-v2 for this committed state. After an incompatible upgrade,
OHLCV alone cannot recover the original preview visitation: rebuilding starts
closed-bar semantics, which the host must disclose. Reproducing the original
event-sensitive history requires authoritative event input and an explicitly
supported replay procedure; this guide does not supply one.

## Executable acceptance

From a source checkout with development dependencies:

```bash
python -m pytest -q tests/test_recovery_workflows.py
```

The suite compares fresh-process state-v2 continuation with independent counter
values, explicitly demonstrates replay-v1's different values, and loads real
historical snapshots from `64eb354` without modifying them. After their rejection,
it rebuilds the fixture's EMA from the OHLCV specified in its provenance, checks
the current captured seed rule and recursive arithmetic, then checks new
same-version snapshots continue correctly. These are host-neutral acceptance
tests, not proof of recovery for arbitrary user state or distributed hosts.
