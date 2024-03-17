
class ErrorMessage(Exception):
    def __init__(self, error_code, error_message="An error has occurred"):
        self.error_code = error_code
        super().__init__(error_message)
