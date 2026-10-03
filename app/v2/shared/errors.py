"""Application errors that do not depend on HTTP or persistence frameworks."""


class DomainError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
