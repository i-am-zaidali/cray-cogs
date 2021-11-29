class CategoryError(Exception):
    def __init__(self, message: str, name: str) -> None:
        self.message = message
        self.name = name
        super().__init__(message, name)


class CategoryAlreadyExists(CategoryError):
    """
    Exception raised when a category already exists.
    """

    def __init__(self, message, name) -> None:
        super().__init__(message, name)


class CategoryDoesNotExist(CategoryError):
    """
    Exception raised when a category does not exist.
    """

    def __init__(self, message, name) -> None:
        super().__init__(message, name)


class SimilarCategoryExists(CategoryError):
    """
    Exception raised when a category with a similar name exists.
    """

    def __init__(self, message, name) -> None:
        super().__init__(message, name)
