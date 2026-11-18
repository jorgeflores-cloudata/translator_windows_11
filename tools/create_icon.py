"""Generate the original Dova Translator icon (requires Pillow for this build step)."""
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "assets"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" role="img" aria-labelledby="title desc">
  <title id="title">Dova Translator</title>
  <desc id="desc">A teal voice bubble and a white translated-message bubble on a deep navy rounded tile.</desc>
  <defs>
    <linearGradient id="navy" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#173447"/><stop offset="1" stop-color="#0B1422"/></linearGradient>
    <linearGradient id="teal" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#38E0C6"/><stop offset="1" stop-color="#0DADAB"/></linearGradient>
    <mask id="front"><rect x="72" y="96" width="304" height="224" rx="58" fill="white"/><path d="M145 298 L107 374 L225 308 Z" fill="white"/></mask>
  </defs>
  <rect width="512" height="512" rx="112" fill="url(#navy)"/>
  <g fill="#F3FAFC"><rect x="232" y="239" width="200" height="149" rx="44"/><path d="M358 378 L420 434 L414 360 Z"/></g>
  <g fill="#173447"><rect x="284" y="339" width="106" height="12" rx="6"/><rect x="284" y="362" width="68" height="12" rx="6"/></g>
  <rect width="512" height="512" fill="url(#teal)" mask="url(#front)"/>
  <g fill="white">
    <rect x="132" y="186" width="22" height="44" rx="11"/>
    <rect x="174" y="164" width="22" height="88" rx="11"/>
    <rect x="216" y="145" width="22" height="126" rx="11"/>
    <rect x="258" y="164" width="22" height="88" rx="11"/>
    <rect x="300" y="186" width="22" height="44" rx="11"/>
  </g>
</svg>
'''


def build_icon():
    scale = 4
    size = 512 * scale

    def box(coords):
        return tuple(int(v * scale) for v in coords)

    def gradient(top, bottom):
        layer = Image.new("RGBA", (size, size))
        pen = ImageDraw.Draw(layer)
        for y in range(size):
            fraction = y / (size - 1)
            color = tuple(round(a + (b - a) * fraction) for a, b in zip(top, bottom))
            pen.line((0, y, size, y), fill=color + (255,))
        return layer

    tile_mask = Image.new("L", (size, size))
    ImageDraw.Draw(tile_mask).rounded_rectangle(box((0, 0, 512, 512)), radius=112 * scale, fill=255)
    icon = gradient((23, 52, 71), (11, 20, 34))
    icon.putalpha(tile_mask)

    pen = ImageDraw.Draw(icon)
    pen.rounded_rectangle(box((232, 239, 432, 388)), radius=44 * scale, fill="#F3FAFC")
    pen.polygon([box(point) for point in ((358, 378), (420, 434), (414, 360))], fill="#F3FAFC")
    pen.rounded_rectangle(box((284, 339, 390, 351)), radius=6 * scale, fill="#173447")
    pen.rounded_rectangle(box((284, 362, 352, 374)), radius=6 * scale, fill="#173447")

    front_mask = Image.new("L", (size, size))
    front_pen = ImageDraw.Draw(front_mask)
    front_pen.rounded_rectangle(box((72, 96, 376, 320)), radius=58 * scale, fill=255)
    front_pen.polygon([box(point) for point in ((145, 298), (107, 374), (225, 308))], fill=255)
    front = gradient((56, 224, 198), (13, 173, 171))
    icon.paste(front, (0, 0), front_mask)
    pen = ImageDraw.Draw(icon)
    for x, height in ((132, 44), (174, 88), (216, 126), (258, 88), (300, 44)):
        top = 208 - height / 2
        pen.rounded_rectangle(box((x, top, x + 22, top + height)), radius=11 * scale, fill="white")

    ASSETS.mkdir(parents=True, exist_ok=True)
    source = icon.resize((512, 512), Image.Resampling.LANCZOS)
    source.save(ASSETS / "dova-translator-512.png")
    source.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS / "dova-translator-256.png")
    source.save(ASSETS / "dova-translator.ico", sizes=[(s, s) for s in ICO_SIZES])
    (ASSETS / "dova-translator.svg").write_text(SVG, encoding="utf-8")
    print(f"Created Dova Translator icon assets in {ASSETS}")


if __name__ == "__main__":
    build_icon()
