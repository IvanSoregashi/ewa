from enum import IntEnum


class EpubError(Exception): ...


class EpubSpecificationError(EpubError): ...


class EpubSkipReason(IntEnum):
    DESTINATION_EXISTS = 1
    NOT_IMPLEMENTED = 2
    INCORRECT_DIRECTORY = 3
    NON_DEFAULT_OPF = 4


class EpubErrorReason(IntEnum):
    UNKNOWN = 1
    INCORRECT_RESULT = 2
