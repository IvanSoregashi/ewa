from enum import StrEnum


class FileContents(StrEnum):
    MIMETYPE = "application/epub+zip"
    EWA_ONE = "application/epub+zip+ewa1"


class FileTemplate(StrEnum):
    MIMETYPE = "application/epub+zip"
    CONTAINER = r"""<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile media-type="application/oebps-package+xml" full-path="{opf_path}"/>
  </rootfiles>
</container>
"""
    NCX = r"""<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" />
"""
    NAV = r"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"/>
"""
    CHAPTER = r"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#">
</html>
"""
    COVER = r"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">
  <head></head>
  <body>
    <img src="" alt="" style="height:100%; text-align:center" />
  </body>
</html>
"""
