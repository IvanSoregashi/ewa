# EPUB architecture TODO

Work is ordered by dependency and intended execution. Complete one migration step per
reviewable change while keeping affected callers working. The next step is **4**.
Design contracts and open decisions are in [EPUB_SPECIFICATION.md](EPUB_SPECIFICATION.md);
working conventions and validation commands are in [AGENTS.md](../AGENTS.md).

## Completed foundation

- [x] Fix failed ZIP session cleanup and subsequent reads.
- [x] Fix single-file ZIP extraction destinations, timestamps, and duplicated member paths; add synthetic regression tests.
- [x] Introduce EpubPackage with OPF/container discovery, editing, and export flushing.
- [x] Create a missing container for a unique OPF; verify relocation and export/reopen.
- [x] Make resource rename re-key the index and preserve original source information.
- [x] Define and test relocation path/URL validation and resolve manifest hrefs relative to the OPF.
- [x] Consolidate inventory ownership, deletion, manifest synchronization, and selection membership.
- [x] Remove the EpubManifest wrapper and retire EpubCore pending separate core/chapter design.
- [x] Move workflow recipes, operation protocols, eligibility policies, and persisted outcome codes into the plugin.

## Shared processing context migration

### 1. Finish the library/plugin boundary

- [x] Move configured verification classes and their tests into the plugin; keep reusable parsing/editing functions in the library.
- [x] Consolidate verification protocols and immutable VerificationResult in the plugin; preserve configured skip reasons and numeric values.
- [x] Remove obsolete EPUB verification entry points and duplicate library/plugin protocol inheritance.
- [x] Verify library code/tests do not import the plugin and checks work in an ordered loop.

### 2. Introduce a small per-book context

- [x] Add ProcessingContext with live EPUB, original information, replacements, and one unsaved SQLModel analytics list.
- [x] Document per-book ownership, sequential use, and empty replacements meaning no work.
- [x] Reuse EpubOperationResult for success/skip/error outcomes retaining diagnostics and analytics without live resources or rollback.
- [x] Test independent contexts, outcomes, and local serialization while keeping the legacy recipe working.

### 3. Add context lifetime management and automatic outcomes

- [x] Enter an empty context and call `open_epub(path)` inside its block to construct/open the EPUB and capture original information. Convert setup failures to outcomes with the input path and no invented metadata; reliably release acquired sources.
- [x] Add the minimal check entry point: consume each check result, immediately stop on failure, and produce a skip with the configured reason and details. Update protocol documentation to remove warn/repair decision policies.
- [x] Automatically convert processing exceptions into error outcomes while retaining earlier evidence and propagating interrupts. Require explicit success after export/output validation; define behavior for missing completion.
- [x] Test source lifetime/cleanup, short-circuiting, construction/opening/metadata/processing failures, partial outcome reporting/serialization, retained evidence, interrupts, explicit success, and missing completion with synthetic books. Keep the legacy recipe working.

### 4. Prove the operation interface with simple steps

- [ ] Establish uniform `perform(context)` and `verify(context)` contracts using the lifecycle API.
- [ ] Migrate translation and resource-removal classes first, then CSS cleanup and Panda checks. Adapt callers or retain an explicit temporary legacy path until step 8.
- [ ] Test ordered execution, failed-check termination, operation-owned conditional behavior, and direct context construction.

### 5. Establish how analytics belong to a processing run

- [ ] Define a minimal run record for success, skip, and error outcomes.
- [ ] Choose run IDs versus object relationships to an unsaved run record; prove parent/child persistence and an actual Windows process-pool round trip.
- [ ] Define analytics models near their operations in importable modules without database/configuration I/O. Document schema registration/imports.
- [ ] Plan coexistence or migration of existing analytics tables/data while preserving history and reason codes.

### 6. Add the generic parent-side recorder

- [ ] Persist mixed unsaved mapped instances in one session/transaction per batch, including relationship handling.
- [ ] Test mixed model types, run/child associations, diagnostic details, and rollback in a temporary database. Verify actual batching behavior.
- [ ] Retain buffers after failed writes. Define duplicate prevention and uncertain-commit handling before adding retries.

### 7. Migrate image optimization and reference updates

- [ ] Adapt the image operation to publish operation-owned SQLModel analytics and successful path changes to the shared replacement mapping.
- [ ] Make HTML/OPF steps consume replacements; clear mappings only after all consumers finish. Preserve the current unmatched-link policy.
- [ ] Test collisions, conversion/rename/link consistency, unchanged images, partial failures, and export/reopen.

### 8. Assemble the Panda recipe around the context

- [ ] Replace inline work with the reviewed checks/operations and context lifecycle; retain recipe ordering, export, output validation, and explicit success.
- [ ] Remove superseded paths and result conversions while preserving eligibility decisions, filenames, and transformations except separately documented fixes.
- [ ] Decide explicitly how to replace destination-deletion/original-movement test scaffolding before real-book runs.
- [ ] Test success, early skip, operation failure, and export/output validation failure; retain earlier evidence on each outcome.

### 9. Integrate batch execution and test real books

- [ ] Return the same outcomes/analytics from synchronous and ProcessPoolExecutor paths.
- [ ] Test spawned workers with success/skip/error outcomes and related analytics, plus parent database failure; retain outcomes for worker failures.
- [ ] Fix/document the synchronous behavior of `max_workers=None` versus its CPU-count docstring.
- [ ] Validate a small representative set of copied EPUBs and saved analytics before increasing batch size; keep originals untouched.

## Backlog after the migration

These tasks are unscheduled; their order is not an implementation commitment.

- [ ] Define whole-publication deletion/link policy for XHTML, CSS, NCX, and NAV.
- [ ] Design core/chapter disassembly, chapter deduplication, and reassembly together.
- [ ] Define shared-asset retention and reuse during disassembly/reassembly.
- [ ] Support incremental chapter updates and EPUB assembly from internet articles.
- [ ] Revisit navigation across spine, NCX, guide/tours, and EPUB 3 NAV.
