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
conversion/recompression, keeps the image only if worthwhile, then decides resizing from the
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
The retained optimizer reports rejected candidate metadata. The replacement records rejected
attempts in operations and retains ImageInfo only for accepted states.
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
open_bytes_as_image(content) inside its with block. Opening initializes independent original,
current, and target ImageInfo objects. Entering performs no input opening.

replace_image(image) owns the proposed image, saves it using target format/quality, and compares
its encoded size against the current image. Acceptance requires strictly more than 5% savings:
after_bytes * 100 < before_bytes * 95. This is the replacement recipe's policy; the retained
optimizer keeps its historical whole-percent cutoff.

Until acceptance, the current Pillow image remains live. Acceptance updates current metadata,
candidate bytes, and current_quality, then closes the previous image. Rejection closes only the
proposed image and keeps the current image and accepted bytes. Passing the current image itself
permits format-only conversion or recompression without copying or closing its pixels.
After either decision, target metadata and quality reset to the accepted current state.
current_quality is None for the original input because its encoder quality is unknown.

Images are registered for cleanup before metadata inspection or encoding can fail. All owned
resources are closed on exit, including when another close fails. Use a fresh context per call,
without re-entry guards. There are no preserve/restore/accept calls for the recipe to coordinate.

original_image_info retains captured input metadata, or known byte size if metadata capture fails.
current_image_info describes the accepted working image: dimensions and mode from its pixels,
format from the encoder selection, and filesize from the encoded bytes. ImageInfo.from_image
accepts an explicit format because Pillow transformations have no encoded format. Other header
fields come from the working Pillow image and are not a fresh inspection of output bytes.
target_image_info holds requested size, mode, and format; target_quality holds encoder quality.
Copied target fields such as filesize and extrema are not instructions or predicted output values.

operations contains one dictionary per attempted replacement. It records changed resize/convert/
reformat values, encoder quality when supplied, old_size and new_size in bytes, and accepted.
It does not retain before/after ImageInfo snapshots or pixels. If encoding fails, the incomplete
record retains the requested changes and old size, without new_size or accepted.
Rejected image metadata is discarded. ImageOptimizationResult.new_image describes the most
recent accepted image, or is None when no replacement was accepted.

verify(*checks) runs ordinary callables returning None or an ImageSkipReason, stopping on the
first failed check. The context-local verifications list records each callable and its result;
only detached operation records are included in ImageOptimizationResult.
A normal exit with no attempted replacement produces NOT_OPTIMIZED. If every attempt is
rejected, it produces WORSE_CONVERSION. Any accepted candidate produces success without an
explicit succeed call. A later rejection retains earlier accepted bytes.

After the block, outcome() returns (ImageOptimizationResult, accepted bytes or None).
Ordinary exceptions are classified by ImageErrorReason.from_error. Cleanup failure overrides
success or skip, while a processing failure retains its classification if cleanup also fails.
Errors discard candidate bytes but retain known accepted metadata and operation records.
Interrupts propagate after cleanup. The working image reference is cleared on exit.

## Decisions and execution

Decision functions accept the context, read current information and earlier target choices,
and modify target_image_info or target_quality without transforming pixels or recording an
operation. Reuse ImageInfo for original/current/target without another metadata class.

The default recipe verifies minimum filesize, supported format, and static-image policy.
remove_useless_alpha selects RGB when the original PNG RGBA pixels have minimum alpha >= 250.
This intentionally differs from the retained optimizer's post-resize inspection: resizing can
hide an original alpha value of 249. convert_inefficient_png_to_jpeg selects JPEG for PNG with
planned RGB mode and current density at least 0.5 bytes/pixel. Its public configuration switch
remains on the recipe/adapter entry point and controls whether the decision is called.

select_encoding selects quality independently: 85 for PNG-to-JPEG, 75 for JPEG input,
85 for GIF, and no quality argument for PNG. needs_encoding is a boolean eligibility decision,
not a recipe-ending verification: matching targets can still require JPEG recompression when
density is at least 0.5 bytes/pixel or caller-provided compression is below 75.

When encoding is needed, convert_image applies the target mode if different and passes the
image to replace_image for encoding and acceptance. A format-only change or JPEG recompression
passes the same Pillow object. Conversion is measured at unchanged dimensions, so percentage
BPP improvement equals percentage byte savings.

The recipe next calls select_dimensions using accepted current format and measured BPP.
Explicit bounds take priority; defaults retain 2560 width for PNG below 0.2 bytes/pixel or
JPEG below 0.1, otherwise 1080, including GIF. Rejected conversions have already reset targets.
Encoder settings are selected again for the accepted format, and resize_image applies target
dimensions with LANCZOS only when they differ. It submits the resized image to replace_image,
which compares total encoded bytes with the accepted pre-resize state.

Resizing uses live working pixels, never a decoded intermediate JPEG, avoiding an additional
lossy generation. An accepted conversion with no required resize is not encoded again.
Custom recipes can set targets and call these execution functions without default eligibility
decisions. Exceptions produce an error outcome rather than returning earlier accepted bytes.

Synthetic tests cover supported formats/modes, target independence, strict savings boundaries,
all conversion/resize acceptance combinations, current-density sizing, original-pixel alpha
decisions, ownership, skips, processing/cleanup failures, and interrupts. Worker tests transport
only bytes/configuration and detached outcomes. The retained optimizer and the adapter's
opt-in use_context switch remain until the complete comparison and performance work is done.
