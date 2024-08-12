from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from nonebot.log import logger


def draw(game_map: list[list[bool]]) -> bytes:
    logger.debug(str(game_map))
    image = Image.new("RGB", (len(game_map[0]) * 20 + 29, len(game_map) * 20 + 34), (0x00, 0x33, 0x66))
    d = ImageDraw.Draw(image)
    x, y = 22, 27
    for row in game_map:
        for col in row:
            if col:
                fill = (0x00, 0x99, 0xFF)
            else:
                fill = None
            d.rectangle((x, y, x + 16, y + 16), fill, (0x00, 0x99, 0xFF))
            x += 20
        y += 20
        x = 22
    d.rectangle((16, 21, len(game_map[0]) * 20 + 24, len(game_map) * 20 + 29), None, (0x00, 0x99, 0xFF), 3)
    y = 27
    font = ImageFont.load_default(16)
    for i in range(len(game_map)):
        d.text((4, y), str(i + 1), (0xFF, 0xFF, 0xFF), font)
        y += 20
    x = 26
    for i in range(len(game_map[0])):
        d.text((x, 2), str(i + 1), (0xFF, 0xFF, 0xFF), font)
        x += 20
    io = BytesIO()
    image.save(io, "PNG")
    return io.getvalue()