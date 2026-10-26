"""The ΛX emblem (top bar, TV) and the favicons: see build.py."""
import math

def cres(cx, cy, a, b, rot, t0, t1, wmax, n=90):
    cr, sr = math.cos(rot), math.sin(rot)
    def P(t, off):
        x, y = a * math.cos(t), b * math.sin(t)
        nx, ny = b * math.cos(t), a * math.sin(t); l = math.hypot(nx, ny)
        x += nx / l * off; y += ny / l * off
        return cx + x * cr - y * sr, cy + x * sr + y * cr
    o, i = [], []
    for k in range(n + 1):
        u = k / n; t = t0 + (t1 - t0) * u; w = wmax * math.sin(math.pi * u) ** 0.9
        o.append(P(t, w / 2)); i.append(P(t, -w / 2))
    return 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x, y in o + i[::-1]) + 'Z'

GRAD = '''<linearGradient id="b" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#1d6cf2"/><stop offset="1" stop-color="#5aa8ff"/></linearGradient>
<linearGradient id="s" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f1f5f9"/><stop offset="1" stop-color="#9fb0c8"/></linearGradient>'''

def letter_paths(x0, y0, h, wa, wx, gap):
    xa = x0; xx = x0 + wa + gap
    return (f'M{xa},{y0+h} L{xa+wa/2},{y0} L{xa+wa},{y0+h}',
            f'M{xx},{y0} L{xx+wx},{y0+h} M{xx+wx},{y0} L{xx},{y0+h}')

def letters(sw, x0=12, y0=20, h=24, wa=19, wx=17, gap=4.5, silver='url(#s)', knock=0):
    A, X = letter_paths(x0, y0, h, wa, wx, gap)
    if knock:   # the letters' outline, a little wider: cut out of the orbit
        return (f'<path d="{A}" stroke="#000" stroke-width="{sw + knock}" fill="none"/>'
                f'<path d="{X}" stroke="#000" stroke-width="{sw + knock}" fill="none"/>')
    return (f'<g fill="none" stroke-width="{sw}" stroke-linejoin="miter" stroke-linecap="butt">'
            f'<path d="{A}" stroke="url(#b)"/><path d="{X}" stroke="{silver}"/></g>')

def mark(sw=3.2, orbit=True, silver='url(#s)'):
    """Transparent 64x64 emblem: ΛX inside a tilted orbit."""
    orb = ''
    if orbit:
        rot = math.radians(-28)
        orb = (f'<path fill="url(#b)" d="{cres(32, 32, 29, 11.5, rot, math.radians(-175), math.radians(-25), 2.6)}"/>'
               f'<path fill="url(#b)" d="{cres(32, 32, 29, 11.5, rot, math.radians(15), math.radians(150), 2.4)}"/>')
    m = (f'<mask id="k" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">'
         f'<rect width="64" height="64" fill="#fff"/>{letters(sw, knock=3.2)}</mask>')
    # Cropped to the orbit: the letters fill the height of a line of text.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="4 13 56 38"><defs>{GRAD}{m}</defs>'
            f'<g mask="url(#k)">{orb}</g>{letters(sw, silver=silver)}</svg>')

def favicon(sw=4.4, orbit=True, small=False):
    bg = ('<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0d1a38"/>'
          '<stop offset="1" stop-color="#060b18"/></linearGradient>')
    orb = ''
    if orbit:
        rot = math.radians(-22)
        orb = (f'<path fill="url(#b)" d="{cres(32, 33, 28, 10, rot, math.radians(-200), math.radians(-10), 2.8)}"/>'
               f'<path fill="url(#b)" d="{cres(32, 33, 28, 10, rot, math.radians(10), math.radians(160), 2.4)}"/>')
    geo = dict(x0=8, y0=16, h=32, wa=24, wx=22, gap=4) if small else dict(x0=10.5, y0=19, h=26, wa=21, wx=19, gap=4.5)
    m = (f'<mask id="k" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">'
         f'<rect width="64" height="64" fill="#fff"/>{letters(sw, knock=3.6, **geo)}</mask>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs>{GRAD}{bg}{m}</defs>'
            f'<rect width="64" height="64" rx="14" fill="url(#g)"/>'
            f'<rect x="0.75" y="0.75" width="62.5" height="62.5" rx="13.25" fill="none" stroke="#ffffff" stroke-opacity=".10" stroke-width="1.5"/>'
            f'<g mask="url(#k)">{orb}</g>{letters(sw, **geo)}</svg>')
