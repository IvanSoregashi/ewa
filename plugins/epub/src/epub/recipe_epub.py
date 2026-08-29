import json
from pathlib import Path
import logging
from ewa.config import settings
from library.asserts import require
from library.epub.epub import EPUB
from library.epub.media_type import FileName, EpubRole
from library.epub import recipe_image, recipe_html
from epub import recipe_analytics, recipe_css, recipe_package

logger = logging.getLogger(__name__)
sp_dictionary_path: Path = settings.profile_dir / "epub" / "serene_panda" / "translator.json"
sp_dictionary = str.maketrans(json.loads(sp_dictionary_path.read_text(encoding="utf-8")))


def fully_process_encrypted_panda(path: Path) -> None:
    destination = Path()  # TODO
    try:
        with EPUB(path).stream_to(destination) as epub:
            # 0. standardize the archive layout: opf at the root
            recipe_package.relocate_package(epub)

            # 1. remove font
            fonts = [f for f in epub.resources.by_role(EpubRole.FONT) if "serenepanda" in f.info.filename.lower()]
            font = require(fonts[0] if fonts else None, "serene panda font")
            epub.resources.remove(font)
            epub.core.manifest.remove_by_path(font.info.filename)

            # 2. cleanup css
            for css_resource in epub.resources.by_role(EpubRole.STYLE):
                recipe_css.de_panda_css_resource(css_resource)

            # 3. all image resources - through optimization
            image_optimization_results = [
                recipe_image.perform_image_optimization(image_resource)
                for image_resource in epub.resources.by_role(EpubRole.IMAGE)
            ]

            # 3.1. received statistics - save conversion info to SQL
            recipe_analytics.record_image_statistics(path, image_optimization_results, settings.database_url)

            # 3.2. received statistics - form a path replacement dictionary
            # (keys/values are archive paths; opf is at the root, so manifest hrefs match)
            replacement_dict = {}
            for result in image_optimization_results:
                if result.success and result.new_image and result.new_image.path is not None:
                    replacement_dict[result.original_image.path] = result.new_image.path

            # 4. for the html resources:
            #    - if path replacement dictionary - make replacements
            #    - translate
            for html_resource in epub.resources.by_role(EpubRole.HTML):
                if replacement_dict:
                    recipe_html.replace_links(html_resource, replacement_dict)
                recipe_html.translate_text(html_resource, sp_dictionary)

            # 5. package: apply renames to the manifest, drop the font item from
            #    the package document itself, and sync the parsed package into its resource
            if replacement_dict:
                recipe_package.replace_links(epub, replacement_dict)
            epub.core.package.manifest.remove_item(path=font.info.filename)
            epub.core.package_resource.content = epub.core.package.to_xml_bytes()

    except Exception as e:
        logger.error(f"EPUB FAIL {path}, error: {e}")
    # if no error, move original to archive/encrypted completed
    # if error, move to quarantine
