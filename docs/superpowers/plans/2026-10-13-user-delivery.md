# User delivery implementation plan

> For agentic workers: execute these independently testable tasks with test-driven development and review each result before integration.

**Goal:** Make reports easier to follow, require traceable issue closure, and provide a durable continuation entry point.

**Architecture:** Keep the existing SQLite ledger, CLI and evidence identity. Add bounded delivery metadata through `import-records`, render a fixed `handoff.md` in the same atomic export generation, and preserve old records while identifying unsupported closure claims.

**Tech Stack:** Python 3.10+, unittest, SQLite, existing FFmpeg/NumPy/Pillow tooling.

**Spec:** The user-approved review of 2026-10-13, items 1–3: readable report, justified issue closure, persistent continuation. Cross-video evidence and candidate-planning changes are deferred.

## Global constraints

- Preserve source media, existing ledgers, historical validation, schema 3 and strict/layered evidence boundaries.
- Work in the development directory, preserving the pre-change snapshot; synchronize only reviewed files to the Git copy.
- No commit, push, release, new dependency, paid model API or source-video instruction execution.
- Full evidence remains accessible; imported subtitles are not proof of listening to narration.
- Reproduction is separate from review completion and must become stale after relevant content changes.

## Task 1: readable report

Files: `scripts/vor_report.py`, `scripts/tests/test_delivery_layout.py`.

- [x] Add and run failing tests: all numbered operation summaries precede the first image, every asset remains linked, details contain the full evidence, and unsafe Markdown remains escaped.
- [x] Add a continuous instruction list and collapsible full evidence per step.
- [x] Accept `report['delivery_summary']` lines and link the fixed `handoff.md`.
- [x] Rerun report and new layout tests.

## Task 2: justified issue closure

Files: `scripts/vor_record_contract.py`, `scripts/tests/test_issue_resolution.py`, integration in store and audit modules.

- [x] Reproduce acceptance of an unjustified resolved issue with a failing import test.
- [x] Require new resolved imports to identify reviewer, reason and evidence, or an explicit reasoned withdrawal basis.
- [x] Preserve readable legacy records; expose `issue_is_resolved(issue)` and treat old unsupported closures as pending in reports and completion checks.
- [x] Test batch rollback, nested evidence checks and legacy readability.

## Task 3: delivery context and continuation

Files: new `scripts/vor_delivery.py`, `scripts/tests/test_delivery_context.py`; integrate `vor_store.py`, `vor_export.py`, `vor_language.py` and export tests.

- [x] Add red tests for context round trip, language-use distinction, content-bound reproduction, handoff generation and rollback.
- [x] `delivery_context` stores `question`, `scope`, `next_action`, and `used_language_source_ids` through the existing import transaction and history.
- [x] `reproduction_checks` stores authored outcomes with reviewer, scope, environment, result, step IDs, current content snapshot and hashed files inside the review directory. It records an assertion, not automated semantic verification.
- [x] Export context and check freshness; generate `handoff.md` alongside the four existing delivery files and include it in the manifest/rollback sequence.
- [x] `status` exposes the content snapshot used for explicit reproduction binding. `tracks` persists its actual probe result so no-audio and unchecked are distinguishable.
- [x] Verify an interrupted five-file export preserves its old generation.

## Integration and acceptance

- [x] Update Chinese documentation, then matching English README; provide exact import examples and version compatibility boundaries.
- [x] Run focused tests, then all unittests on the available Python 3.12 and 3.10 environments.
- [x] Re-export a copied real review and check report links, original evidence identity and unresolved items.
- [x] In a fresh agent context, provide only the review directory; verify recovery of the question, scope and next action without rebuilding the index.
- [x] Use a separate agent to follow a frozen delivery and save the observed result; distinguish recorded reproduction from independent human acceptance.
- [x] Review changed files independently, synchronize approved files to the publishing copy, and check parity without publishing.
