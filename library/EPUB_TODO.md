# EPUB architecture TODO

## Agreed next steps

- [x] Fix Source exception cleanup: a failed ZIP session must close and reset its handle, and subsequent reads must work.
- [x] Fix single-file ZIP extraction: match DirectorySource for existing-directory and exact-filename destinations, preserve timestamps, and avoid duplicated member paths. Add synthetic regression tests.
- [x] Prototype a package entity associating the OPF resource with its parsed document. EpubPackage exposes document, local href resolution and flush; EPUB export flushes document edits. Review before expanding the design.
- [x] Put discovery in EpubPackage.from_resources. Keep the container resource and its XML model on the package; package.relocate updates the OPF hrefs, resource index, and container reference together.
- [x] Make ResourceIndex.rename(resource, new_filename) rename and re-key together, rejecting collisions. Preserve original source ZipInfo separately from current output metadata so reads survive renames.
- [x] When a unique OPF exists without META-INF/container.xml, create a standard container document and resource, add it to the inventory, and bind it to the package. Verify relocation and export/reopen; replace the current missing-container rejection test.
- [x] Define and test valid archive destination paths and URL handling for relocation (normalization, encoded paths, queries, and fragments) before treating it as general EPUB reference rewriting.
- [x] Justify any package facades and a separate EpubManifest through useful editing methods. Avoid wrappers that merely shorten attribute access.
- [x] Settle resource deletion and collection ownership on one consistent model. Review the implementation before adopting wider ResourceIndex API changes; membership versus is_deleted is currently redundant.
- [x] Address manifest index consistency and synchronization during add/remove/edit, together with the ownership decision. Decide how filtered collections behave.
- [x] Retire the current EpubCore while restructuring package handling. Preserve the requirement for a future core abstraction, either as a parallel API or a separate class on the same Source/Resources foundation.

## Design constraints and future work

- [ ] Keep Resource focused on providing bytes; do not restore the previous accumulation of OPF/NCX links and document-, image-, or chapter-specific behavior on Resource.
- [ ] Develop core and chapter support together: disassemble the webnovel EPUB library, deduplicate overlapping chapters, and reassemble EPUBs around their cores.
- [ ] Support assembling and updating EPUBs when new chapters arrive, and creating EPUBs from collections of internet articles.
- [ ] Define how shared chapter assets are retained and reused during disassembly and reassembly. Detailed ownership and deduplication policies remain open.
- [ ] Revisit navigation design separately: spine, NCX, guide/tours, and eventual EPUB 3 NAV support. No combined navigation API or reading-order/TOC class structure has been accepted yet.

The core/content distinction is application-defined, not a partition imposed by the EPUB specification. A NAV document may belong to the core even when it appears in the spine.

Use `uv run ruff format` on changed Python files. The repository has pre-existing Ruff/ty findings; assess checks against the affected scope.

## Explicitly deferred

- Source path APIs, Path/ZipPath/backend types, and escaping path lifetimes remain unchanged for now; they may serve uses beyond EPUB.
- Shared-instance concurrency is not being added. The concern is multiple workers sharing one EPUB/Source instance, not workers each processing their own instance.
- Broader changes to resource identity, statistics, streaming, and generic book models require separate review; they are not part of the Source fixes.

## Already accepted

- [x] Resolve local manifest hrefs relative to the OPF location. The package prototype replaces the copied package_path argument with an EpubPackage reference.

## Package prototype choices awaiting review

- EpubPackage.from_resources discovers the OPF/container; the constructor also accepts already-selected resources. The relocation recipe delegates to package.relocate. Discovery creates a standard container for a unique OPF when the container is absent; existing invalid containers are not silently replaced.
- EpubCore is retired; callers use epub.package. NCXDocument remains available for parsing NCX resources directly, pending the separate navigation design.
- Export serializes loaded OPF and container documents directly, without snapshots or formatting-preservation flags. Unopened documents are left alone. Once parsed, edit the document rather than independently replacing its resource bytes.
- Metadata and spine remain on PackageDocument; resource deletion follows the ownership rules below.

Relocation accepts normalized archive-relative file paths; it rejects absolute/escaping paths and file/directory collisions. Local URL paths use strict UTF-8 percent decoding, preserve query/fragment suffixes, and reject encoded separators or malformed escapes. Remote URLs pass through. This is the supported local-path contract, not a full WHATWG URL implementation.

## Package ownership implementation

- EpubManifest is removed. The package reads the XML manifest directly and coordinates add_resource/remove_resource; no second manifest index is cached.
- ResourceIndex owns membership; ResourceSelection is an immutable membership snapshot with editable resources. Removed objects can still be held/read, but export uses the owner's current inventory. There is no is_deleted flag.
- remove_resource rejects OPF dependents unless remove_references=True. Cleanup covers spine, guide, fallback/media-overlay, spine toc, cover metadata and dependent refinements. Content and NCX/NAV links are not inspected or rewritten.
- [ ] Define book-level deletion/link policy for XHTML, CSS, NCX and NAV before claiming whole-publication safe removal.

## Recipe ownership

- [x] Move EPUB workflow recipes, operation protocols, eligibility policies, and persisted outcome codes into the EPUB plugin. Keep resource editing, image inspection, and general verification in the library. Tests follow the same boundary.

## Shared processing context migration

Implement one numbered step per reviewable change. Each step must keep its affected callers working and pass focused tests before proceeding. This is a migration plan, not approval to change production data or run the full book collection.

### 1. Finish the library/plugin boundary

