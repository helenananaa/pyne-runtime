# Incremental callback dispatch

Ordinary Python functions now obtain their argument layout from their current
code object instead of constructing an `inspect.Signature` for every bar. This
applies to incremental callbacks in standalone and embedded use alike.

Functions with `__signature__`, `__wrapped__`, or `__text_signature__`, bound
methods, partials and other callable objects retain the reflection path. Code
replacement is observed on the next call. Existing handling of positional,
variadic and keyword-only arguments is preserved, including call errors.

There is no new public API, callback state, cache or snapshot field. Incremental
semantics identity remains unchanged. The standalone runtime still contains no
host matching, process deadline or CandleScope policy.

`tests/test_callback_arity_fastpath.py` verifies dispatch equivalence, dynamic code
replacement, decorated/overridden signatures, partials and keyword-only errors.
Canonical scalar OHLCV payloads also use an isolated shallow dictionary copy;
payloads containing nested metadata, custom values or custom keys retain deep
copying. This removes redundant recursive traversal of immutable numbers while
preserving snapshot and request history isolation.

These optimizations reduce per-callback overhead; they do not turn repeated
historical-prefix evaluations into incremental execution.
