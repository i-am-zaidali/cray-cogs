class CategoryAlreadyExists(Exception):
    """
    Exception raised when a category already exists.
    """
    def __init__(self, message: str, name: str) -> None:
        self.message = message
        self.name = name
        super().__init__(message, name)