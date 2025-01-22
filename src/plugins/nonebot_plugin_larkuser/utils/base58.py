import string

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(user_id: str) -> str:
    number = int(user_id, 16)
    if number == 0:
        return BASE58_ALPHABET[0]
    encoded = ""
    while number > 0:
        number, remainder = divmod(number, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    return encoded


def base58_decode(encoded: str) -> str:
    decoded = 0
    for char in encoded:
        decoded = decoded * 58 + BASE58_ALPHABET.index(char)
    return hex(decoded)[2:].upper()
