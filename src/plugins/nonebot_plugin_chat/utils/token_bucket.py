class TokenBucket:

    def __init__(self, max_token: int, min_token: int) -> None:
        self.max_token = max_token
        self.min_token = min_token
        self.token = 0

    def add(self, token: float) -> None:
        self.token = min(self.token + token, self.max_token)

    def consume(self, token: float) -> float:
        self.token = max(self.token - token, self.min_token)
        return self.token

    def get(self) -> float:
        return self.token

    def __str__(self) -> str:
        return str(round(self.token, 1))
