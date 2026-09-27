from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
import multiprocessing
import os
import random

from PIL import Image

from library.image.models import ImageErrorReason, ImageSkipReason
from library.image.recipe import optimize_image


def process_image(content, options):
    # Only bytes/configuration enter the worker; its recipe creates all live objects.
    return os.getpid(), optimize_image(content, **options)


def test_spawned_worker_returns_detached_outcomes_and_has_no_cross_call_state():
    with BytesIO() as buffer, Image.frombytes("RGB", (128, 128), random.Random(9).randbytes(128 * 128 * 3)) as image:
        image.save(buffer, format="PNG")
        content = buffer.getvalue()
    cases = [
        (content, {"min_filesize": 0}),
        (b"invalid", {}),
        (content, {"min_filesize": len(content) + 1}),
        (content, {"min_filesize": 0, "convert_png_to_jpeg": False, "max_dimensions": (64, 32)}),
        (content, {"min_filesize": 0}),
    ]
    expected = [optimize_image(data, **options) for data, options in cases]
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        actual = [pool.submit(process_image, data, options).result(timeout=60) for data, options in cases]
    assert all(pid != os.getpid() for pid, _ in actual)
    assert len({pid for pid, _ in actual}) == 1
    assert [outcome for _, outcome in actual] == expected
    assert expected[0][0].success and expected[3][0].success
    assert expected[1][0].error == ImageErrorReason.DECODE_FAILED
    assert expected[2][0].skip == ImageSkipReason.SMALL_IMAGE
    assert expected[0] == expected[-1]
    assert expected[0][0].original_image is not expected[-1][0].original_image
