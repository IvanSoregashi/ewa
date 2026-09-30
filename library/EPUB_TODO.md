# EPUB architecture TODO

Work is ordered by dependency and intended execution. Complete one migration step per
reviewable change while keeping affected callers working. The book-context migration is complete;
unfinished image work is tracked separately in [IMAGE_TODO.md](IMAGE_TODO.md). Unscheduled EPUB work stays in the backlog.
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
- [x] Consolidate verification protocols in the plugin; return None on success or a failure message, preserving configured skip reasons and numeric values.
- [x] Remove obsolete EPUB verification entry points and duplicate library/plugin protocol inheritance.
- [x] Verify library code/tests do not import the plugin and checks work in an ordered loop.

### 2. Introduce a small per-book context

- [x] Add ProcessingContext with live EPUB, original information, replacements, and one unsaved SQLModel analytics list.
- [x] Document per-book ownership, sequential use, and empty replacements meaning no work.
- [x] Initially reuse EpubOperationResult for detached outcomes; step 5 supersedes it with ProcessingRun.
- [x] Test independent contexts, outcomes, and local serialization while keeping the legacy recipe working.

### 3. Add context lifetime management and automatic outcomes

- [x] Enter an empty context and call `open_epub(path)` inside its block to construct/open the EPUB and capture original information. Convert setup failures to outcomes with the input path and no invented metadata; reliably release acquired sources.
- [x] Add verify(*checks): consume checks in order, immediately stop on failure, and produce a skip with the configured reason and details. Update protocol documentation to remove warn/repair decision policies.
- [x] Automatically convert processing exceptions into error outcomes while retaining earlier evidence and propagating interrupts. Require explicit success after export/output validation; define behavior for missing completion.
- [x] Test source lifetime/cleanup, short-circuiting, construction/opening/metadata/processing failures, partial outcome reporting/serialization, retained evidence, interrupts, explicit success, and missing completion with synthetic books. Keep the legacy recipe working.

### 4. Prove the operation interface with simple steps

- [x] Establish uniform `perform(context)` and `verify(context)` contracts using the lifecycle API.
- [x] Migrate translation and resource-removal classes first, then CSS cleanup and Panda checks. Adapt callers or retain an explicit temporary legacy path until step 8.
- [x] Test ordered execution, failed-check termination, operation-owned conditional behavior, and direct context construction.

### 5. Establish how analytics belong to a processing run

- [x] Use ProcessingRun directly for success, skip, and error outcomes and persistence; remove the duplicate result class and conversion.
- [x] Choose worker-created UUIDs and scalar foreign keys; prove parent/child persistence and an actual Windows process-pool round trip, including setup failures and retained evidence.
- [x] Keep book/image metadata typed as EpubInfo/ImageInfo through one TypedJSON adapter; operation-owned image records remain importable without database/configuration I/O.
- [x] Clarify dataclass snapshot semantics: unknown image dimensions/density, byte-based density naming, optimizer-owned thresholds, and filesystem-only EpubInfo.from_path.
- [x] Replace the legacy analytics models/wrappers with two tables for new writes; preserve historical tables/data and numeric reason codes.

### 6. Add the generic parent-side recorder

- [x] Persist mixed unsaved mapped instances directly in one session/transaction per batch; flush run records before analytics with scalar foreign keys.
- [x] Test mixed model types, run/child associations, diagnostic details, rollback, and actual batched inserts in temporary databases.
- [x] Propagate failed writes without clearing the batch. Use stable primary keys and no automatic retries; document explicit reconciliation for uncertain commits.

### 7. Migrate image optimization and reference updates

- [x] Publish image records directly from the current Panda recipe, retaining evidence on later skips/errors; remove legacy result/table conversions.
- [x] Adapt the image operation to publish records through ProcessingContext and successful path changes to its shared replacement mapping.
- [x] Make ReplaceLinks consume replacements in HTML and OPF, retain separate non-manifest and manifest unmatched-path mappings on the context, and clear replacements after both consumers finish. Missing old manifest entries are reported without adding declarations. Keep HTML skip policy in NoUnmatchedLinks.
- [x] Test collisions, conversion/rename/link consistency, unchanged images, partial failures, and export/reopen.

### 8. Assemble a separate Panda recipe around the context

- [x] Replace inline work with the reviewed checks/operations and context lifecycle; retain export, output validation, and explicit success.
- [x] Run NoUnmatchedLinks after reference updates and before translation/export to preserve Panda's unmatched-link skip policy.
- [x] Add a separate AllResourcesInManifest check and DeclareMissingResources operation. Retain them as optional tools; automatic repair/full-coverage verification was removed from the candidate because undeclared resources may be abandoned assets.
- [x] Keep _fully_process_encrypted_panda as the legacy default and add _fully_process_encrypted_panda_with_context for comparison. Retain verify_epub while the legacy recipe needs it.
- [x] Move directory/destination filtering into decrypt and the batch dispatcher; filtered paths produce no ProcessingRun or analytics, while processing functions always return a run.
- [x] Classify InvalidEpubOutput in __exit__ to preserve INCORRECT_RESULT without a mutable error-reason field; keep original exception diagnostics.
- [x] Extract packaging into PackageEpub, calling a separate output-validation function before marking success; retain the current reopening/metadata check for comparison.
- [x] Preserve destination-deletion/original-movement scaffolding during assembly; schedule its replacement decision before real-book runs in step 9.
- [x] Test success, early skip, setup/operation/export/output-validation failures, and source cleanup; retain earlier evidence on each outcome.

