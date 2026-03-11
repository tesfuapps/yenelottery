"""
utils/poster.py — Winner announcement poster generator using Pillow.
Produces a stylized PNG image announcing the lottery winner.
"""

import io
import logging
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Assets ────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).parent.parent / "assets"
FONT_BOLD   = str(ASSETS_DIR / "NotoSansEthiopic-Bold.ttf")
FONT_REGULAR = str(ASSETS_DIR / "NotoSansEthiopic-Regular.ttf")

# Fallback to built-in if custom fonts aren't present
def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except (IOError, OSError):
        try:
            return ImageFont.truetype("arial.ttf", size)
        except Exception:
            return ImageFont.load_default()


# ── Palette ───────────────────────────────────────────────────────────────────
GOLD    = (255, 195, 0)
DARK_BG = (15, 15, 35)
WHITE   = (255, 255, 255)
SILVER  = (192, 192, 192)
GREEN   = (0, 200, 100)


def generate_winner_poster(
    lottery_title: str,
    winner_name: str,
    winner_ticket: int,
    prize_pool: str,
    total_entries: int,
    draw_seed_short: str,   # first 12 chars of seed for display
) -> io.BytesIO:
    """
    Generate a winner announcement poster.

    Returns:
        BytesIO buffer containing the PNG image.
    """
    WIDTH, HEIGHT = 900, 600
    img = Image.new("RGB", (WIDTH, HEIGHT), color=DARK_BG)
    draw = ImageDraw.Draw(img)

    # ── Background gradient overlay (manual rects) ───────────────────────────
    for i in range(HEIGHT):
        ratio = i / HEIGHT
        r = int(15  + (30  - 15)  * ratio)
        g = int(15  + (20  - 15)  * ratio)
        b = int(35  + (60  - 35)  * ratio)
        draw.line([(0, i), (WIDTH, i)], fill=(r, g, b))

    # ── Gold border ──────────────────────────────────────────────────────────
    border = 8
    draw.rectangle(
        [border, border, WIDTH - border, HEIGHT - border],
        outline=GOLD, width=4
    )

    # ── Fonts ────────────────────────────────────────────────────────────────
    font_title   = _load_font(FONT_BOLD, 48)
    font_winner  = _load_font(FONT_BOLD, 56)
    font_sub     = _load_font(FONT_REGULAR, 28)
    font_small   = _load_font(FONT_REGULAR, 20)
    font_emoji   = _load_font(FONT_REGULAR, 72)

    # ── Header ───────────────────────────────────────────────────────────────
    draw.text((WIDTH // 2, 55), "🏆", font=font_emoji, fill=GOLD, anchor="mm")
    draw.text(
        (WIDTH // 2, 130), "YENE LOTTERY",
        font=font_title, fill=GOLD, anchor="mm"
    )
    draw.text(
        (WIDTH // 2, 180), lottery_title,
        font=font_sub, fill=SILVER, anchor="mm"
    )

    # ── Divider ──────────────────────────────────────────────────────────────
    draw.line([(60, 210), (WIDTH - 60, 210)], fill=GOLD, width=2)

    # ── Winner announcement ───────────────────────────────────────────────────
    draw.text(
        (WIDTH // 2, 255), "🎉 WINNER 🎉",
        font=font_sub, fill=WHITE, anchor="mm"
    )
    draw.text(
        (WIDTH // 2, 325), winner_name,
        font=font_winner, fill=GOLD, anchor="mm"
    )
    draw.text(
        (WIDTH // 2, 385), f"Ticket #{winner_ticket:03d}",
        font=font_sub, fill=GREEN, anchor="mm"
    )

    # ── Prize ────────────────────────────────────────────────────────────────
    draw.line([(60, 415), (WIDTH - 60, 415)], fill=GOLD, width=2)
    draw.text(
        (WIDTH // 2, 445), "🏅 Prize",
        font=font_sub, fill=SILVER, anchor="mm"
    )
    draw.text(
        (WIDTH // 2, 490), prize_pool,
        font=font_title, fill=GOLD, anchor="mm"
    )

    # ── Footer: provably fair details ────────────────────────────────────────
    draw.rectangle([0, HEIGHT - 70, WIDTH, HEIGHT], fill=(10, 10, 25))
    draw.text(
        (WIDTH // 2, HEIGHT - 45),
        f"Total Entries: {total_entries}  •  Seed: {draw_seed_short}...  •  Provably Fair Draw",
        font=font_small, fill=SILVER, anchor="mm"
    )

    # ── Serialize to bytes ───────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
