from enum import StrEnum


class DCMetadataType(StrEnum):
    TITLE = "title"
    CREATOR = "creator"
    SUBJECT = "subject"
    DESCRIPTION = "description"
    PUBLISHER = "publisher"
    CONTRIBUTOR = "contributor"
    DATE = "date"
    TYPE = "type"
    FORMAT = "format"
    IDENTIFIER = "identifier"
    SOURCE = "source"
    LANGUAGE = "language"
    RELATION = "relation"
    COVERAGE = "coverage"
    RIGHTS = "rights"


class MetadataType(StrEnum):
    META = "meta"
    DC_META = "meta"
