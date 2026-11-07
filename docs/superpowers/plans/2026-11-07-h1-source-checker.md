# H1 source checker implementation plan

Scope: authorized incremental implementation for issue #25 on the supplied
isolated branch at baseline `959d6ca`. No kernel or host changes.

Design: extend the existing gate with optional `--source-tree PATH`. Keep the
version-1 JSON contract and default output unchanged. Add a separate versioned
source observation report only when requested. Read three fixed regular files,
fingerprint bytes, strip comments/literals, inspect named function definitions
and driver/PM initializers, and compare the SMP2P proposal's restore shape.
An absent hook is a file-local lexical observation, not proof of absent PM.
Always deny admission; PAS lifecycle and C7-style equivalence remain unproven.

Alternatives: changing the strict contract would break existing consumers;
substring-only checking would confuse comments/prototypes/unbound callbacks
with implementation. A compiler/preprocessor would require executing tree
content or toolchain configuration. Use bounded stdlib lexical inspection and
explicitly report its limits instead.

- [x] Add synthetic source fixtures and CLI tests for missing/patched SMP2P,
  disconnected hooks, API drift, misleading comments, PAS PM changes, invalid
  paths/encoding and read-only behavior; observe RED.
- [x] Implement optional source inspection and reason codes; observe GREEN.
- [x] Document exact expectations, safe compensation prerequisites, provenance
  limits, unknown Dell behavior and unchanged contract.
- [x] Run full unittest discovery, shell syntax and diff checks; review diff;
  commit locally, with no push/merge.

Review focus: no implicit source discovery; missing or ambiguous input cannot
be evidence of absence; conditionals/macros are not compiled; matching hooks
cannot reconcile firmware/software state; source bytes must remain unchanged.

Verification: initial CLI RED produced 17 assertion failures because the new
option did not exist; the first focused GREEN passed 13 tests. Added PAS phase
coverage then passed in a full run of 156 tests (one skipped). A subsequent
return-type mutation exposed a void callback falsely matching the restore shape;
the checker now requires the proposal's static int declaration. The final local
full-suite attempt was interrupted amid sandbox resource failures; the integrator
independently reports **157 tests OK (one skipped)** on the final implementation.
Source non-mutation is covered by byte-for-byte before/after comparison of every
fixture-tree file, including the matching restore case; contract bytes are also
checked by the original suite. Bash syntax passed before the final Python-only
fix. Final diff whitespace check passed. Review was performed locally; actual
Ubuntu source and Dell runtime validation remain for the XPS integrator.
