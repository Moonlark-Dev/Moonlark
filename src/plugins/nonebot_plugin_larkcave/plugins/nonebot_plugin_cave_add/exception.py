from ...models import CaveData

class ReviewFailed(Exception):
    def __init__(self, reason: str, *args: object) -> None:
        super().__init__(*args)
        self.reason = reason

class DuplicateCave(Exception):
    def __init__(self, cave: CaveData, score: float, *args: object) -> None:
        super().__init__(*args)
        self.cave = cave
        self.score = score


class EmptyImage(Exception):
    pass
