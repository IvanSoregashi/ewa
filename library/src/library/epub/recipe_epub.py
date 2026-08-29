from pathlib import Path
import logging
from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import FileName, EpubRole
from library.epub.recipe_css import de_panda_css_resource
from library.epub.recipe_image import perform_image_optimization


logger = logging.getLogger(__name__)


def fully_process_encrypted_panda(path: Path) -> None:
    destination = Path()  # TODO
    try:
        with EPUB(path).stream_to(destination) as epub:
            # 1. remove font
            font = require(epub.resources.by_path(FileName.SP_FONT), FileName.SP_FONT)
            epub.resources.remove(font)
            # 2. cleanup css
            for css_resource in epub.resources.by_role(EpubRole.STYLE):
                de_panda_css_resource(css_resource)
            # 3. all image resources - through optimization
            image_optimization_results = [
                perform_image_optimization(image_resource) for image_resource in epub.resources.by_role(EpubRole.IMAGE)
            ]

            for image_optimization_result in image_optimization_results:
                if image_optimization_result.success:
                    continue
                if image_optimization_result.skip:
                    continue
                if image_optimization_result.error:
                    continue

            # 3.1 received statistics - save conversion info to SQL
            # 3.2 received statistics - form a path replacement dictionary
            # 4. for the html spine resources
            #        translate
            #        if path replacement dictionary - make replacements
            # 5. package
            #        if path replacement dictionary - make replacements
            #        remove font
    except Exception as e:
        logger.error(f"EPUB FAIL {path}, error: {e}")
    # if no error, move original to archive/encrypted completed
    # if error, move to quarantine