### 9. Compare recipes before switching callers

- [x] Compare synthetic outcomes, book/image metadata, analytics (excluding generated IDs), and exported resource contents for 14 success/skip/error scenarios.
- [x] Add explicit regression cases for differences in undeclared-orphan handling and cleanup diagnostics; do not claim full equivalence.
- [x] Compare missing-manifest images with and without HTML references, and cleanup failures after success, unmatched-link skip, translation/export failure, and output-validation failure; verify retained analytics and unchanged input bytes.
- [x] Resolve missing-manifest failures with one shared replace_links helper that returns absent old entries without creating declarations. Both recipes now succeed for referenced images and produce UNMATCHED_LINKS for images absent from HTML; compare outcomes, analytics, and exported contents. Keep the context's cleanup diagnostics without requiring exact legacy text.
- [x] Establish comparison policy: apply intentional behavior improvements to both recipes, sharing helpers instead of preserving obsolete behavior in the old implementation.
- [x] Make the test workflow an explicit dry_run option through both recipes, single/batch callers, and CLI (-d / --dry_run). Dry runs retain originals and discard output while still processing/recording analytics; normal runs keep output and move originals after success. Test both modes and preserve existing processed files.
- [x] Normalize Pillow rational/fractional DPI metadata to floats so image analytics can serialize and round-trip through JSON storage; test synthetic DPI values.
- [x] Compare isolated copies of the six supplied Panda books, excluding the merged example: both recipes succeed with identical output bytes, outcomes, and analytics after the shared DPI fix. Original hashes remain unchanged; temporary database integrity checks pass. Compare bytes without displaying book text.
- [x] Switch single/batch callers to the context recipe after comparison; remove the legacy implementation and verify_epub entry points. Retain comparison scenarios as regression tests and verify caller persistence with a temporary database.

### 10. Integrate batch execution

- [x] Document the retained synchronous behavior for `max_workers=None` and `0`; positive values use a process pool.
- [x] Allow concurrent workers to create a shared output directory without a check/create race; add a deterministic regression test.
- [x] Return the same outcomes/analytics from synchronous and ProcessPoolExecutor paths. Preserve process-pool submission/result failures as UNKNOWN outcomes instead of dropping books; synchronous dispatch calls the recipe directly.
- [x] Keep dry-run deletion outside the processing context as nonfatal housekeeping; log deletion failures without changing success or analytics. Retain original error codes and analytics if failed-output removal also fails. Test cleanup failures and propagation of unexpected synchronous exceptions.
- [x] Test real spawned workers with success/skip/error outcomes and related analytics, abrupt worker termination, submission failures, and parent database failure. Compare synchronous/spawned results and output bytes in normal and dry-run modes.
- [x] Validate isolated copies of the six comparison books with two spawned workers and flush_size=2: all succeed with identical output bytes and saved analytics; 6 runs and 6,755 image records pass database integrity checks. Originals remain unchanged and the merged example stays excluded. Keep CLI batch sizing unchanged.

## Image optimization checkpoint (not the finished design)

- [x] Introduce library optimize_image for decoding/encoding and size acceptance, with resource updates in the EPUB adapter. Add options for PNG-to-JPEG conversion, minimum file size, and resize bounds. This is a committed intermediate implementation; its internal structure still needs revision.
- [x] Add coverage for format-preserving optimization/export, configurable thresholds, resizing, and the existing savings cutoff. Later edits removed the rejected thin-image precautions; reconcile resizing code and expectations before establishing the next baseline.
- [x] Compare that initial checkpoint's default settings on isolated copies of the six supplied books: output bytes and all 6,755 image records matched the previous results; originals remained unchanged. This historical comparison does not validate subsequent edits.

## Completed recipe follow-ups

- [x] Expose the no-relink Panda recipe through single-book and batch Python entry points and `decrypt-no-relink` / `dd-no-relink` CLI commands. Share batch orchestration; retain filtering, parent-side analytics, and dry-run handling. Validate CLI dispatch and synchronous/spawned execution with synthetic books and temporary databases.

- [x] Restore PNG-to-JPEG conversion and HTML/manifest link replacement in the alternative Panda recipe, followed by NoUnmatchedLinks before export. Retain nested-OPF/multiple-font support, existing entry-point names, and current CLI batch settings. Verify converted output references, unmatched-link skips, collisions, persistence, and synchronous/spawned callers.

- [x] Let the alternative Panda recipe continue after unmatched links, saving separate HTML/manifest mappings under `profile_dir/epub/unmatched_links` with the input's relative path. Preserve reports in dry runs, remove stale reports on clean retries, and treat report I/O failures as nonfatal. Keep the default recipe's unmatched-link gate.

## Backlog after the migration

These tasks are unscheduled; their order is not an implementation commitment.

- [ ] Define whole-publication deletion/link policy for XHTML, CSS, NCX, and NAV.
- [ ] Design core/chapter disassembly, chapter deduplication, and reassembly together.
- [ ] Define shared-asset retention and reuse during disassembly/reassembly.
- [ ] Support incremental chapter updates and EPUB assembly from internet articles.
- [ ] Revisit navigation across spine, NCX, guide/tours, and EPUB 3 NAV.
- [ ] Define proper EPUB output validation beyond reopening and metadata reading: agree on validation scope and tooling for archive/package integrity, content references, and EPUB conformance.


# Another issue with useless text, watermarks? waste of space.
```css
.calibre5 {
  height: 0.01em;
  font-size: 0.01em !important;
}
```
```html
  <p class="calibre5">watermark</p>
```

