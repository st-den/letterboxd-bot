import io
import re
from random import choice
from string import punctuation

from PIL import Image, ImageFont
from pilmoji import Pilmoji
from pilmoji.source import AppleEmojiSource

with open("positive_texts.txt") as f:
    POSITIVE_TEXTS = f.read().split("\n\n")


def _image_to_bytes(image):
    bio = io.BytesIO()
    bio.name = "image.png"
    image.save(bio, format="PNG")
    bio.seek(0)
    return bio


def _draw_centered(image, position, text, font, text_color):
    lines = [*text.split("\n"), "\n"]
    for i, line in enumerate(lines):
        text = []
        for j, _ in enumerate(lines):
            text.extend(line.strip() if i == j else "\n")

        Pilmoji(image, source=AppleEmojiSource).text(
            position,
            "".join(text),
            font=font,
            anchor="mm",
            fill=text_color,
        )


def create_high_rating_meme(username, poster):
    username = _clean_name(username)
    image = Image.open("good.png").convert("RGBA")
    overlay_image = Image.open(poster)
    overlay_image = overlay_image.resize((220, int(220 * 3 / 2)))
    image.paste(overlay_image, (35, 150))

    username_position = (720, 515)
    text_position = (550, 260)
    username_font = ImageFont.truetype("arial_bold.ttf", size=20)
    text_font = ImageFont.truetype("arial_bold.ttf", size=26)
    text_color = (35, 35, 35)

    Pilmoji(image, source=AppleEmojiSource).text(
        username_position,
        username,
        font=username_font,
        anchor="mm",
        fill=text_color,
    )
    _draw_centered(
        image,
        text_position,
        choice(POSITIVE_TEXTS),
        text_font,
        text_color,
    )

    return _image_to_bytes(image)


def create_low_rating_meme(name, poster):
    name = _clean_name(name)
    image = Image.open("bad.png").convert("RGBA")
    overlay_image = Image.open(poster)
    overlay_image = overlay_image.resize((220, int(220 * 3 / 2)))
    image.paste(overlay_image, (680, 148))

    username_position = (155, 475)
    username_font = ImageFont.truetype("arial_bold.ttf", size=26)
    text_color = (35, 35, 35)

    Pilmoji(image, source=AppleEmojiSource).text(
        username_position,
        name,
        font=username_font,
        anchor="mm",
        fill=text_color,
    )

    return _image_to_bytes(image)


def _clean_name(name):
    emojis = r"[^\w\s" + re.escape(punctuation) + "]"
    name = re.sub(r"(?<=\S)" + f"({emojis})", r" \1", name)
    return re.sub(f"({emojis})" + r"(?=\S)", r"\1 ", name)
