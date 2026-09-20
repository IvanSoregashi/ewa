import logging
import time

import typer
from pathlib import Path

from pydantic import DirectoryPath

from epub import recipe_epub, recipe_epubs
from epub.serene_panda.orchestration import move_file_preserving_hierarchy
from ewa.ui import print_success, print_error
from library.epub.media_type import FileName, EpubRole
from library.epub.utils import to_hex_hash
from library.epub.epub import EPUB
from epub.config import settings


app = typer.Typer(help="Epub Plugin")
logger = logging.getLogger("EPUB")


# Entry point for the plugin loader
def plugin():
    return app


@app.callback()
def setup():
    """Initialize the database on first run."""
    pass


@app.command("get-conf")
def get_config(key: str = typer.Argument("")):
    if key:
        print_success(f"{key}={getattr(settings, key, 'not-found')!r}")
    else:
        print_success(f"settings:\n{settings.model_dump_json(indent=4)}")


@app.command("set-conf")
def set_config(key: str = typer.Option("", "-k"), value: str = typer.Option("", "-v")):
    try:
        print_success("before change: " + repr(getattr(settings, key, "not-found")))
        parsed_value: str | bool = value
        match value.lower():
            case "false":
                parsed_value = False
            case "true":
                parsed_value = True
        setattr(settings, key, parsed_value)
        print_success("after change: " + repr(getattr(settings, key, "not-found")))
    except Exception as e:
        print_error(str(e))


@app.command()
def decrypt(epub_path: Path = typer.Argument(exists=True)):
    start = time.time()
    result = recipe_epub.fully_process_encrypted_panda(str(epub_path))
    elapsed = time.time() - start
    print(f"ELAPSED {elapsed:.2f}s")
    if result is None:
        return

    result.report()

    if result.success and result.new_epub and result.new_epub.path:
        Path(result.new_epub.path).unlink(missing_ok=True)


@app.command("dd")
def decrypt_dir(epub_dir: DirectoryPath = typer.Argument(exists=True)):
    start = time.time()
    results = recipe_epubs.fully_process_encrypted_pandas(
        directory=epub_dir,
        max_workers=8,
        flush_size=32,
    )
    elapsed = time.time() - start

    for result in results:
        result.report()

    print(f"ELAPSED {elapsed:.2f}s")


@app.command("il")
def image_log(epub_path: Path = typer.Argument(exists=True)):
    start = time.time()
    recipe_epub.image_stats(str(epub_path))
    elapsed = time.time() - start
    print(f"ELAPSED {elapsed:.2f}s")


@app.command("move-sp")
def move_serene_panda_encrypted_separately():
    start_time = time.time()
    skipped = 0
    moved = 0
    sync_dir = Path(r"C:\Users\Ivan\Sync\Books")
    move = False
    for file in sync_dir.rglob("*.epub"):
        latest_time = time.time()
        if file.is_dir():
            logger.info(f"SKIPPED DIR: {str(file)!r}")
            continue
        try:
            epub = EPUB(file)
            with epub.source.open():
                font = epub.source.getinfo(FileName.SP_FONT)
                font2 = epub.source.getinfo("SerenePanda.ttf")
                font3 = epub.source.getinfo("serenepanda.ttf")

                if font is not None or font2 is not None or font3 is not None:
                    move = True
                if not move:
                    fonts = epub.resources.by_role(EpubRole.FONT)
                    if len(fonts):
                        for font in fonts:
                            if "serenepanda" in font.info.filename.lower():
                                logger.warning(
                                    f"FOUND FONT {time.time() - latest_time:.3f}s {time.time() - start_time:.3f}s: {font.info.filename}"
                                )
                                move = True

        except ValueError as e:
            logger.error(f"ValueError: {str(file)!r} (SKIPPING)\n{e!r}")
            continue
        except (IndexError, AssertionError) as e:
            logger.error(f"RecoverableError: {str(file)!r} (SKIPPING)\n{e!r}")
            break
        except PermissionError as e:
            logger.error(f"PermissionError: {str(file)!r} (SKIPPING)\n{e!r}")
            break
        except Exception as e:
            logger.error(f"Exception: {str(file)!r}\n{e!r}")
            break

        if move:
            move_file_preserving_hierarchy(file, settings.encrypted_epub_dir)
            moved += 1
            move = False
        else:
            skipped += 1
            logger.info(
                f"SKIPPED({skipped:>03}) {time.time() - latest_time:.3f}s {time.time() - start_time:.3f}s: {str(file)!r}"
            )

    logger.warning(f"SKIPPED: {skipped}, MOVED: {moved}, ELAPSED: {time.time() - start_time}")


@app.command("move-ne")
def move_not_epubs():
    epub_dir = settings.epub_dir
    destination = (settings.D_DISK / "OTHER_BOOKS").absolute()
    destination.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    moved = 0
    dirs = list(epub_dir.rglob("*"))

    for file in dirs:
        if file.is_dir():
            logger.info(f"SKIPPED DIR: {str(file)!r}")
            continue
        if file.suffix.lower() == ".epub":
            logger.info(f"SKIPPED EPUB: {str(file)!r}")
            continue
        move_file_preserving_hierarchy(file, destination)
        moved += 1

    logger.info(f"MOVED: {moved}, ELAPSED: {time.time() - start_time}")


@app.command("hash-dups")
def count_hash_duplicates():
    start_time = time.time()
    filehash = {}
    read_files = 0
    errors = 0
    dirpath = Path("D:/OTHER_BOOKS")
    for file in dirpath.rglob("*"):
        if file.is_dir():
            continue

        try:
            fhash = to_hex_hash(file.read_bytes())
            filehash.setdefault(fhash, []).append(str(file))
            read_files += 1

        except Exception as e:
            logger.error(f"Exception: {str(file)!r}\n{e!r}")
            errors += 1
            continue

    logger.warning(
        f"READ/HASHES: {read_files}/{len(filehash)}, DIFF: {read_files - len(filehash)}, ERRORS: {errors}, ELAPSED: {time.time() - start_time:.2f}s"
    )

    deleted_files = 0
    deleted_bytes = 0
    for fhash, files in filehash.items():
        if len(files) == 1:
            continue

        logger.info(f"DUPLICATES {len(files)} - {fhash}")
        for i, f in enumerate(files):
            logger.info(f"\t {i}) {f!r}")
        remain = input("Choose index of remaining file (NAN to SKIP): ")

        try:
            remain = int(remain)
        except ValueError:
            logger.warning(f"Skipping {fhash}")
            continue

        for i, f in enumerate(files):
            if i != remain:
                p = Path(f)
                file_size = p.stat().st_size
                try:
                    p.unlink()
                    deleted_files += 1
                    deleted_bytes += file_size
                    logger.warning(f"REMOVED: {f!r} ({file_size / (1024 * 1024):.2f} MB)")
                except Exception as e:
                    logger.error(f"Exception: {str(f)!r}\n{e!r}")
                    pass

    logger.warning(
        f"REMOVED TOTAL OF: {deleted_files} files, {deleted_bytes / (1024 * 1024):.2f} MB, ELAPSED: {time.time() - start_time:.2f}s"
    )
