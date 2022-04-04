class BankError(Exception):
    def __init__(self, message: str, name: str) -> None:
        self.message = message
        self.name = name
        super().__init__(message, name)


class BankAlreadyExists(BankError):
    """
    Exception raised when a Bank already exists.
    """

    def __init__(self, message, name) -> None:
        super().__init__(message, name)


class BankDoesNotExist(BankError):
    """
    Exception raised when a Bank does not exist.
    """

    def __init__(self, message, name) -> None:
        super().__init__(message, name)


class SimilarBankExists(BankError):
    """
    Exception raised when a Bank with a similar name exists.
    """
    def __init__(self, message, name) -> None:
        super().__init__(message, name)
