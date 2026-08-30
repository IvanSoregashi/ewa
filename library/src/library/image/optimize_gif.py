"""Experimental animated-GIF optimization functions.

Each function takes an open PIL GIF image plus the original byte size, and
returns optimized bytes plus a small info dict. Shared contract:

    optimize_<name>(image: Image.Image, original_size: int, **params)
        -> (bytes, dict)

Frame metadata (durations, loop) is preserved; the strategies differ in how
aggressively they rebuild the frame sequence.
"""

import io

from PIL import Image, ImageSequence


def _savings_percent(original_size: int, new_bytes: bytes) -> float:
    if original_size <= 0:
        return 0.0
    return round(100.0 * (1 - len(new_bytes) / original_size), 1)


def resave_optimized(image: Image.Image, original_size: int) -> tuple[bytes, dict]:
    """Re-encode as-is: let Pillow do interframe diffing and palette cleanup."""
    frames, durations = [], []
    for frame in ImageSequence.Iterator(image):
        durations.append(frame.info.get("duration", 100))
        frames.append(frame.copy())

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=image.info.get("loop", 0),
        optimize=True,
    )
    new_bytes = buffer.getvalue()
    return new_bytes, {"frames": len(frames), "savings_percent": _savings_percent(original_size, new_bytes)}


def reindex_palette(image: Image.Image, original_size: int, colors: int = 128) -> tuple[bytes, dict]:
    """Quantize every frame to one shared adaptive palette of `colors` entries."""
def reindex_palette(image: Image.Image, original_size: int, colors: int = 128) -> tuple[bytes, dict]:
    """Quantize every frame to one shared adaptive palette of `colors` entries."""
    frames, durations = [], []
    base_palette = None
    for frame in ImageSequence.Iterator(image):
        if base_palette is None:
            base_palette = frame.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
        # quantize-to-palette requires RGB/L source; GIF frames are P or RGB(A)
        quantized = frame.convert("RGB").quantize(palette=base_palette, dither=Image.Dither.NONE)
        quantized.info.pop("transparency", None)  # stale tuple index breaks the GIF encoder
        frames.append(quantized)
        durations.append(frame.info.get("duration", 100))

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=image.info.get("loop", 0),
        optimize=True,
    )
    new_bytes = buffer.getvalue()
    return new_bytes, {"colors": colors, "frames": len(frames), "savings_percent": _savings_percent(original_size, new_bytes)}


def drop_frames(image: Image.Image, original_size: int, keep_every: int = 2) -> tuple[bytes, dict]:
    """Keep every Nth frame, stretching durations to preserve total runtime."""
    all_durations = [frame.info.get("duration", 100) for frame in ImageSequence.Iterator(image)]
    frames = [frame.copy() for frame in ImageSequence.Iterator(image)][::keep_every]
    kept_durations = [
        sum(all_durations[i : i + keep_every]) for i in range(0, len(all_durations), keep_every)
    ]

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=kept_durations,
        loop=image.info.get("loop", 0),
        optimize=True,
    )
    new_bytes = buffer.getvalue()
    return new_bytes, {
        "frames_before": len(all_durations),
        "frames_after": len(frames),
        "savings_percent": _savings_percent(original_size, new_bytes),
    }


def downscale_frames(image: Image.Image, original_size: int, factor: float = 0.5) -> tuple[bytes, dict]:
    """Resize every frame; the heavy hammer for oversized animations."""
    new_size = (max(1, int(image.width * factor)), max(1, int(image.height * factor)))
    frames, durations = [], []
    for frame in ImageSequence.Iterator(image):
        resized = frame.convert("RGBA").resize(new_size, Image.Resampling.LANCZOS)
        durations.append(frame.info.get("duration", 100))
        frames.append(resized)

    buffer = io.BytesIO()
    frames[0].save(
        buffer, format="GIF", save_all=True, append_images=frames[1:], duration=durations,
        loop=image.info.get("loop", 0), optimize=True,
    )
    new_bytes = buffer.getvalue()
    return new_bytes, {"new_size": frames[0].size, "savings_percent": _savings_percent(original_size, new_bytes)}
