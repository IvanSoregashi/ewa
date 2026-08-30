"""Experimental GIF optimization functions.

Pillow-based strategies share the contract:

    optimize_<name>(image: Image.Image, original_size: int, **params)
        -> (bytes, dict)

External-tool strategies (ffmpeg, gifsicle) operate on file paths via
subprocess and are guarded by shutil.which, so the module works on machines
without them (functions return None + skip note in that case).
"""

import io
import shutil
import subprocess
import tempfile

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


def convert_to_webp(
    image: Image.Image,
    original_size: int,
    quality: int = 80,
    method: int = 4,
) -> tuple[bytes, dict]:
    """Transcode the animation to animated WebP: modern video-style temporal
    compression, Pillow-native (no external tools)."""
    frames, durations = [], []
    for frame in ImageSequence.Iterator(image):
        durations.append(frame.info.get("duration", 100))
        frames.append(frame.convert("RGBA"))

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=image.info.get("loop", 0),
        quality=quality,
        method=method,
    )
    new_bytes = buffer.getvalue()
    return new_bytes, {
        "quality": quality,
        "frames": len(frames),
        "savings_percent": _savings_percent(original_size, new_bytes),
    }


def downscale_then_webp(
    image: Image.Image,
    original_size: int,
    factor: float = 0.5,
    quality: int = 80,
) -> tuple[bytes, dict]:
    """Combined pipeline: downscale every frame, then transcode to WebP."""
    new_size = (max(1, int(image.width * factor)), max(1, int(image.height * factor)))
    frames, durations = [], []
    for frame in ImageSequence.Iterator(image):
        resized = frame.convert("RGBA").resize(new_size, Image.Resampling.LANCZOS)
        durations.append(frame.info.get("duration", 100))
        frames.append(resized)

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=image.info.get("loop", 0),
        quality=quality,
        method=4,
    )
    new_bytes = buffer.getvalue()
    return new_bytes, {
        "format": "webp",
        "new_size": frames[0].size,
        "quality": quality,
        "savings_percent": _savings_percent(original_size, new_bytes),
    }


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None



def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def convert_to_mp4(
    image: Image.Image,
    original_size: int,
    crf: int = 26,
    preset: str = "medium",
    source_bytes: bytes | None = None,
) -> tuple[bytes | None, dict]:
    """Transcode the animation to MP4 (h264) via system ffmpeg.

    When source_bytes are given they are written to disk directly (fast,
    byte-identical to the original); otherwise the open image is re-encoded
    to GIF first (slower). Returns (None, {...skip...}) when ffmpeg is absent.
    """
    if not _tool_available("ffmpeg"):
        return None, {"skipped": "ffmpeg not found"}

    with tempfile.TemporaryDirectory() as tmp:
        source_path = f"{tmp}/source.gif"
        if source_bytes is not None:
            with open(source_path, "wb") as f:
                f.write(source_bytes)
        else:
            image.save(source_path, format="GIF", save_all=True)
        # yuv420p for reader compatibility; even dimensions required by h264
        command = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", source_path,
            "-movflags", "+faststart",
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            f"{tmp}/out.mp4",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            return None, {"skipped": f"ffmpeg failed: {result.stderr[-200:]}"}
        new_bytes = open(f"{tmp}/out.mp4", "rb").read()
        return new_bytes, {
            "format": "mp4",
            "crf": crf,
            "preset": preset,
            "savings_percent": _savings_percent(original_size, new_bytes),
        }


def gifsicle_optimize(
    image: Image.Image,
    original_size: int,
    lossy: int = 80,
    colors: int = 128,
    source_bytes: bytes | None = None,
) -> tuple[bytes | None, dict]:
    """Optimize the GIF via system gifsicle (-O3 --lossy --colors).

    Returns (None, {...skip...}) when gifsicle is not installed.
    """
    if not _tool_available("gifsicle"):
        return None, {"skipped": "gifsicle not found"}

    with tempfile.TemporaryDirectory() as tmp:
        source_path = f"{tmp}/source.gif"
        if source_bytes is not None:
            with open(source_path, "wb") as f:
                f.write(source_bytes)
        else:
            image.save(source_path, format="GIF", save_all=True)
        command = ["gifsicle", "-O3", f"--lossy={lossy}", f"--colors={colors}", "-o", f"{tmp}/out.gif", source_path]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            return None, {"skipped": f"gifsicle failed: {result.stderr[-200:]}"}
        new_bytes = open(f"{tmp}/out.gif", "rb").read()
    return new_bytes, {"lossy": lossy, "colors": colors, "savings_percent": _savings_percent(original_size, new_bytes)}
