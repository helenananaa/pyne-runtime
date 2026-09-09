# ADX and DI migration

This directory is a standalone Pyne translation of BeikabuOyaji **ADX and DI**.

- Public script: https://www.tradingview.com/script/VTPMMOrx-ADX-and-DI/
- License of the original and of `capture.pine`, `naive.py`, `batch.py`, and `incremental.py`: **Mozilla Public License 2.0** (`https://mozilla.org/MPL/2.0/`). Attribution: © BeikabuOyaji.
- The `pyne-runtime` package license (MIT) does **not** relicense these derivative scripts. They stay MPL-2.0 and are tests-only; they are not copied into the installed wheel or runtime sources.

## Recurrence (not `ta.dmi` / `ta.adx`)

TradingView built-in DMI/ADX uses a different seed. This case keeps the original custom recurrence:

- previous high / low / close use `nz(..., 0)`
- Wilder-like sums start at `0`
- `Smoothed := nz(prev) - nz(prev)/len + current`
- `DX` then `SMA(len)`
- defaults: `len=14`, threshold `th=20`

## Files

| File | Role |
| --- | --- |
| `capture.pine` | Namespaced Pine v5 source used for parent TradingView capture |
| `tradingview.json` | Parent-captured 80-row JSON (OHLCV, time, DI+/DI-/ADX) |
| `tradingview.txt` | Parent-captured Pine log dump for the same bars |
| `naive.py` | First Python transliteration with series `if` / ternary (migration hints) |
| `batch.py` | Corrected batch script (explicit bar-index loop, `PyneSeries` plots) |
| `incremental.py` | Corrected incremental script (`ctx.state` `.value`, `ctx.ta.sma`) |

## Capture status

Parent capture is present as `tradingview.json` and `tradingview.txt` (80 real market rows, OHLCV + time). Do not rewrite those files. Synthetic OHLCV in tests is smoke-only and is not external parity evidence. Root separately enforces raw capture identities and prefix/restart capture equality.

The maintainer captured these rows through Chrome on 2026-09-09, verified source
text against `capture.pine`, and preserved raw Logs before parsing JSON.
See [acceptance and reproduction](../../../docs/development/adx_migration_acceptance_zh.md).
Incremental renders the original threshold as a constant `Threshold` plot because
its supported surface has no `hline`; batch retains `hline`. The reference value
is preserved, while renderer object type and line style are explicitly different.
The full license is in [LICENSE](LICENSE).
