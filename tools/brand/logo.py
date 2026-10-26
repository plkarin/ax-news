"""The AXIOM logo: a thin-stroke wordmark inside two orbits, the tagline in
Inter. Pure geometry, no raster: see build.py."""
import math, sys, os
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'frontend', 'assets', 'fonts', 'inter-latin.woff2')

def text_path(s, x, y, size, weight=300, tracking=0.0, anchor='middle'):
    f = TTFont(FONT)
    f = instantiateVariableFont(f, {'wght': weight})
    gs = f.getGlyphSet(); cmap = f.getBestCmap(); upm = f['head'].unitsPerEm
    hmtx = f['hmtx']; sc = size / upm
    names = [cmap[ord(c)] for c in s]
    adv = [hmtx[n][0] * sc + tracking * size for n in names]
    total = sum(adv) - tracking * size
    cx = x - (total / 2 if anchor == 'middle' else 0)
    d = []
    for n, a in zip(names, adv):
        pen = SVGPathPen(gs)
        tp = TransformPen(pen, (sc, 0, 0, -sc, cx, y))
        gs[n].draw(tp)
        d.append(pen.getCommands()); cx += a
    return ' '.join(d), total

def orbit(cx, cy, a, b, rot, t0, t1, wmax, boxes, minlen=0.18):
    """Crescents along the arc t0..t1, cut wherever the arc crosses a box
    (the text): each visible piece tapers to a point at both ends."""
    cr, sr = math.cos(rot), math.sin(rot)
    def inside(t):
        x, y = a * math.cos(t), b * math.sin(t)
        X, Y = cx + x * cr - y * sr, cy + x * sr + y * cr
        return any(x0 <= X <= x1 and y0 <= Y <= y1 for x0, y0, x1, y1 in boxes)
    N = 1200; runs = []; cur = None
    for i in range(N + 1):
        t = t0 + (t1 - t0) * i / N
        if not inside(t):
            cur = [t, t] if cur is None else [cur[0], t]
        elif cur is not None:
            runs.append(cur); cur = None
    if cur: runs.append(cur)
    return [crescent(cx, cy, a, b, rot, r0, r1, wmax) for r0, r1 in runs if abs(r1 - r0) >= minlen]

def crescent(cx, cy, a, b, rot, t0, t1, wmax, n=160, power=0.9, outward=1):
    """Filled crescent along ellipse arc t0..t1 (radians), thickest mid-arc."""
    cr, sr = math.cos(rot), math.sin(rot)
    def P(t, off):
        x, y = a * math.cos(t), b * math.sin(t)
        nx, ny = b * math.cos(t), a * math.sin(t)
        l = math.hypot(nx, ny); nx, ny = nx / l, ny / l
        x += nx * off * outward; y += ny * off * outward
        return cx + x * cr - y * sr, cy + x * sr + y * cr
    outer, inner = [], []
    for i in range(n + 1):
        u = i / n; t = t0 + (t1 - t0) * u
        w = wmax * (math.sin(math.pi * u) ** power)
        outer.append(P(t, w / 2)); inner.append(P(t, -w / 2))
    pts = outer + inner[::-1]
    return 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in pts) + 'Z'

# ── wordmark geometry (y down; cap top = 0, baseline = H) ───────────────
H, S = 150, 11          # cap height, stroke
def letters(x0, y0):
    out = []; x = x0
    def seg(*pts): return 'M' + ' L'.join(f'{x0_+0:.1f},{y_:.1f}' for x0_, y_ in pts)
    # A: Λ with a short floating bar on the left leg side (futuristic)
    w = 142
    A = [seg((x, y0 + H), (x + w / 2, y0), (x + w, y0 + H))]
    out.append(('A', A)); x += w + 26
    w = 132
    X1 = seg((x, y0), (x + w, y0 + H)); X2 = seg((x + w, y0), (x, y0 + H))
    out.append(('X1', [X1])); out.append(('X2', [X2])); x += w + 40
    I = seg((x, y0), (x, y0 + H)); out.append(('I', [I])); x += 40
    w = 150; r = 34
    O = (f'M{x + r:.1f},{y0:.1f} H{x + w - r:.1f} A{r},{r} 0 0 1 {x + w:.1f},{y0 + r:.1f} V{y0 + H - r:.1f} '
         f'A{r},{r} 0 0 1 {x + w - r:.1f},{y0 + H:.1f} H{x + r:.1f} A{r},{r} 0 0 1 {x:.1f},{y0 + H - r:.1f} '
         f'V{y0 + r:.1f} A{r},{r} 0 0 1 {x + r:.1f},{y0:.1f} Z')
    out.append(('O', [O])); x += w + 38
    w = 160
    M = [seg((x, y0 + H), (x, y0), (x + w / 2, y0 + H * 0.64), (x + w, y0), (x + w, y0 + H))]
    out.append(('M', M)); x += w
    return out, x - x0

