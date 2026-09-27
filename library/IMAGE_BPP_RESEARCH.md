# Image compression density research

## Finding

The sources below do not establish a universal bytes-per-pixel cutoff for deciding that
PNG, JPEG, or GIF is efficiently encoded, or that an image should be resized. Density depends
on content, dimensions, pixel representation, encoder settings, and (for lossy formats)
accepted distortion. Treat our thresholds as provisional policy, not format properties.

## Units

ImageInfo.bytes_per_pixel is encoded file bytes divided by width × height. Compression papers
usually use **bits** per pixel. The conversion is bits/pixel = 8 × bytes/pixel.

| Current threshold (bytes/pixel) | Equivalent bits/pixel | Current policy role |
| --- | --- | --- |
| 0.1 | 0.8 | JPEG below this value gets the 2560-pixel default width limit |
| 0.2 | 1.6 | PNG below this value gets the 2560-pixel default width limit |
| 0.5 | 4.0 | RGB PNG at/above this value is eligible for a JPEG trial; JPEG at/above it is eligible for recompression |

Other default widths are 1080; explicit max_dimensions overrides density policy. GIF keeps
the existing 1080 default without adding an unsupported density threshold.

## Published measurements

Google's [JPEG/WebP compression study](https://developers.google.com/speed/webp/docs/webp_study)
compares encoded sizes at matched SSIM and plots rate versus distortion, rather than defining
an efficiency boundary. Its 512 × 512 Lenna example reports these JPEG sizes:

| JPEG quality setting | Reported size | Approximate bytes/pixel |
| --- | --- | --- |
| 50 | 23.5 KB | 0.09 |
| 75 | 37.0 KB | 0.14 |
| 95 | 104 KB | 0.40 |

The last column is our rounded conversion; the source labels sizes KB. These are one image
and historical libjpeg 6b settings, not quality guarantees or measurements of our Pillow encoder.
The study also separates photographic test sets from heterogeneous web images. Our inference:
0.1 or 0.5 cannot tell us whether a JPEG is already optimal or whether its resolution is excessive.

Google's [lossless and alpha study](https://developers.google.com/speed/webp/docs/webp_lossless_alpha_study)
reports the following ZopfliPNG densities (Table 1):

| Data | Reported bits/pixel | Converted bytes/pixel |
| --- | --- | --- |
| One photographic benchmark image | 12.2 | 1.525 |
| One graphical benchmark image | 1.05 | 0.13125 |
| 12,000-image web corpus | 5.05 | 0.63125 |

These are optimized lossless PNGs. The photo and graphic rows each represent one image,
not distributions of all photos or graphics. Nevertheless, the spread demonstrates why
0.2 bytes/pixel cannot be a universal limit for an efficient PNG. High density may reflect
detail or noise that lossless compression must preserve. These data do not directly compare
PNG with JPEG at a common quality level.

The [libjpeg-turbo quality/size study](https://libjpeg-turbo.org/About/SmartScale-Lossy)
varies quality and chroma subsampling and reports content-dependent ratios and distortion.
It also documents visible artifacts missed by a numerical similarity measure. This supports
using visual review alongside measurements when calibrating policy for covers, scans, or text.

The PNG project's [compression guidance](https://www.libpng.org/pub/png/book/chapter09.html)
recommends JPEG for photographic content when its loss is acceptable, and PNG/GIF for
limited-color graphics and sharp edges. Pixel depth and PNG filtering also affect size.
This is content-based guidance, not evidence for a single GIF or PNG BPP boundary.

## Implementation decision

Retain 0.1, 0.2, and 0.5 as explicit, provisional heuristics. No reviewed source justifies
replacing them with another universal number. Conversion trials measure actual encoded size
at unchanged dimensions; percentage BPP improvement then equals percentage byte savings.
Keep the existing whole-percent acceptance rule: int(after_bytes / before_bytes × 100) <= 97.
This preserves the existing cutoff, including acceptance of a 97.9% ratio; it is not a
research-derived perceptual-quality threshold.

Resize decisions use the accepted current encoding's density. Resize acceptance compares
byte counts against that accepted image, since changing pixel area makes a BPP-improvement
comparison unsuitable. Retain working Pillow pixels across the trial so a second encode
after resizing does not require decoding the intermediate JPEG.

Before changing the heuristic values, collect per-format and per-content measurements from
representative copies of our images: original/converted/resized dimensions, bytes/pixel,
byte savings, encoder settings, runtime, and visual quality. Examine distributions and
text/edge preservation rather than selecting a cutoff from an average. That calibration,
and the final real-book comparison, remain separate work; this research used no book files.
