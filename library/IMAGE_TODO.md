# Image processing TODO

Work is ordered by dependency and intended execution. Complete one migration step per
reviewable change while keeping affected callers working. Implementation awaits an explicit
instruction to start. Unscheduled image work stays in the backlog.

This list owns unfinished library image processing and EPUB image-adapter work.
Completed migration history remains in [EPUB_TODO.md](EPUB_TODO.md#image-optimization-checkpoint-not-the-finished-design);
design contracts currently live in [EPUB_SPECIFICATION.md](EPUB_SPECIFICATION.md#planned-imageprocessingcontext).
Working conventions and validation commands are in [AGENTS.md](../AGENTS.md).

## ImageProcessingContext refactor

Follow the [planned image-context contracts](EPUB_SPECIFICATION.md#planned-imageprocessingcontext).
Implement each step separately; this plan does not introduce a resource context or a shared base class.

### 1. Settle the input contract and comparison baseline

- [ ] Keep optimize_image as the image recipe entry point. Choose the initial bytes/stream/opener signature and configuration shape without introducing a source hierarchy. Define stream ownership, seekability/position, and optional known byte size; acquiring/opening input must happen inside the managed block.
- [ ] Separate header/size eligibility from full reads and pixel decoding. len(bytes) is constant-time; a stream may need a supplied size. Decide how unavailable size affects checks, savings comparison, and metadata. Preserve the existing ZIP-compression-based JPEG decision through plain additional data supplied by the resource adapter.
- [ ] Reconcile current resizing code/tests with the intended bounds and removal of thin-image guards. Establish synthetic outcome/byte comparisons and timing/read baselines for cheap skips and larger transformations before changing the pipeline. Identify intentional behavior changes separately.

### 2. Introduce the concrete library context and its lifetime

- [ ] Add ImageProcessingContext in library.image for one image and one recipe call: configuration, original metadata, working Pillow image, candidate bytes, and one final ImageOptimizationResult. Reuse existing result/metadata types and numeric reasons; add no per-step result or findings list.
- [ ] Open input and create the Pillow image inside the with block so setup failures reach __exit__. Release owned streams, images, and buffers; retain borrowed-stream ownership and known metadata. Derive error outcomes from exceptions, propagate interrupts, and finalize a detached result after cleanup.
- [ ] Test opening/metadata/processing/cleanup failures and source ownership with synthetic inputs. Use one context per call by convention, without re-entry or active-context guard machinery.

### 3. Express the image recipe through checks and transformations

- [ ] Add ordered verification that ends the recipe at the first failed gate. Keep conditional transformations inside operations and ordinary pixel/arithmetic helpers as functions; introduce operation objects only where they make the recipe clearer.
- [ ] Move format eligibility, transparency handling, resizing, encoding, and savings acceptance into explicit recipe steps. Mark success only for accepted encoded output; keep candidate metadata for rejected conversions where currently reported.
- [ ] Preserve current PNG/JPEG/static-GIF policies, animation skips, encoder settings, configured conversion/size options, and integer savings cutoff. Compare outcomes and accepted bytes as each format migrates; retain the old implementation temporarily for comparison.

### 4. Integrate the resource adapter and verify isolation

- [ ] Keep perform_image_optimization as a short resource recipe: acquire input/additional metadata, call the image recipe, then apply accepted bytes and rename. Keep resource collisions, link mappings, and database analytics outside the image context.
- [ ] Create contexts and open sources inside workers. Pass bytes or a serializable source description across process boundaries, never live contexts, Pillow images, streams, EPUB resources, or database state; arbitrary opener functions are not assumed serializable.
- [ ] Test independent calls and an actual spawned-worker round trip of supported inputs/results. Verify conversion-disabled paths need no new link replacements and per-image errors leave resources unchanged.

### 5. Compare the complete pipeline and remove superseded machinery

- [ ] Compare synthetic success/skip/error outcomes, metadata, and output bytes under the same policy. Repeat the six-book comparison on copies, excluding the merged example; compare bytes and analytics without displaying book contents or changing originals.
- [ ] Compare read/decode work and runtime against step 1 for cheap skips and larger images. Check avoidable image copies, retained buffers, and transport costs before claiming a performance benefit.
- [ ] After comparison, remove the superseded optimizer path and unused helpers, keeping public callers working. Review the concrete context for unnecessary layers; leave a resource context and generic context base deferred unless a concrete need emerges.

## Backlog after the migration

These tasks are unscheduled; their order is not an implementation commitment.

- [ ] Consider creating a new resource for image conversions that change the path, removing the original, and synchronizing the manifest with the final inventory; settle preservation of IDs, properties, and dependent references before replacing the current rename/link-update flow.
- [ ] Reconcile convert_giant_gifs with animation handling: the regular optimizer skips animated images, while the dedicated GIF-to-MP4 recipe still assumes it converts and renames them. Keep video conversion separate from format-preserving image optimization.
