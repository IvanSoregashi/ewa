# Image processing TODO

Work is ordered by dependency and intended execution. Complete one migration step per
reviewable change while keeping affected callers working. Unscheduled image work stays in the backlog.

This list owns unfinished library image processing and EPUB image-adapter work.
Completed migration history remains in [EPUB_TODO.md](EPUB_TODO.md#image-optimization-checkpoint-not-the-finished-design);
image contracts live in [IMAGE_SPECIFICATION.md](IMAGE_SPECIFICATION.md);
EPUB adapter responsibilities live in [EPUB_SPECIFICATION.md](EPUB_SPECIFICATION.md#state-and-ownership).
Working conventions and validation commands are in [AGENTS.md](../AGENTS.md).

## ImageProcessingContext refactor

Follow the [planned image-context contracts](IMAGE_SPECIFICATION.md#planned-imageprocessingcontext).
Implement each step separately; this plan does not introduce a resource context or a shared base class.
Keep the current optimizer and its callers in place while building the replacement alongside it.
Switch callers only after the replacement passes comparison for all important cases.

### 1. Introduce the concrete library context and its lifetime

- [x] Use the same bytes input, configuration arguments/defaults, compression data, and return contract as the current optimize_image entry point. Stream/opener support is deferred and does not block the context.
- [x] Add ImageProcessingContext in library.image for one image and one recipe call: configuration, original metadata, working Pillow image, candidate bytes, and one final ImageOptimizationResult. Reuse existing result/metadata types and numeric reasons; add no per-step result or findings list.
- [x] Open input and create the Pillow image inside the with block so setup failures reach __exit__. Release owned streams, images, and buffers; retain known metadata. Derive error outcomes from exceptions, propagate interrupts, and finalize a detached result after cleanup.
- [x] Test opening/metadata/processing/cleanup failures and source ownership with synthetic inputs. Use one context per call by convention, without re-entry or active-context guard machinery.

### 2. Express the image recipe through checks and transformations

- [x] Use the committed resize fix as the common baseline: both-axis limits use the narrowed dimensions, and the user-restored one-pixel minimum is retained. Both implementations share the helper; resizing tests pass.
- [x] Establish synthetic outcome/byte comparisons as each format migrates; keep the existing optimizer available as the comparison implementation.
- [x] Add ordered verification that ends the recipe at the first failed gate. Keep conditional transformations inside operations and ordinary pixel/arithmetic helpers as functions; introduce operation objects only where they make the recipe clearer.
- [x] Move format eligibility, transparency handling, resizing, encoding, and savings acceptance into explicit recipe steps. Mark success only for accepted encoded output; keep candidate metadata for rejected conversions where currently reported.
- [x] Preserve current PNG/JPEG/static-GIF policies, animation skips, encoder settings, configured conversion/size options, and integer savings cutoff. Compare outcomes and accepted bytes as each format migrates; retain the old implementation temporarily for comparison.

### 3. Integrate the resource adapter and verify isolation

- [x] Keep perform_image_optimization as a short resource recipe with an opt-in use_context comparison path and the current optimizer as default: acquire input/additional metadata, call the image recipe, then apply accepted bytes and rename. Keep resource collisions, link mappings, and database analytics outside the image context.
- [x] Create contexts and open sources inside workers. Pass bytes or a serializable source description across process boundaries, never live contexts, Pillow images, streams, EPUB resources, or database state; arbitrary opener functions are not assumed serializable.
- [x] Test independent calls and an actual spawned-worker round trip of supported inputs/results. Verify conversion-disabled paths need no new link replacements and per-image errors leave resources unchanged.

### 4. Clarify context exception handling

- [x] Review ImageProcessingContext.__exit__ for readability while preserving failure precedence, retained evidence, and interrupt propagation.
- [x] At minimum, add a short comment before each handling block explaining which exception or exit condition it handles and why: recipe skip, cleanup failure, interrupts, missing completion, ordinary failure classification, and candidate disposal.
- [x] Keep lifecycle tests covering combined processing/cleanup failures and interrupts.

### 5. Split format processing from saving

- [x] Split encode_image into a processing operation for each supported format, with each operation acting only when the input is its format.
- [x] Give PNG processing ownership of its conditional conversion and unchanged-image policy.
- [x] Give JPEG processing ownership of its density/compression decision and encoder settings.
- [x] Give static GIF processing ownership of its unchanged-image policy and encoder settings; retain the separate animation gate.
- [x] Extract saving into a separate operation that writes the selected format/settings and records candidate bytes/metadata. Keep savings acceptance and success after saving.
- [x] Compare outcomes, metadata, and bytes against the retained implementation after the split; introduce no per-operation classes unless they improve the recipe.

### 6. Separate image transformations and encoding decisions

- [x] Keep resizing, alpha removal, format conversion, encoding selection, and saving as independent operations; supersede the per-format processing functions from step 5.
- [x] Make resizing change dimensions only, alpha removal change pixel mode only, and format conversion select the target format without choosing quality or saving.
- [x] Move unchanged-image and JPEG recompression eligibility into a needs_encoding check after transformations.
- [x] Select encoder quality separately, preserving PNG-to-JPEG and JPEG-input quality differences. Record candidate metadata only after saving.
- [x] Compare outcomes and bytes with the retained optimizer and verify stage independence; keep production defaults unchanged.
- [x] Remove the PNG-conversion switch from the context. Keep eligibility in the recipe and make png_to_jpeg unconditional when invoked; retain the public recipe/adapter option for compatibility.
- [x] Remove repeated operation readiness assertions; rely on recipe ordering while preserving lifecycle error handling.

### 7. Compare the complete pipeline and remove superseded machinery

- [ ] Compare synthetic success/skip/error outcomes, metadata, and output bytes under the same policy. Repeat the six-book comparison on copies, excluding the merged example; compare bytes and analytics without displaying book contents or changing originals.
- [ ] Measure and compare read/decode work and runtime against the retained optimizer for cheap skips and larger images. Check avoidable image copies, retained buffers, and transport costs before claiming a performance benefit.
- [ ] After all important cases pass comparison, switch callers and remove the temporary use_context switch, superseded optimizer path, and unused helpers, keeping public callers working. Review the concrete context for unnecessary layers; leave a resource context and generic context base deferred unless a concrete need emerges.

## Backlog after the migration

These tasks are unscheduled; their order is not an implementation commitment.

- [ ] Consider creating a new resource for image conversions that change the path, removing the original, and synchronizing the manifest with the final inventory; settle preservation of IDs, properties, and dependent references before replacing the current rename/link-update flow.
- [ ] Reconcile convert_giant_gifs with animation handling: the regular optimizer skips animated images, while the dedicated GIF-to-MP4 recipe still assumes it converts and renames them. Keep video conversion separate from format-preserving image optimization.