def logo_svg(variant='dark', tagline=True, w_total=1200, h_total=560):
    words, ww = letters(0, 0)
    ox = (w_total - ww) / 2; oy = h_total / 2 - H / 2 - (14 if tagline else 0)
    cx, cy = w_total / 2, h_total / 2 - 4
    blue1, blue2 = '#1d6cf2', '#5aa8ff'
    if variant == 'dark':
        sil1, sil2, word2a, word2b, tagc = '#f1f5f9', '#8c9bb3', '#e2e8f0', '#9fb0c8', '#8ea0bb'
    else:
        sil1, sil2, word2a, word2b, tagc = '#94a3b8', '#475569', '#1e293b', '#475569', '#64748b'
    paths = []
    # orbits
    pad = 26
    boxes = [(ox - pad, oy - pad, ox + ww + pad, oy + H + pad)]
    if tagline:
        boxes.append((cx - 430, oy + H + 30, cx + 430, oy + H + 70))
    a1, b1 = 548, 146
    for d in orbit(cx, cy, a1, b1, 0, math.radians(128), math.radians(236), 12, boxes):
        paths.append(f'<path fill="url(#sil)" d="{d}"/>')
    for d in orbit(cx, cy, a1, b1, 0, math.radians(-50), math.radians(56), 12, boxes):
        paths.append(f'<path fill="url(#sil)" d="{d}"/>')
    rot = math.radians(-24); a2, b2 = 470, 176
    for t0, t1 in ((-150, 10), (32, 160)):
      for d in orbit(cx, cy + 8, a2, b2, rot, math.radians(t0), math.radians(t1), 11, boxes, minlen=0.6):
        paths.append(f'<path fill="url(#blu)" d="{d}"/>')
    # letters
    g = [f'<g transform="translate({ox:.1f},{oy:.1f})" fill="none" stroke-width="{S}" stroke-linejoin="miter" stroke-miterlimit="10">']
    for name, ds in words:
        col = {'A': 'url(#wb)', 'X1': 'url(#wb)', 'X2': 'url(#ws)'}.get(name, 'url(#w2)')
        for d in ds:
            g.append(f'<path d="{d}" stroke="{col}"/>')
    g.append('</g>')
    tag = ''
    if tagline:
        d, tw = text_path('TECHNOLOGY · INTELLIGENCE · IMPACT', cx, oy + H + 58, 25, weight=350, tracking=0.42)
        tag = f'<path fill="{tagc}" d="{d}"/>'
    defs = f'''<defs>
<linearGradient id="blu" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="{blue1}"/><stop offset="1" stop-color="{blue2}"/></linearGradient>
<linearGradient id="sil" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{sil1}"/><stop offset="1" stop-color="{sil2}"/></linearGradient>
<linearGradient id="wb" gradientUnits="userSpaceOnUse" x1="{ox:.0f}" y1="{oy + H:.0f}" x2="{ox + 300:.0f}" y2="{oy:.0f}"><stop offset="0" stop-color="{blue1}"/><stop offset="1" stop-color="{blue2}"/></linearGradient>
<linearGradient id="ws" gradientUnits="userSpaceOnUse" x1="{ox + 168:.0f}" y1="{oy:.0f}" x2="{ox + 300:.0f}" y2="{oy + H:.0f}"><stop offset="0" stop-color="{word2a}"/><stop offset="1" stop-color="{word2b}"/></linearGradient>
<linearGradient id="w2" gradientUnits="userSpaceOnUse" x1="0" y1="{oy:.0f}" x2="0" y2="{oy + H:.0f}"><stop offset="0" stop-color="{word2a}"/><stop offset="1" stop-color="{word2b}"/></linearGradient>
</defs>'''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w_total} {h_total}" role="img" aria-label="AXIOM">'
            f'<title>AXIOM</title>{defs}{"".join(paths)}{"".join(g)}{tag}</svg>')
