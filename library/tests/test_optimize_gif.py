"""Exercise every optimize_gif strategy against the real sample animations.

For each optimization function: optimized gifs are written to
samples/images/<function_name>/ and a savings report table is printed.
"""

from pathlib import Path

import pytest
from PIL import Image

from library.image.optimize_gif import (
    convert_to_mp4,
    convert_to_webp,
    downscale_frames,
    downscale_then_webp,
    drop_frames,
    gifsicle_optimize,
    reindex_palette,
    resave_optimized,
)

SAMPLES = Path(__file__).parent / "samples" / "images"


def savings_percent(original_size: int, new_bytes: bytes) -> float:
    if original_size <= 0:
        return 0.0
    return round(100.0 * (1 - len(new_bytes) / original_size), 1)


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("no rows")
        return
    headers = list(rows[0])
    widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
    print(" | ".join(h.ljust(widths[h]) for h in headers))
    print("-+-".join("-" * widths[h] for h in headers))
    for row in rows:
        print(" | ".join(str(row[h]).ljust(widths[h]) for h in headers))


OPTIMIZERS = {
    "resave_optimized": lambda im, size, src: resave_optimized(im, size),
    "reindex_palette_128": lambda im, size, src: reindex_palette(im, size, colors=128),
    "drop_half": lambda im, size, src: drop_frames(im, size, keep_every=2),
    "downscale_half": lambda im, size, src: downscale_frames(im, size, factor=0.5),
    "convert_to_webp_q80": lambda im, size, src: convert_to_webp(im, size, quality=80),
    "downscale_webp": lambda im, size, src: downscale_then_webp(im, size, factor=0.5, quality=80),
    "ffmpeg_mp4_crf23": lambda im, size, src: convert_to_mp4(im, size, crf=23, source_bytes=src),
    "ffmpeg_mp4_crf30": lambda im, size, src: convert_to_mp4(im, size, crf=30),
    "gifsicle_lossy80": lambda im, size, src: gifsicle_optimize(im, size, lossy=80, colors=128, source_bytes=src),
}

@pytest.mark.skip()
def test_optimize_all_samples():
    rows = []
    for name, func in OPTIMIZERS.items():
        out_dir = SAMPLES / name
        out_dir.mkdir(exist_ok=True)
        for path in sorted(SAMPLES.glob("*.gif")):
            original_size = path.stat().st_size
            source_bytes = path.read_bytes()  # for external tools: skip PIL re-encode
            with Image.open(path) as image:
                if not getattr(image, "is_animated", False):
                    continue
                new_bytes, info = func(image, original_size, source_bytes)
                if new_bytes is None:
                    rows.append(
                        {
                            "function": name,
                            "file": path.name,
                            "original_kb": round(original_size / 1024),
                            "new_kb": "-",
                            "savings_%": info.get("skipped", "skipped"),
                        }
                    )
                    continue
                suffix = (
                    ".mp4" if info.get("format") == "mp4" else (".webp" if info.get("format") == "webp" else ".gif")
                )
                (out_dir / (path.stem + suffix)).write_bytes(new_bytes)
                rows.append(
                    {
                        "function": name,
                        "file": path.name,
                        "format": info.get("format", "gif"),
                        "original_kb": round(original_size / 1024),
                        "new_kb": round(len(new_bytes) / 1024),
                        "savings_%": info["savings_percent"],
                    }
                )

    print()
    headers = list(rows[0])
    widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
    print(" | ".join(h.ljust(widths[h]) for h in headers))
    print("-+-".join("-" * widths[h] for h in headers))
    for row in rows:
        print(" | ".join(str(row[h]).ljust(widths[h]) for h in headers))
    assert rows, "no animated samples processed"
