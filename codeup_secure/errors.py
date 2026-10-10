class CodeupError(Exception):
    """A fixed, credential-free diagnostic safe to show to a user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
