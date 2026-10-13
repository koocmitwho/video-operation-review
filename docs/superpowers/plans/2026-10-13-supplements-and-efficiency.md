# Supplemental evidence and focused review implementation plan

**Goal:** Complete the approved cross-recording evidence and efficiency improvements, then publish a verified prerelease including the prior delivery improvements.

**Architecture:** Keep one ledger per video. Explicitly import immutable, verified snapshots of selected full images from another complete export; require a new local image-tool viewing record before citing them in an issue's followup. The original issue and original-video completion gates remain separate. Prioritize existing candidate requests through a read-only question queue and accelerate the exact RGB difference kernel without changing any frame metric or candidate.

**Tech Stack:** Existing Python 3.10+, SQLite, NumPy, Pillow and FFmpeg; no new dependency.

**Spec:** User-approved items 4 and 5 and explicit instruction to publish after completion, 2026-10-13.

## Constraints

- Develop only in the canonical tree; preserve the already implemented items 1–3 and all historical results.
- Imported snapshots retain source SHA-256, export generation, original frame/image identity and local re-view provenance; never credit them as original-video coverage.
- Importing another recording does not demonstrate a shared session, object or causal chain. The reviewer states the supported later claim and the original-record limitation.
- No fixed whole-review frame cap, no overview-as-native conversion, no relaxed completion gate, no source-video publication.
- Publish a new prerelease, preserving old tags/assets and the three local-only historical receipts.

## Tasks

- [ ] Add failing tests, then `vor_supplements.py`: complete-export verification, bounded portable snapshots, immutable IDs, local viewing, integrity diagnostics, traversal/link refusal and failure atomicity.
- [ ] Add failing integration tests, then CLI `supplement-import` / `supplement-view` / `supplements`; validate an issue `followup` with `claim`, `original_record_limit`, `reviewer` and `supplement_refs`.
- [ ] Bind nonempty supplement metadata into review/replay snapshots; render later-source claims separately and preserve the original gap.
- [ ] Add failing queue tests, then CLI `queue`: pending native/full candidates only, original-request PTS priority, dynamic batches without offsets or loss of remaining candidates.
- [ ] Diagnose and test exact RGB metric equivalence and bounded memory, then optimize only the identified channel-difference kernel.
- [ ] Run at least two isolated sequential real-video timing pairs and compare all frame fields, segments and candidates. Report machine timing separately from actual visual work.
- [ ] Perform actual image-tool viewing of a selected imported snapshot, record its reference, export the followup and verify original ledger counters and gap remain intact.
- [ ] Update Chinese and English documentation, version and RC scope; run focused and full Windows Python 3.10/3.12 regression.
- [ ] Independently inspect the final package boundary; synchronize byte-for-byte, stage only audited files, commit and push normally.
- [ ] Verify main and tag CI matrices, create a draft prerelease with commit-bound ZIP/manifests, download and test the installed package, then publish and anonymously verify the assets.
