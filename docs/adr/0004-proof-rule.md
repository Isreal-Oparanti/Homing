# ADR 0004: Proof rule. Models propose, code decides

**Status:** accepted · 30 Oct 2026

## Context
Models are probabilistic and sometimes produce confident nonsense, even with full context. Our product's value is that what it shows can be trusted. A wrong ✓ is worse than no answer.

## Decision
- Every fact shown as checked must come with a quote that code finds in a stored source snapshot (exact, or fuzzy ≥ 92 for quotes ≥ 12 characters).
- Dates are parsed by code from the verified quote text, not taken from the model's interpretation.
- Verdict labels are computed by code from verified findings and the profile.
- Unverifiable means silence ("couldn't confirm"), never a guess.

## Consequences
- We'll sometimes show less than the model "knows". That's intended.
- `verify/` is pure, heavily tested code.
