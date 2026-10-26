"""Builds every brand file under frontend/ from logo.py and mark.py.

    python3 -I tools/brand/build.py

Needs fontTools + brotli (the tagline is Inter, turned into paths), Pillow,
and rsvg-convert (librsvg) for the PNG, WebP and ICO renditions."""
import io, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import logo, mark

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))
BRAND = os.path.join(ROOT, 'assets', 'brand')
os.makedirs(BRAND, exist_ok=True)


def write(path, text):
    with open(path, 'w') as f:
        f.write(text)


def png(svg, w, h=None, bg=None):
    cmd = ['rsvg-convert', '-w', str(w)] + (['-h', str(h)] if h else []) + (['-b', bg] if bg else [])
    out = subprocess.run(cmd, input=svg.encode(), capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(out)).convert('RGBA')


dark, light = logo.logo_svg('dark'), logo.logo_svg('light')
write(f'{BRAND}/axiom-dark.svg', dark)
write(f'{BRAND}/axiom-light.svg', light)
write(f'{BRAND}/mark.svg', mark.mark())
write(f'{BRAND}/mark-light.svg', mark.mark(silver='#334155'))

fav, fav_small = mark.favicon(), mark.favicon(sw=6.2, orbit=False, small=True)
write(f'{ROOT}/favicon.svg', fav)
# 16 px: no orbit, heavier strokes — the orbit is a blur at that size.
icons = [png(fav_small, 16, 16), png(fav, 32, 32), png(fav, 48, 48)]
# Pillow writes each size from the image of that size in append_images.
icons[2].save(f'{ROOT}/favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)], append_images=icons[:2])
png(fav, 180, 180).save(f'{ROOT}/apple-touch-icon.png', optimize=True)
png(fav, 192, 192).save(f'{ROOT}/icon-192.png', optimize=True)
big = png(fav, 512, 512)
big.save(f'{ROOT}/icon-512.png', optimize=True)
big.save(f'{ROOT}/favicon.png', optimize=True)
big.save(f'{ROOT}/favicon.webp', quality=92, method=6)

# The full logo as a picture, for places that cannot take SVG (mail, README).
full = png(dark, 1800)
full.save(f'{ROOT}/logo.png', optimize=True)
full.save(f'{ROOT}/logo.webp', quality=92, method=6)

# Link preview: the logo on the site's night blue.
og = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630">'
      '<defs><radialGradient id="bg" cx=".5" cy=".42" r=".75"><stop offset="0" stop-color="#0f1d3d"/>'
      '<stop offset="1" stop-color="#050912"/></radialGradient></defs>'
      '<rect width="1200" height="630" fill="url(#bg)"/>'
      f'<g transform="translate(120 20) scale(.8)">{dark[dark.index(">") + 1:-len("</svg>")]}</g>'
      f'<path fill="#e2e8f0" d="{logo.text_path("AX·NEWS", 600, 548, 44, weight=600, tracking=0.32)[0]}"/>'
      f'<path fill="#8ea0bb" d="{logo.text_path("Global tech news, translated and sorted every few minutes", 600, 590, 22, weight=400, tracking=0.02)[0]}"/>'
      '</svg>')
write(f'{ROOT}/og-image.svg', og)
ogp = png(og, 1200, 630).convert('RGB')
ogp.save(f'{ROOT}/og-image.png', optimize=True)
ogp.save(f'{ROOT}/og-image.webp', quality=90, method=6)

write(f'{ROOT}/site.webmanifest', json.dumps({
    'name': 'AX-NEWS', 'short_name': 'AX-NEWS', 'start_url': '/', 'display': 'standalone',
    'background_color': '#060a13', 'theme_color': '#060a13',
    'icons': [{'src': '/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
              {'src': '/icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
              {'src': '/favicon.svg', 'sizes': 'any', 'type': 'image/svg+xml'}]}, indent=2) + '\n')
print('brand files written to', ROOT)
