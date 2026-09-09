from enum import IntEnum


class EpubError(Exception): ...


class EpubSpecificationError(EpubError): ...


class EpubSkipReason(IntEnum):
    DESTINATION_EXISTS = 1
    NOT_IMPLEMENTED = 2
    INCORRECT_DIRECTORY = 3
    NON_DEFAULT_OPF = 4
    UNMATCHED_LINKS = 5
    MIMETYPE_VERIFICATION = 6
    SERENE_PANDA_FONT = 7
    INVALID_XML_CHAPTERS = 8
    BIG_GIFS = 9


class EpubErrorReason(IntEnum):
    UNKNOWN = 1
    INCORRECT_RESULT = 2
