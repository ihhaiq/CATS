"""
Composites: breed base asset + emotion state + collar overlay with the cat's
name/id, correctly shaped for Arabic text.
TODO (AGENT.md step 10):
  - emotion_bucket(cat) -> "happy" | "neutral" | "sad": derive from hunger/happiness
    thresholds (mirror the ones in decay_engine / notification thresholds).
  - render_cat(cat) -> bytes (PNG):
      1. base = Image.open(f"assets/cats/{cat.breed}/{emotion_bucket}.png")
      2. draw collar text using shape_arabic(f"{cat.name} | #{cat.id_number}")
      3. cache by (breed, emotion_bucket, cat.title) — recompute only when one of
         those actually changes since the last render (store a cache key on the
         cat row or in Redis, per the caching note in the system prompt).
  - Asset folders must exist per breed: assets/cats/{breed}/{happy,neutral,sad}.png
"""
from io import BytesIO

from PIL import Image, ImageDraw

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:
    arabic_reshaper = None
    get_display = None


def shape_arabic(text: str) -> str:
    """Run this on any Arabic string before drawing it with Pillow — raw Pillow
    draws Arabic glyphs unshaped/disconnected and in visual left-to-right order."""
    if arabic_reshaper is None or get_display is None:
        return text
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def emotion_bucket(cat) -> str:
    if cat.hunger > 70 or cat.happiness < 30:
        return "sad"
    if cat.happiness > 70:
        return "happy"
    return "neutral"


def render_cat(cat) -> bytes:
    image = Image.new("RGB", (800, 500), (245, 232, 210))
    draw = ImageDraw.Draw(image)
    draw.ellipse((220, 95, 580, 455), fill=(224, 153, 92), outline=(74, 49, 38), width=6)
    draw.polygon([(245, 155), (265, 35), (350, 120)], fill=(224, 153, 92), outline=(74, 49, 38))
    draw.polygon([(450, 120), (535, 35), (555, 155)], fill=(224, 153, 92), outline=(74, 49, 38))
    draw.ellipse((315, 205, 345, 240), fill=(30, 25, 20))
    draw.ellipse((455, 205, 485, 240), fill=(30, 25, 20))
    draw.arc((340, 250, 460, 340), 10, 170, fill=(74, 49, 38), width=5)
    draw.rounded_rectangle((245, 375, 555, 430), radius=18, fill=(71, 120, 92))
    label = f"{cat['name']}  #{cat['id_number']}"
    draw.text((270, 392), label, fill="white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
