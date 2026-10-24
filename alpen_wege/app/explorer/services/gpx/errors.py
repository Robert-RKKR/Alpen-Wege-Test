class GpxProcessingError(Exception):
    def __init__(self, code: str, user_message: str):
        self.code = code
        self.user_message = user_message
        super().__init__(f"[{code}] {user_message}")
