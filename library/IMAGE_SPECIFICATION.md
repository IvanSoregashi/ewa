# Image processing specification

## Scope and status

This document owns contracts for reusable image processing in library.image, independently
of EPUB workflows. Implementation order lives in [IMAGE_TODO.md](IMAGE_TODO.md);
contributor instructions live in [AGENTS.md](../AGENTS.md).
EPUB resource integration belongs to [EPUB_SPECIFICATION.md](EPUB_SPECIFICATION.md#state-and-ownership).

The existing optimize_image implementation remains active. ImageProcessingContext is planned,
not implemented; implementation awaits an explicit instruction to start.

## Current optimizer contract and policy

optimize_image accepts bytes and the existing configuration and compression arguments.
It owns decoding, encoding, and size acceptance, returning an ImageOptimizationResult and
accepted bytes (None for skip/error). Keep the existing argument names and defaults.

Options include convert_png_to_jpeg=True, min_filesize=50 * 1024 (bytes), and
max_dimensions=None (the existing density-based limits). Explicit dimensions are intended
to bound resizing without upscaling; zero leaves an axis unconstrained, so (0, 0) disables
resizing. Current resizing code and tests need reconciliation with those intended bounds
and the removal of rejected thin-image guards before comparing resize behavior.

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

This refactor is agreed direction, not implemented behavior. `optimize_image` remains the image
recipe entry point; a concrete `ImageProcessingContext` in `library.image` will own one image's
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
