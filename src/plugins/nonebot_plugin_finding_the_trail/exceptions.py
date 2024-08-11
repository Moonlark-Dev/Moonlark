class Quited(Exception):
    pass


class CannotMove(Exception):
    def __init__(self, step_index: int) -> None:
        self.step_length = step_index
