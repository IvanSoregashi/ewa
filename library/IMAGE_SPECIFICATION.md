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
The replacement context now separates original, current, and target metadata. Moving all
policy decisions ahead of image transformations is the next migration stage.

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
`bytes_per_pixel` returns None for unknown or zero-area dimensions, including older snapshots.
Density thresholds belong to the optimizer and retain their existing byte-based values.
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
work does not block introducing the context. Resolve intentional policy changes explicitly and
apply them to both implementations.

Checks stop on failure; transformations own conditional behavior. The context retains known
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
of a transformed image and immediately closes the previous image to release its pixel buffer.
The replacement is registered before closing the previous image so cleanup also covers close failures.
All registered resources are closed on exit, including when another
close fails. Use a fresh context per call, without re-entry guards.

original_image_info retains captured metadata (or known byte size if metadata capture fails).
image is the working Pillow object; current_image_info tracks its size and mode through
replace_image. Its format and filesize describe the last encoded representation, initially the
input, and are updated by save_image. Other captured metadata remains inherited from the input.
target_image_info holds the requested size, mode, and format; target_quality holds encoder quality.
Copied target fields such as filesize and extrema are not instructions or predicted output values.
candidate holds encoded bytes. The external ImageOptimizationResult.new_image is populated from
current_image_info only when candidate bytes exist, preserving the result contract.
skip(reason) stops the block, retaining metadata but discarding candidate bytes on exit.
succeed() requires candidate bytes; the recipe performs encoding and size acceptance before calling it.
Encoding and savings policy live in recipe functions, outside the context.

After the block, outcome() returns the existing (ImageOptimizationResult, accepted bytes or None)
shape. Ordinary exceptions are classified by ImageErrorReason.from_error; missing completion
becomes UNKNOWN. Cleanup failure overrides success or skip, while a processing failure retains
its classification if cleanup also fails. Diagnostics are logged. Interrupts propagate after
cleanup and leave no completed result. The working image reference is cleared on exit.

## Planned decisions and execution

Decision functions accept the context, read original information and earlier target choices,
and modify target_image_info or target_quality without transforming the working image.
Execution then applies target dimensions and mode, saves using the target format and quality,
checks savings, and accepts the candidate through separate functions. Reuse ImageInfo for all
three roles without another metadata class. Original metadata remains unchanged.

PNG-to-JPEG density policy uses original encoded filesize divided by planned pixel area.
JPEG recompression can be eligible even when target dimensions, mode, and format match the input;
save eligibility is a separate decision. Quality is an output setting, not inferred input metadata.
Alpha inspection order remains to be settled during migration: current policy examines resized
pixels, so moving inspection to original pixels can change decisions near the threshold.

## Parallel image recipe

recipe.optimize_image_with_context accepts the same bytes and keyword arguments as
optimization.optimize_image. It opens inside the context and verifies minimum size, supported
format, and animation policy. Independent operations then resize, remove useless PNG alpha,
and select a format conversion. The needs_encoding check skips unchanged images unless JPEG
density or ZIP compression warrants re-encoding. Encoding selection and saving follow that
check; savings acceptance and success follow saving. Until the decision/execution migration,
resize and alpha removal still act directly on the working image; target size/mode are initialized
but do not yet drive those operations.

resize_image changes dimensions only. remove_useless_alpha changes pixel mode only.
png_to_jpeg unconditionally selects JPEG output when called; save_image produces the JPEG bytes.
The default recipe decides whether to invoke it using convert_inefficient_png_to_jpeg (PNG, RGB,
and post-resize density). The convert_png_to_jpeg keyword remains only on recipe/adapter entry
points for compatibility; it controls invocation, not context state.
select_encoding sets target_quality without manipulating the image or deciding eligibility:
PNG-to-JPEG uses 85, JPEG input uses 75, GIF uses 85, and PNG has no quality argument.
save_image encodes the working image using target format and quality, then records
candidate bytes and current metadata. Metadata survives rejected savings.

verify(*checks) takes ordinary functions returning None on success or an ImageSkipReason on
failure; the first failure stops the recipe. Operations keep their conditional behavior inside
ordinary functions, without operation classes. Operations rely on recipe ordering instead of
repeated image/candidate readiness assertions; the image property provides the working image.
The earlier per-format process_png/jpeg/gif functions are superseded by these independent
operations and the needs_encoding check.

Synthetic comparisons cover outcomes, metadata, and accepted bytes, including configured
bounds, modes, transparency, animations, size/compression boundaries, invalid/truncated data,
and injected processing failures. The existing optimizer remains active until the final
pipeline and performance comparisons are finished.

A spawned-worker regression test sends only bytes and configuration into a worker, creates the
context and Pillow objects there, and returns detached results and bytes. Repeated success,
error, skip, and format-preserving calls in the same worker match synchronous calls without
sharing image state. No image-level parallel scheduler is added to production code.