- [ ] Move the remaining configured verification classes (`MimetypeVerification`, `ValidXMLChapters`) into the plugin, together with their tests. Keep reusable parsing/editing functions in the library; any verification logic retained there must have a function interface.
- [ ] Consolidate verification protocols and `VerificationResult` in the plugin. Remove the duplicate library/plugin protocol inheritance. Keep each check's default `skip_reason` and its fresh per-call findings. Preserve existing persisted numeric reason values.
- [ ] Inspect `EPUB.is_specification` / `require_specification` and their callers for overlap; resolve obsolete verification entry points within this step without creating replacement abstractions.
- [ ] Verify that library code and tests do not import the plugin and that checks still work in a simple ordered loop.

### 2. Introduce a small per-book context

- [ ] Add `ProcessingContext` in the plugin with the live EPUB, original book information, a replacement mapping, and one analytics list accepting SQLModel table instances. No database session, engine, arbitrary shared-state dictionary, or operation-specific result slots.
- [ ] Document ownership: one context per book, created inside the worker; operations run sequentially; an empty replacement mapping means no work. Do not introduce a separate state distinguishing "not run" from "no replacements" unless a real operation needs it.
- [ ] Define how the context produces the returned success/skip/error outcome. Return findings and analytics, not the live context/EPUB/source. Preserve useful findings when a later step fails; failure does not roll back EPUB edits.
- [ ] Test independent contexts, final outcomes, and exclusion of live resources from the returned value. Keep the existing recipe running while this small API is reviewed.

### 3. Prove the operation interface with simple steps

- [ ] Establish the plugin contracts `perform(context)` and `verify(context)` without adding a runner framework or protocol hierarchy. Operations publish analytics only when useful; most return nothing and need no analytics model. Verification retains its failure explanation and default skip reason.
- [ ] Migrate the existing translation and resource-removal classes first, followed by CSS cleanup and the checks used by the Panda recipe. Adapt current callers in the same change or retain an explicit temporary legacy path until step 7; do not leave incompatible signatures.
- [ ] Test the simple ordered loop, stopping after a failed check, and building an incoming context directly in tests.

### 4. Establish how analytics belong to a processing run

- [ ] Define a minimal processing-run record that exists for success, skip, and error outcomes. This permits earlier operation findings to survive a later failure, unlike the current success-only image foreign keys.
- [ ] Choose the association before migrating existing analytics: application-generated run IDs versus object relationships to an unsaved run record. Prototype one parent and one child; check persistence and a Windows process-pool round trip with the project's installed SQLModel version.
- [ ] Define analytics table models near their owning operations in importable modules without database I/O or configuration-file reads. Keep the shared run model independent of individual operations. Document schema registration/imports.
- [ ] Decide and document how existing analytics tables/data will coexist with or migrate to the new schema. Preserve history and reason codes; do not silently drop or recreate production tables. SQLModel create_all is not an existing-schema migration.

### 5. Add the generic parent-side recorder

- [ ] Accept mixed unsaved table instances and persist through one session/transaction per batch, using normal ORM persistence so relationships can be resolved. No per-operation conversion switch or one database helper per analytics class.
- [ ] Test mixed model types, run/child associations, diagnostic details, and transactional rollback using a temporary database. Validate actual batching behavior before claiming one insert statement per table.
- [ ] Specify failed-write handling: do not clear an unsaved analytics buffer as the current batch function does. If retries are supported, define duplicate prevention and uncertain-commit handling before enabling automatic retries.

### 6. Migrate image optimization and reference updates

- [ ] Add the context-based image operation using the existing optimizer. Store image analytics as that operation's SQLModel records and publish successful path changes into the context's replacement mapping.
- [ ] Make HTML/OPF reference-update steps consume that mapping. Empty mappings are a no-op. Clear pending mappings only after all intended consumers have finished; preserve existing unmatched-link policy until explicitly reconsidered.
- [ ] Check output-path collisions and failed conversions before publishing mappings. Test conversion/rename/link consistency, unchanged images, partial failure reporting, and export/reopen.

### 7. Assemble the Panda recipe around the context

- [ ] Replace inline work in `_fully_process_encrypted_panda` with the reviewed verification and operation sequence. The recipe owns ordering, export, output verification, and final outcome construction; operations do not write to the analytics database.
- [ ] Remove temporary result conversions and superseded call paths after migration. Keep filenames, eligibility decisions, and transformations equivalent except for separately documented fixes.
- [ ] Make an explicit decision about current test scaffolding (destination deletion on success and disabled original movement) before real-book runs. Do not silently enable moving originals.
- [ ] Test success, early skip, mid-operation failure, and export failure with synthetic books; earlier analytics must remain attached to the correct final outcome.

### 8. Integrate batch execution and test real books

- [ ] Update synchronous and ProcessPoolExecutor paths to return the same outcome/analytics structure. Workers create contexts and unsaved records; only the parent owns database connections and persistence.
- [ ] Test actual spawned workers with success/skip/error outcomes and related analytics, plus a parent-side database failure. Record worker failures as outcomes rather than merely logging and losing the book.
- [ ] Fix/document the current max_workers=None behavior (the code runs synchronously despite the docstring promising the CPU-count default).
- [ ] Run a small representative set of copied EPUBs, inspect output links and saved analytics, then increase batch size. Keep original books untouched during this validation.

Deferred: automatic operation dependency graphs, generic context extension registries, rollback of in-memory EPUB edits, and converting every low-level library function to a class. None is needed for the proposed context-based recipe.
