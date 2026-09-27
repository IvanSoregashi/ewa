# Image pipeline validation

## Decision

The context recipe replaces the old optimizer. The public
`library.image.optimization.optimize_image` import and arguments remain supported.
The temporary EPUB `use_context` switch is removed. BPP thresholds and encoder settings
are unchanged; conversion before resizing, current-BPP sizing, original-pixel alpha
inspection, and the strict greater-than-5% savings gate follow the agreed design.

This is behavioral validation, not a claim of identical decisions for different inputs
or a performance improvement. In particular, the old PNG conversion decision used
original bytes divided by resized area; the new decision measures density before resizing.
An accepted conversion/recompression can also change the subsequent resize limit.

## Six-book comparison

Compared the old optimizer and context recipe from commit `24d0dc7` using the full Panda
recipe. Used the same six inputs as the earlier comparison, excluding the merged example.
Each run used copies, separate input/output/processed directories, and a fresh analytics
database. SHA-256 checks confirmed originals stayed unchanged. No book text or images
were displayed. ZIP CRC checks and decoding of every accepted image passed.

| Input | Images | Accepted, both | Old EPUB bytes | New EPUB bytes | Changed images |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 24 | 21 | 9,640,059 | 11,196,104 | 4 |
| 2 | 1 | 1 | 214,125 | 214,125 | 0 |
| 3 | 6,692 | 2 | 76,901,875 | 76,901,875 | 0 |
| 4 | 35 | 32 | 10,495,955 | 10,495,955 | 0 |
| 5 | 1 | 0 | 980,774 | 980,774 | 0 |
| 6 | 2 | 1 | 410,208 | 410,208 | 0 |

All 6,755 per-image success/skip/error outcomes and original metadata matched. Both accepted
57 images with zero errors. Five complete EPUB outputs were byte-identical. Unchanged
accepted image bytes also had matching size, mode, format, and byte-count metadata.
Persisted 12 processing runs and 13,510 image records; SQLite integrity and foreign-key
checks passed. Rejected-attempt metadata differences are covered by synthetic tests.

The four changed images in input 1 were 3780 × 5669 JPEGs. Accepted recompression lowered
their BPP below 0.1, so the new resize decision chose 2560 × 3839 instead of 1080 × 1619.
These are the only output differences, and they follow current-BPP sizing:

| Image index | Original bytes | Recompressed bytes | Old final bytes | New final bytes |
| --- | ---: | ---: | ---: | ---: |
| 0, 17 | 3,877,306 | 713,525 | 133,614 | 422,333 |
| 16 | 3,547,398 | 676,034 | 122,730 | 396,090 |
| 18 | 10,987,517 | 1,665,585 | 276,509 | 981,756 |

## Density and visual review

Reviewed copies of two landscape photographs, an illustrated graphic, a diagram, a JPEG
text sheet, and a synthetic PNG with small text, one-pixel lines, and colored rectangles.
Compared whole images and detail crops at output resolution. All six pairs of old/new
outputs were byte-identical. This sample spans content types but is too small to calibrate
universal thresholds; retain the provisional values described in [BPP research](IMAGE_BPP_RESEARCH.md).

| Content | Input bytes/pixel | Result | Visual observation |
| --- | ---: | --- | --- |
| Photo A, JPEG | 0.3580 | 6000 × 4000 → 1080 × 720 | Fine rock detail softened at quality 75; same in both recipes |
| Photo B, JPEG | 0.4626 | 4000 × 6000 → 1080 × 1620 | Fine branches and terrain softened; no additional migration difference |
| Illustrated graphic, PNG | 1.6881 | JPEG at unchanged 1024 × 1024 | Lettering remains readable; slight edge/texture changes from lossy encoding |
| Diagram, PNG | 0.1287 | Alpha removed; dimensions and PNG retained | Colored lines and edges retained |
| Text sheet, JPEG | 0.1343 | 1280 × 1638 → 1080 × 1382 | Reviewed text remains readable; resampling and JPEG soften edges |
| Synthetic text/lines, PNG | 0.0506 | Original retained | Resize grew 291,734 bytes to 464,411 and was correctly rejected |

Low BPP does not guarantee a smaller result after resizing, and high BPP alone does not
establish acceptable lossy quality. Nothing in these observations supports changing 0.1,
0.2, or 0.5. Visual review here does not establish acceptable quality for every book or device.

## Work, time, and memory

The full comparison counted 6,755 image opens and 60 pixel decodes for each implementation.
Encoding calls rose from 57 to 62 because conversion/recompression can be tried before
resizing. Live pixels are reused: intermediate JPEG bytes are not decoded, and format-only
conversion/recompression does not copy the image. Tests also cover source-read counts,
immediate closing of rejected/obsolete images, and transport of detached results through
spawned workers. Worker tests establish correctness, not a transport-speed improvement.

Instrumented full-recipe elapsed totals were 40.69 s old and 43.41 s new; time inside the
optimizers was 19.85 s and 20.67 s. These include instrumentation overhead and one run per
book, so they are not controlled throughput measurements.

Standalone timing used a fresh process per input/implementation, three repetitions per
larger image, and 1,000 for the small skip. RSS was sampled every 2 ms, excluding process
startup and input acquisition; peaks include the Python process and repeated-call allocator
retention. Medians and observed peaks on this Windows/Python 3.14 environment:

| Case | Old/new median ms | Old/new peak RSS MiB |
| --- | ---: | ---: |
| Small PNG skip | 0.021 / 0.048 | 29.6 / 29.7 |
| Diagram | 171.4 / 188.2 | 44.1 / 43.9 |
| Illustrated graphic | 41.5 / 54.6 | 34.8 / 36.0 |
| Photo A | 522.3 / 542.7 | 149.9 / 150.1 |
| Photo B | 712.6 / 546.3 | 164.9 / 164.2 |
| Synthetic text | 435.0 / 456.9 | 83.0 / 83.9 |
| Text sheet | 86.1 / 81.0 | 50.1 / 49.1 |

There is no demonstrated speedup. Cheap skips add about 27 microseconds; larger timings
vary, and measured memory is comparable. Additional stage encodings are intentional work.

## Reproduction and regression coverage

The validation checkout's local `.image-validation/` directory contains the comparison and measurement
scripts, frozen legacy optimizer, input hashes, per-image JSON, fresh database, copied books,
and standalone review sheets. It is ignored because it contains private samples and large
outputs. The legacy source can also be recovered from the commit above. For a new comparison,
use a fresh artifact directory/database, the same input copies and dictionary, the full
Panda recipe, and record each image's outcome, metadata, output hash, opens, decodes, and saves.

Synthetic coverage exercises supported formats/modes, gate and BPP boundaries, explicit
dimensions, strict savings, conversion/resize acceptance combinations, alpha ordering,
current-density resizing, corruption, encoder/cleanup failures, interrupts, and workers.
After removing the old implementation, byte expectations use direct Pillow encodings
rather than comparing two aliases of the same function. EPUB coverage includes rename
collisions, unchanged resources on skips/errors, manifest identity and dependent cover
references, export/reopen, fresh analytics, and full synchronous/spawned recipes.
