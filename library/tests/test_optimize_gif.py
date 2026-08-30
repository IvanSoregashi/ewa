"""Exercise every optimize_gif strategy against the real sample animations.

For each optimization function: optimized gifs are written to
samples/images/<function_name>/ and a savings report table is printed.
"""

from pathlib import Path

from PIL import Image

from library.image.optimize_gif import downscale_frames, drop_frames, reindex_palette, resave_optimized

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
        print(" | ".join(str(r[h]).ljust(widths[h]) for h in headers))


OPTIMIZERS = {
    "resave_optimized": resave_optimized,
    "reindex_palette_128": lambda im, size: reindex_palette(im, size, colors=128),
    "drop_half": lambda im, size: drop_frames(im, size, keep_every=2),
    "downscale_half": lambda im, size: downscale_frames(im, size, factor=0.5),
}


def test_optimize_all_samples():
    rows = []
    for name, func in OPTIMIZERS.items():
        out_dir = SAMPLES / name
        out_dir.mkdir(exist_ok=True)
        for path in sorted(SAMPLES.glob("*.gif")):
            original_size = path.stat().st_size
            with Image.open(path) as image:
                if not getattr(image, "is_animated", False):
                    continue
                new_bytes, info = func(image, original_size)
                (out_dir / path.name).write_bytes(new_bytes)
                rows.append({
                    "function": name,
                    "file": path.name,
                    "original_kb": round(original_size / 1024),
                    "new_kb": round(len(new_bytes) / 1024),
                    "savings_%": info["savings_percent"],
                })

    print()
    headers = list(rows[0])
    widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
    print(" | ".join(h.ljust(widths[h]) for h in headers))
    print("-+-".join("-" * widths[h] for h in headers))
    for row in rows:
        print(" | ".join(str(row[h]).ljust(widths[h]) for h in headers))
    assert rows, "no animated samples processed"
