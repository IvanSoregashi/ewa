# Image processing specification

## Scope and status

This document owns contracts for reusable image processing in library.image, independently
of EPUB workflows. Implementation order lives in [IMAGE_TODO.md](IMAGE_TODO.md);
contributor instructions live in [AGENTS.md](../AGENTS.md).
EPUB resource integration belongs to [EPUB_SPECIFICATION.md](EPUB_SPECIFICATION.md#state-and-ownership).

The existing optimize_image implementation remains active. ImageProcessingContext now provides
a concrete lifetime API, and recipe.optimize_image_with_context implements the replacement recipe
alongside it. The EPUB adapter can opt into the replacement for comparison; existing callers
still default to optimization.optimize_image.
The replacement context separates original, current, and target metadata. It first attempts
conversion/recompression, accepts or restores that image, then decides resizing from the
accepted current encoding's density. Each stage has its own save and savings decision.

## Current optimizer contract and policy

optimize_image accepts bytes and the existing configuration and compression arguments.
It owns decoding, encoding, and size acceptance, returning an ImageOptimizationResult and
accepted bytes (None for skip/error). Keep the existing argument names and defaults.

Options include convert_png_to_jpeg=True, min_filesize=50 * 1024 (bytes), and
max_dimensions=None (the existing density-based limits). Explicit dimensions are intended
to bound resizing without upscaling; zero leaves an axis unconstrained, so (0, 0) disables
resizing. The committed resize baseline applies the height limit to the already narrowed width
and keeps the user-restored one-pixel minimum for thin images. Both recipes share this helper.

Preserve PNG/JPEG/static-GIF policies, encoder quality, transparency handling, and animation
skips. Unchanged PNGs are skipped rather than re-encoded solely to attempt compression.
The historical savings gate accepts int(output_size / input_size * 100) <= 97.
Rejected candidates may retain candidate metadata but have no accepted bytes.
ZIP compression information used by JPEG policy is plain additional data from the caller;
the image library has no dependency on EPUB resources.

## Image metadata

ImageInfo remains a dataclass. ImageInfo uses `size=None` for unreadable dimensions;
`bytes_per_pixel` returns a float and raises ValueError when dimensions are unknown or nonpositive.
Density thresholds are provisional byte-based heuristics, not format efficiency guarantees;
see [BPP research and published measurements](IMAGE_BPP_RESEARCH.md).
DPI is captured as a pair of floats: Pillow EXIF rational values otherwise cannot serialize to JSON,
and integer typing would reject fractional resolutions when reading stored snapshots.

## Planned ImageProcessingContext

The lifetime API and parallel replacement recipe are implemented; caller migration remains planned. `optimize_image` remains the image
recipe entry point; a concrete `ImageProcessingContext` in `library.image` owns one image's
working state, lifetime, and automatic outcome. Reuse `ImageInfo` and `ImageOptimizationResult`.
Keep pixel helpers as functions; adapters remain outside the image library.
No common context base is needed for this step.

Initially keep the current optimize_image contract: bytes input, existing configuration arguments
and defaults, plain compression data, and the existing result/accepted-bytes return shape.
Create the Pillow image through the context's opening method inside the with block so opening
failures reach __exit__. The context owns the buffers and Pillow objects it creates.
len(bytes) gives the encoded size in constant time; header inspection can avoid pixel decoding,
but the caller has already acquired the encoded bytes. Stream/opener support can be added later
and is not a prerequisite for the context. Keep ZIP compression data independent of EPUB resources.

Build the context and replacement recipe alongside the current optimizer. Keep existing callers
on the current implementation until comparisons cover all important cases. Establish synthetic
comparisons during migration and measure both implementations before switching callers; baseline
work does not block introducing the context. Document intentional policy changes and cover
their differences separately from equivalence comparisons; keep the original optimizer as the baseline.

Checks stop on failure; decisions select targets and transformations apply them. The context retains known
metadata on failure, releases its owned resources, and returns one detached outcome with accepted
bytes only after encoding and size acceptance succeed. Interrupts propagate. Resource mutation,
renaming, link replacement, and persistence remain outside this context.

Create each context and its live inputs inside its worker. Input API flexibility does not imply
that live streams or arbitrary opener functions can cross process boundaries: transport bytes or
a serializable source description and return detached data. Preserve processing policy during the
refactor and compare behavior and costs before retiring the current implementation.

## Implemented context lifetime

Create ImageProcessingContext with compression, min_filesize, and max_dimensions, then call
open_bytes_as_image(content) inside its with block. Opening initializes independent current
and target copies of the original ImageInfo. Entering performs no input opening.
The context owns its input buffer and opened image; replace_image(image) also takes ownership
of a transformed image. It closes the previous image unless preserve_image() retained it for
the current stage. Preservation keeps the live Pillow image and a separate ImageInfo snapshot,
without copying pixels or reopening encoded bytes. It also retains the previous candidate
output and quality so rejection can return to the last accepted encoding.
accept_image() closes an obsolete preserved image; restore_image() restores it and closes
the rejected image. Both reset target metadata to the accepted current state. Only one stage
is preserved at a time; obsolete intermediate images still close when replaced.
The replacement is registered before closing the previous image so cleanup also covers close failures.
All registered resources are closed on exit, including when another
close fails. Use a fresh context per call, without re-entry guards.

original_image_info retains captured metadata (or known byte size if metadata capture fails).
image is the working Pillow object; current_image_info tracks its size and mode through
replace_image. Its format and filesize describe the last encoded representation, initially the
input, and are updated by save_image. Other captured metadata remains inherited from the input.
target_image_info holds the requested size, mode, and format; target_quality holds encoder quality.
Copied target fields such as filesize and extrema are not instructions or predicted output values.
candidate holds encoded bytes and is invalidated when the working image changes.
image_info_history retains independent metadata snapshots for attempted "conversion" and
"resize" encodings, including rejected attempts; it is context-local and contains no pixels.
The external ImageOptimizationResult.new_image describes accepted output or the last rejected
candidate when neither stage succeeds. Preserved images and candidate references are released
on exit, including errors and interrupts; metadata remains available.
skip(reason) stops the block, retaining metadata but discarding candidate bytes on exit.
succeed() requires candidate bytes; the recipe performs encoding and size acceptance before calling it.
Encoding and savings policy live in recipe functions, outside the context.

After the block, outcome() returns the existing (ImageOptimizationResult, accepted bytes or None)
shape. Ordinary exceptions are classified by ImageErrorReason.from_error; missing completion
becomes UNKNOWN. Cleanup failure overrides success or skip, while a processing failure retains
its classification if cleanup also fails. Diagnostics are logged. Interrupts propagate after
cleanup and leave no completed result. The working image reference is cleared on exit.

## Decisions and execution

Decision functions accept the context, read current information and earlier target choices,
and modify target_image_info or target_quality without transforming the working image.
Execution applies the target for each stage, saves using its format and quality,
checks savings, and accepts or restores the image through separate functions. Reuse ImageInfo for all
three roles without another metadata class. Original metadata remains unchanged.

PNG-to-JPEG eligibility uses current encoded filesize and current pixel area before resizing.
JPEG recompression can be eligible even when target dimensions, mode, and format match the input;
save eligibility is a separate decision. Quality is an output setting, not inferred input metadata.
Alpha removal is decided from original PNG RGBA pixels before resizing: minimum alpha >= 250
selects RGB. This intentionally differs from the retained optimizer's post-resize inspection.
For example, resizing can hide an original alpha value of 249; the new recipe still keeps RGBA.
Accepted mode conversion now precedes resizing; rejection restores the previous pixel mode.
The resized image comes from retained working pixels, never a decoded intermediate JPEG.
This avoids an additional lossy generation, though two encodes are needed when both stages run.

Each savings decision compares encoded byte size with the preserved image from that stage,
using int(after / before * 100) <= 97. Conversion leaves dimensions unchanged, so this also
measures percentage BPP improvement. Resizing changes pixel area; its acceptance uses bytes,
not BPP. A rejected conversion still proceeds to resizing. Rejected resizing retains any
accepted conversion. If neither stage changes the image, return NOT_OPTIMIZED; if all attempted
encodings are rejected, return WORSE_CONVERSION and the last attempted metadata. Exceptions
still produce an error outcome rather than silently accepting an earlier stage.

## Parallel image recipe

recipe.optimize_image_with_context accepts the same bytes and keyword arguments as
optimization.optimize_image. It opens inside the context and verifies minimum size, supported
format, and animation policy. It preserves the current image, then remove_useless_alpha,
convert_inefficient_png_to_jpeg, and select_encoding populate conversion targets.
needs_encoding compares target and current information and permits eligible JPEG recompression.
When needed, convert_image and save_image run, followed by accept_savings; otherwise the
unchanged image/settings are restored. Rejection does not call the recipe-ending skip().

The resize stage preserves that accepted state, runs select_dimensions, and performs
resize_image and save_image only when size changes. Its own accept_savings can restore the
accepted conversion. An accepted conversion with no required resize is returned without
saving again. Explicit success follows completion of both stages.

select_dimensions sets target size using current format/density and the shared crop_dimensions
arithmetic. Explicit bounds take priority. Defaults retain 2560 width for PNG below 0.2
bytes/pixel or JPEG below 0.1, otherwise 1080, including GIF.
remove_useless_alpha sets target mode to RGB when original pixels meet the alpha rule.
convert_inefficient_png_to_jpeg selects target JPEG for PNG inputs with planned RGB mode and
current density at least 0.5 bytes/pixel. The convert_png_to_jpeg keyword remains only
on recipe/adapter entry points for compatibility; it controls invocation, not context state.
select_encoding sets target_quality without manipulating the image or deciding eligibility:
PNG-to-JPEG uses 85, JPEG input uses 75, GIF uses 85, and PNG has no quality argument.

resize_image applies target size with LANCZOS; convert_image applies target pixel mode.
Each does nothing when current and target already match. They do not select policy or quality.
save_image encodes using target format and quality, then records candidate bytes and current
metadata. It does not reapply conversion eligibility. Custom recipes may set target fields
directly and use the same execution operations. Metadata survives rejected savings.

verify(*checks) takes ordinary functions returning None on success or an ImageSkipReason on
failure; the first failure stops the recipe. Decisions and operations are ordinary functions,
without operation classes. They rely on recipe ordering instead of
repeated image/candidate readiness assertions; the image property provides the working image.
The earlier per-format process_png/jpeg/gif functions are superseded by these independent
operations and the needs_encoding check.

Synthetic comparisons cover outcomes, metadata, and accepted bytes, including configured
bounds, modes, transparency, animations, size/compression boundaries, invalid/truncated data,
and injected processing failures. Stage acceptance combinations, retained-image rollback,
current-density resize decisions, and original-pixel alpha differences are tested explicitly.
The existing optimizer remains active until the final
pipeline and performance comparisons are finished.

A spawned-worker regression test sends only bytes and configuration into a worker, creates the
context and Pillow objects there, and returns detached results and bytes. Repeated success,
error, skip, and format-preserving calls in the same worker match synchronous calls without
sharing image state. No image-level parallel scheduler is added to production code.
