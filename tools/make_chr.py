#!/usr/bin/env python3
"""
make_chr.py — Convert multiple BMP images to NES slideshow data.

Reads all *.bmp files from ../src-images/ (relative to project root),
scales each to 256×160 (32×20 tiles), converts to NES 2bpp CHR format
with k-means palette clustering and Floyd-Steinberg dithering, then
LZE-compresses the tile patterns.

Output:
    asm/img_data.s   — all image data (CHR, nametable, palette, attrs)
"""

import sys, os, struct, math, zlib

# ---------------------------------------------------------------------------
# NES master palette (64 entries, standard NTSC)
# ---------------------------------------------------------------------------
NES_PALETTE = [
    (84,84,84),(0,30,116),(8,16,144),(48,0,136),(68,0,100),(92,0,48),(84,4,0),(60,24,0),
    (32,42,0),(8,58,0),(0,64,0),(0,60,0),(0,50,60),(0,0,0),(0,0,0),(0,0,0),
    (152,150,152),(8,76,196),(48,50,236),(92,30,228),(136,20,176),(160,20,100),(152,34,32),(120,60,0),
    (84,90,0),(40,114,0),(8,124,0),(0,118,40),(0,102,120),(0,0,0),(0,0,0),(0,0,0),
    (236,238,236),(76,154,236),(120,124,236),(176,98,236),(228,84,236),(236,88,180),(236,106,100),(212,136,32),
    (160,170,0),(116,196,0),(76,208,32),(56,204,108),(56,180,204),(60,60,60),(0,0,0),(0,0,0),
    (236,238,236),(168,204,236),(188,188,236),(212,178,236),(236,174,236),(236,174,212),(236,180,176),(228,196,144),
    (204,210,120),(180,222,120),(168,226,144),(152,226,180),(160,214,228),(160,162,160),(0,0,0),(0,0,0),
]

# ---------------------------------------------------------------------------
# PNG writer (no external dependencies, uses zlib)
# ---------------------------------------------------------------------------

def write_png(path, pixels, width, height, scale=3):
    """Write an RGB image as PNG. pixels[y][x] = (r,g,b). Optionally scale up."""
    w = width  * scale
    h = height * scale
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    sig   = b'\x89PNG\r\n\x1a\n'
    ihdr  = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    rows  = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            r, g, b = pixels[y][x]
            row += bytes([r, g, b]) * scale
        row_bytes = bytes(row)
        rows.extend([b'\x00' + row_bytes] * scale)
    idat  = chunk(b'IDAT', zlib.compress(b''.join(rows), 9))
    iend  = chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(sig + ihdr + idat + iend)

# ---------------------------------------------------------------------------
# BMP reader (24bpp, Windows BITMAPINFOHEADER)
# ---------------------------------------------------------------------------

def read_bmp(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[0:2] != b'BM':
        raise ValueError(f'Not a BMP file: {path}')
    pixel_offset = struct.unpack_from('<I', data, 10)[0]
    hdr_size     = struct.unpack_from('<I', data, 14)[0]
    width        = struct.unpack_from('<i', data, 18)[0]
    height       = struct.unpack_from('<i', data, 22)[0]
    bpp          = struct.unpack_from('<H', data, 28)[0]
    compression  = struct.unpack_from('<I', data, 30)[0]
    if bpp != 24:
        raise ValueError(f'Expected 24bpp, got {bpp}bpp: {path}')
    if compression != 0:
        raise ValueError(f'Compressed BMP not supported: {path}')
    row_size   = (width * 3 + 3) & ~3
    bottom_up  = height > 0
    abs_height = abs(height)
    rows = []
    for row_idx in range(abs_height):
        src_row = (abs_height - 1 - row_idx) if bottom_up else row_idx
        off = pixel_offset + src_row * row_size
        row_pixels = []
        for col in range(width):
            b = data[off + col*3]
            g = data[off + col*3 + 1]
            r = data[off + col*3 + 2]
            row_pixels.append((r, g, b))
        rows.append(row_pixels)
    return rows, width, abs_height

# ---------------------------------------------------------------------------
# Image scaling (box filter)
# ---------------------------------------------------------------------------

def scale_image(rows, src_w, src_h, dst_w, dst_h):
    """Downscale using a box filter (area averaging)."""
    xs = src_w / dst_w
    ys = src_h / dst_h
    result = []
    for dy in range(dst_h):
        y0 = dy * ys;  y1 = min(y0 + ys, src_h)
        iy0 = int(y0); iy1 = int(math.ceil(y1))
        row_out = []
        for dx in range(dst_w):
            x0 = dx * xs;  x1 = min(x0 + xs, src_w)
            ix0 = int(x0); ix1 = int(math.ceil(x1))
            r = g = b = count = 0
            for iy in range(iy0, min(iy1, src_h)):
                for ix in range(ix0, min(ix1, src_w)):
                    px = rows[iy][ix]
                    r += px[0]; g += px[1]; b += px[2]
                    count += 1
            if count:
                row_out.append((r // count, g // count, b // count))
            else:
                row_out.append((0, 0, 0))
        result.append(row_out)
    return result

# ---------------------------------------------------------------------------
# Color math
# ---------------------------------------------------------------------------

def color_dist_sq(c1, c2):
    return (c1[0]-c2[0])**2 + (c1[1]-c2[1])**2 + (c1[2]-c2[2])**2

def nearest_nes(rgb):
    return min(range(64), key=lambda i: color_dist_sq(rgb, NES_PALETTE[i]))

def brightness(rgb):
    return 0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]

def rgb_to_lab(rgb):
    """Convert sRGB (0-255 each) to CIE L*a*b*."""
    r, g, b = rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0
    def lin(c):
        return c/12.92 if c <= 0.04045 else ((c + 0.055)/1.055)**2.4
    r, g, b = lin(r), lin(g), lin(b)
    X = r*0.4124564 + g*0.3575761 + b*0.1804375
    Y = r*0.2126729 + g*0.7151522 + b*0.0721750
    Z = r*0.0193339 + g*0.1191920 + b*0.9503041
    X /= 0.95047; Z /= 1.08883
    def f(t):
        return t**(1/3) if t > 0.008856 else 7.787*t + 16/116
    L = 116*f(Y) - 16
    a = 500*(f(X) - f(Y))
    b_ = 200*(f(Y) - f(Z))
    return (L, a, b_)

# ---------------------------------------------------------------------------
# Palette selection
# ---------------------------------------------------------------------------

def pick_best_nes_colors(pixels, n=4, fixed0=None):
    """
    Select n NES palette entries that best cover the given pixels.
    Colorful pixels (high chroma) are weighted higher so the palette
    prioritises hues over neutral grays.
    """
    # Chroma weight: chromatic pixels count more than achromatic ones
    def chroma_weight(px):
        _, a, b_ = rgb_to_lab(px)
        return math.sqrt(a*a + b_*b_) + 1.0

    if fixed0 is not None:
        chosen = [fixed0]
    else:
        counts = [0.0]*64
        for px in pixels:
            counts[nearest_nes(px)] += chroma_weight(px)
        chosen = [max(range(64), key=lambda i: counts[i])]

    for _ in range(n - len(chosen)):
        best_c, best_e = -1, float('inf')
        for c in range(64):
            if c in chosen: continue
            trial = chosen + [c]
            err = sum(
                chroma_weight(px) * min(color_dist_sq(px, NES_PALETTE[i]) for i in trial)
                for px in pixels
            )
            if err < best_e:
                best_e = err; best_c = c
        if best_c >= 0:
            chosen.append(best_c)
    while len(chosen) < n:
        chosen.append(chosen[0])
    return chosen[:n]

# NES palette indices that are distinctly green (vivid enough to read as eye color)
NES_GREEN = {0x19, 0x1A, 0x1B, 0x29, 0x2A, 0x2B}

def rescue_green_globally(palettes, assignments, blk_pixels):
    """
    If the image has significant green pixels but NONE of the 4 palettes
    include any green NES color, inject green into the most appropriate palette.
    Images where green is already represented (5,6,7,8) are left untouched.
    """
    # If any palette already contains a green entry → already fine, do nothing
    if any(c in NES_GREEN for pal in palettes for c in pal):
        return palettes

    # Collect green pixels per cluster
    cluster_green = [[] for _ in range(4)]
    for blk_idx, cl in enumerate(assignments):
        for px in blk_pixels[blk_idx]:
            if nearest_nes(px) in NES_GREEN:
                cluster_green[cl].append(px)

    total_green = sum(len(g) for g in cluster_green)
    if total_green < 10:
        return palettes  # not enough green in the whole image

    # Rescue the cluster that has the most green pixels
    best_cl = max(range(4), key=lambda c: len(cluster_green[c]))
    green_px = cluster_green[best_cl]
    cpix = [px for blk_idx, cl in enumerate(assignments)
            if cl == best_cl for px in blk_pixels[blk_idx]]

    best_green = min(NES_GREEN,
                     key=lambda g: sum(color_dist_sq(px, NES_PALETTE[g]) for px in green_px))
    pal = list(palettes[best_cl])
    best_slot, min_loss = 1, float('inf')
    for slot in range(1, 4):
        if pal[slot] in NES_SKIN:
            continue   # protect skin-tone entries from being overwritten
        remaining = [pal[s] for s in range(4) if s != slot]
        loss = sum(
            min(color_dist_sq(px, NES_PALETTE[c]) for c in remaining) -
            min(color_dist_sq(px, NES_PALETTE[c]) for c in pal)
            for px in cpix
        )
        if loss < min_loss:
            min_loss = loss; best_slot = slot

    if pal[best_slot] in NES_SKIN:
        return palettes   # all non-bg slots are skin; skip green rescue

    print(f'    [green rescue] total {total_green} green px → palette {best_cl} '
          f'slot {best_slot}: ${pal[best_slot]:02X} → ${best_green:02X}', file=sys.stderr)
    pal[best_slot] = best_green
    new_palettes = list(palettes)
    new_palettes[best_cl] = pal
    return new_palettes

# NES palette indices that are distinctly skin-toned (peach/tan/salmon)
NES_SKIN = {0x26, 0x27, 0x35, 0x36, 0x37}

def rescue_skin_globally(palettes, assignments, blk_pixels):
    """
    If the image has significant skin-tone pixels but NONE of the 4 palettes
    include any skin NES color, inject the best skin color into the palette
    that covers the most skin pixels.
    """
    if any(c in NES_SKIN for pal in palettes for c in pal):
        return palettes  # already has skin colors

    cluster_skin = [[] for _ in range(4)]
    for blk_idx, cl in enumerate(assignments):
        for px in blk_pixels[blk_idx]:
            if nearest_nes(px) in NES_SKIN:
                cluster_skin[cl].append(px)

    total_skin = sum(len(s) for s in cluster_skin)
    if total_skin < 15:
        return palettes

    best_cl = max(range(4), key=lambda c: len(cluster_skin[c]))
    skin_px = cluster_skin[best_cl]
    cpix = [px for blk_idx, cl in enumerate(assignments)
            if cl == best_cl for px in blk_pixels[blk_idx]]

    best_skin = min(NES_SKIN,
                    key=lambda s: sum(color_dist_sq(px, NES_PALETTE[s]) for px in skin_px))

    pal = list(palettes[best_cl])
    best_slot, min_loss = 1, float('inf')
    for slot in range(1, 4):
        remaining = [pal[s] for s in range(4) if s != slot]
        loss = sum(
            min(color_dist_sq(px, NES_PALETTE[c]) for c in remaining) -
            min(color_dist_sq(px, NES_PALETTE[c]) for c in pal)
            for px in cpix
        )
        if loss < min_loss:
            min_loss = loss; best_slot = slot

    print(f'    [skin rescue] total {total_skin} skin px → palette {best_cl} '
          f'slot {best_slot}: ${pal[best_slot]:02X} → ${best_skin:02X}', file=sys.stderr)
    pal[best_slot] = best_skin
    new_palettes = list(palettes)
    new_palettes[best_cl] = pal
    return new_palettes

# ---------------------------------------------------------------------------
# K-means clustering
# ---------------------------------------------------------------------------

def block_sig(pixels):
    """
    Chroma-weighted CIE Lab mean of the pixels in a block.
    Skin-tone pixels get an extra 3× weight boost so that face/hand blocks
    form distinct k-means clusters rather than being absorbed into white areas.
    """
    labs = [rgb_to_lab(px) for px in pixels]
    weights = []
    for px, l in zip(pixels, labs):
        w = math.sqrt(l[1]**2 + l[2]**2) + 1.0
        if nearest_nes(px) in NES_SKIN:
            w *= 3.0   # boost: skin blocks stand out from white blocks
        weights.append(w)
    tw = sum(weights)
    return [sum(w*l[i] for w, l in zip(weights, labs))/tw for i in range(3)]

def vec_dist_sq(a, b):
    return sum((x-y)**2 for x, y in zip(a, b))

def kmeans(sigs, k=4, max_iter=50):
    import random; random.seed(42)
    n   = len(sigs)
    dim = len(sigs[0])
    centroids = [list(sigs[random.randrange(n)])]
    for _ in range(k-1):
        dists = [min(vec_dist_sq(s, c) for c in centroids) for s in sigs]
        total = sum(dists)
        if total == 0:
            centroids.append(list(sigs[random.randrange(n)])); continue
        thresh = random.random() * total
        cum = 0.0
        idx = 0
        for i, d in enumerate(dists):
            cum += d
            if cum >= thresh: idx = i; break
        centroids.append(list(sigs[idx]))
    assignments = [0]*n
    for _ in range(max_iter):
        new_a = [min(range(k), key=lambda c: vec_dist_sq(sigs[i], centroids[c])) for i in range(n)]
        if new_a == assignments: break
        assignments = new_a
        sums   = [[0.0]*dim for _ in range(k)]
        counts = [0]*k
        for i, cl in enumerate(assignments):
            sums[cl] = [x+y for x, y in zip(sums[cl], sigs[i])]
            counts[cl] += 1
        for c in range(k):
            if counts[c]:
                centroids[c] = [x/counts[c] for x in sums[c]]
    return assignments

# ---------------------------------------------------------------------------
# Atkinson dithering
# ---------------------------------------------------------------------------

def dither_tile(tile_pix, palette_indices):
    buf = [[list(map(float, px)) for px in row] for row in tile_pix]
    result = [[0]*8 for _ in range(8)]
    for y in range(8):
        for x in range(8):
            old   = buf[y][x]
            rgb_i = tuple(int(max(0, min(255, old[ch]))) for ch in range(3))
            si    = min(range(len(palette_indices)),
                        key=lambda i: color_dist_sq(rgb_i, NES_PALETTE[palette_indices[i]]))
            result[y][x] = si
            near  = NES_PALETTE[palette_indices[si]]
            err   = [old[ch] - near[ch] for ch in range(3)]
            def spread(dy, dx):
                ny, nx = y+dy, x+dx
                if 0 <= ny < 8 and 0 <= nx < 8:
                    for ch in range(3):
                        buf[ny][nx][ch] = max(0., min(255., buf[ny][nx][ch] + err[ch]/8))
            spread(0,  1)
            spread(0,  2)
            spread(1, -1)
            spread(1,  0)
            spread(1,  1)
            spread(2,  0)
    return result

# ---------------------------------------------------------------------------
# CHR tile encoder (NES 2bpp)
# ---------------------------------------------------------------------------

def encode_tile(grid):
    p0 = []; p1 = []
    for row in grid:
        b0 = b1 = 0
        for bit in range(8):
            idx = row[bit] & 3
            b0 |= ((idx >> 0) & 1) << (7-bit)
            b1 |= ((idx >> 1) & 1) << (7-bit)
        p0.append(b0); p1.append(b1)
    return bytes(p0 + p1)

# ---------------------------------------------------------------------------
# Tile deduplication
# ---------------------------------------------------------------------------

BLANK_TILE = bytes(16)  # all-zero = CHR slot $00

def deduplicate_tiles(all_tile_chr):
    """
    Given a list of 16-byte tile patterns, assign each to a CHR slot (0-255).
    Slot $00 is reserved for the blank tile.
    Returns (chr_slots, nametable):
      chr_slots : list of up to 256 16-byte patterns (index = CHR slot number)
      nametable : list of CHR slot indices (same length as all_tile_chr)
    """
    chr_slots   = [BLANK_TILE]           # slot 0 = blank
    slot_map    = {BLANK_TILE: 0}        # tile bytes → slot index
    nametable   = []

    # First pass: assign slots
    overflow = []
    for i, tb in enumerate(all_tile_chr):
        if tb in slot_map:
            nametable.append(slot_map[tb])
        elif len(chr_slots) < 256:
            slot = len(chr_slots)
            chr_slots.append(tb)
            slot_map[tb] = slot
            nametable.append(slot)
        else:
            overflow.append(i)
            nametable.append(-1)         # placeholder

    # Second pass: map overflow tiles to nearest existing slot
    for i in overflow:
        tb  = all_tile_chr[i]
        best_slot = 0
        best_err  = float('inf')
        for s, sb in enumerate(chr_slots):
            err = sum((a-b)**2 for a, b in zip(tb, sb))
            if err < best_err:
                best_err = err; best_slot = s
        nametable[i] = best_slot

    return chr_slots, nametable, len(overflow)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

IMG_W      = 256   # output image width  (pixels)
IMG_H      = 160   # output image height (pixels)
TILES_W    = 32    # IMG_W / 8
TILES_H    = 20    # IMG_H / 8
ABLK_W     = 16    # 2×2 tile blocks across  (TILES_W / 2)
ABLK_H     = 10    # 2×2 tile blocks down    (TILES_H / 2)

# Autoscale steps: (content_w, content_h) in pixels, multiples of 16 for attr alignment.
# Tried in order until tile overflow is resolved.
SCALE_STEPS = [
    (256, 160),
    (224, 144),
    (192, 128),
    (160, 112),
    (128,  96),
]

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert BMP images to NES slideshow data')
    parser.add_argument('--no-green-rescue', action='store_true',
                        help='Disable green rescue (do not force green into palettes)')
    parser.add_argument('--src-dir', default=None,
                        help='Source image directory (default: ../src-images relative to project root)')
    parser.add_argument('--max-images', type=int, default=None,
                        help='Limit number of images to process (first N after sorting)')
    args = parser.parse_args()
    green_rescue = not args.no_green_rescue

    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    asm_dir      = os.path.join(project_root, 'asm')
    build_dir    = os.path.join(project_root, 'build')
    if args.src_dir:
        src_dir = os.path.normpath(args.src_dir)
    else:
        src_dir = os.path.normpath(os.path.join(project_root, '..', 'src-images'))

    print(f'[make_chr] Green rescue: {"ON" if green_rescue else "OFF"}', file=sys.stderr)

    if not os.path.isdir(src_dir):
        print(f'[make_chr] ERROR: src-images not found at {src_dir}', file=sys.stderr)
        sys.exit(1)

    def bmp_sort_key(f):
        name = os.path.splitext(f)[0]
        if name.isdigit():
            return int(name)
        parts = name.rsplit('_', 1)        # e.g. "2_15" → ["2", "15"]
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1])
        return name
    bmp_files = sorted(
        [f for f in os.listdir(src_dir) if f.lower().endswith('.bmp')],
        key=bmp_sort_key
    )
    if not bmp_files:
        print('[make_chr] ERROR: no BMP files found', file=sys.stderr)
        sys.exit(1)
    if args.max_images is not None:
        bmp_files = bmp_files[:args.max_images]

    print(f'[make_chr] Found {len(bmp_files)} BMP files in {src_dir}', file=sys.stderr)

    # ---- Locate lze.py ----
    lze_path = os.path.normpath(os.path.join(project_root, '..', '..', '88image', 'lze.py'))
    if not os.path.exists(lze_path):
        print(f'[make_chr] ERROR: lze.py not found at {lze_path}', file=sys.stderr)
        sys.exit(1)
    import importlib.util
    spec = importlib.util.spec_from_file_location('lze', lze_path)
    lze_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lze_mod)

    # ---- Per-image data ----
    all_chr_compressed = []   # list of bytes objects (compressed CHR, no header)
    all_nametables     = []   # list of 640-byte arrays
    all_palettes       = []   # list of 16-byte arrays (4 palettes × 4 colors)
    all_attrs          = []   # list of 40-byte arrays (5 attr rows × 8 attr cols)

    for bmp_name in bmp_files:
        bmp_path = os.path.join(src_dir, bmp_name)
        print(f'\n[make_chr] Processing {bmp_name}...', file=sys.stderr)

        rows, src_w, src_h = read_bmp(bmp_path)
        print(f'  Source: {src_w}x{src_h}', file=sys.stderr)

        # --- Autoscale retry loop ---
        for attempt, (content_w, content_h) in enumerate(SCALE_STEPS):
            # Determine fill colour from source top-left pixel
            topleft_nes = nearest_nes(rows[0][0])
            fill_rgb = NES_PALETTE[topleft_nes]

            # Build 256×160 frame: fill with bg colour, place scaled content bottom-aligned
            x_off = (IMG_W - content_w) // 2
            y_off = IMG_H - content_h    # bottom-aligned
            frame = [[fill_rgb] * IMG_W for _ in range(IMG_H)]
            content = scale_image(rows, src_w, src_h, content_w, content_h)
            for fy in range(content_h):
                for fx in range(content_w):
                    frame[y_off + fy][x_off + fx] = content[fy][fx]

            # --- Background colour ---
            # Use top-left pixel of the source image if it's a clear background colour
            # (nearest NES entry covers ≥5% of the image), otherwise fall back to
            # the darkest NES colour with ≥1% frequency.
            all_px = [px for row in frame for px in row]
            freq   = [0]*64
            for px in all_px:
                freq[nearest_nes(px)] += 1
            if freq[topleft_nes] >= len(all_px) // 20:   # ≥5%: use top-left colour
                bg = topleft_nes
                print(f'  BG: top-left pixel → NES ${bg:02X} '
                      f'({freq[bg]*100//len(all_px)}% coverage)', file=sys.stderr)
            else:                                          # fallback: darkest frequent colour
                bg = 0x0F
                darkest = float('inf')
                for i in range(64):
                    if freq[i] >= max(1, len(all_px)//100) and brightness(NES_PALETTE[i]) < darkest:
                        darkest = brightness(NES_PALETTE[i]); bg = i

            # --- Extract 2×2 tile block pixels (ABLK_W × ABLK_H = 160 blocks) ---
            blk_pixels = []
            for by in range(ABLK_H):
                for bx in range(ABLK_W):
                    pix = []
                    for py in range(16):
                        for px in range(16):
                            pix.append(frame[by*16+py][bx*16+px])
                    blk_pixels.append(pix)

            # --- K-means: 160 blocks → 4 clusters ---
            sigs        = [block_sig(bp) for bp in blk_pixels]
            assignments = kmeans(sigs, k=4)

            # --- Build 4 palettes ---
            palettes = []
            for cid in range(4):
                cpix = [px for i, a in enumerate(assignments) if a == cid for px in blk_pixels[i]]
                if not cpix:
                    palettes.append([bg]*4)
                else:
                    palettes.append(pick_best_nes_colors(cpix, n=4, fixed0=bg))

            # --- Green rescue: only if NO palette has green (handles 1,2,9,10) ---
            if green_rescue:
                palettes = rescue_green_globally(palettes, assignments, blk_pixels)

            # --- Skin rescue: only if NO palette has skin-tone colors ---
            palettes = rescue_skin_globally(palettes, assignments, blk_pixels)

            pal_bytes = bytes(c for pal in palettes for c in pal)

            # --- Assign palette to each 8×8 tile ---
            # tile (ty, tx) → 2×2 block (ty//2, tx//2) → assignments[by*ABLK_W + bx]
            tile_pal = [
                assignments[(ty//2)*ABLK_W + (tx//2)]
                for ty in range(TILES_H) for tx in range(TILES_W)
            ]

            # --- Dither & encode each tile ---
            tile_chr_data = []
            for ty in range(TILES_H):
                for tx in range(TILES_W):
                    tile_pix = [
                        [frame[ty*8+py][tx*8+px] for px in range(8)]
                        for py in range(8)
                    ]
                    pal      = palettes[tile_pal[ty*TILES_W+tx]]
                    dithered = dither_tile(tile_pix, pal)
                    tile_chr_data.append(encode_tile(dithered))

            # --- Deduplicate tiles ---
            chr_slots, nametable, overflow_count = deduplicate_tiles(tile_chr_data)
            unique_count = len(chr_slots)

            if overflow_count == 0 or attempt == len(SCALE_STEPS) - 1:
                scale_note = f' (autoscaled to {content_w}×{content_h})' if attempt > 0 else ''
                overflow_note = f'  [!] {overflow_count} tiles mapped to nearest slot' if overflow_count else ''
                print(f'  Unique tile patterns: {unique_count} / 256  '
                      f'(blank: {nametable.count(0)}){scale_note}', file=sys.stderr)
                if overflow_note:
                    print(overflow_note, file=sys.stderr)
                break
            else:
                nw, nh = SCALE_STEPS[attempt + 1]
                print(f'  Overflow ({overflow_count} tiles at {content_w}×{content_h}), '
                      f'retrying at {nw}×{nh}...', file=sys.stderr)

        # --- Build 4096-byte raw CHR (256 slots × 16 bytes, unused slots = zero) ---
        chr_raw = bytearray(256 * 16)
        for slot, tb in enumerate(chr_slots):
            chr_raw[slot*16 : slot*16+16] = tb

        # --- LZE-compress CHR ---
        compressed = lze_mod.encode(bytes(chr_raw))
        compressed_data = compressed[4:]   # skip 4-byte size header
        print(f'  CHR: 4096 → {len(compressed_data)} bytes compressed '
              f'({100 - len(compressed_data)*100//4096}% reduction)', file=sys.stderr)

        # --- Build attribute bytes (5 attr rows × 8 attr cols = 40 bytes) ---
        # Screen attr row r+1 covers image tile rows r*4 to r*4+3 (r=0..4)
        attr_bytes = []
        for ar in range(5):          # image attr row 0-4 → screen attr rows 1-5
            for ac in range(8):      # attr cols 0-7
                def qpal(dy, dx):
                    by = ar*2 + dy
                    bx = ac*2 + dx
                    return assignments[by*ABLK_W + bx]
                tl = qpal(0,0); tr = qpal(0,1)
                bl = qpal(1,0); br = qpal(1,1)
                attr_bytes.append(tl | (tr<<2) | (bl<<4) | (br<<6))

        # --- Build preview from nametable + CHR slots (matches actual NES output) ---
        # Overflow tiles are shown as their nearest-slot approximation, same as NES.
        preview = [[None]*IMG_W for _ in range(IMG_H)]
        for tile_idx in range(TILES_W * TILES_H):
            ty = tile_idx // TILES_W
            tx = tile_idx % TILES_W
            tb   = chr_slots[nametable[tile_idx]]
            pal  = palettes[tile_pal[tile_idx]]
            for py in range(8):
                p0 = tb[py]; p1 = tb[py + 8]
                for px in range(8):
                    bit = 7 - px
                    ci = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
                    preview[ty*8+py][tx*8+px] = NES_PALETTE[pal[ci]]

        # --- Write preview PNG ---
        png_name = os.path.splitext(bmp_name)[0] + '_preview.png'
        png_path = os.path.join(src_dir, png_name)
        write_png(png_path, preview, IMG_W, IMG_H, scale=3)
        print(f'  Preview: {png_path}', file=sys.stderr)

        # --- LZE-compress nametable ---
        nt_raw = bytes(nametable)
        nt_compressed = lze_mod.encode(nt_raw)
        nt_compressed_data = nt_compressed[4:]   # skip 4-byte size header
        print(f'  NT:  640 → {len(nt_compressed_data)} bytes compressed '
              f'({100 - len(nt_compressed_data)*100//640}% reduction)', file=sys.stderr)

        all_chr_compressed.append(compressed_data)
        all_nametables.append(nt_compressed_data)
        all_palettes.append(pal_bytes)
        all_attrs.append(bytes(attr_bytes))

    # ---- Write build/img_config.h (NUM_IMAGES for C code) ----
    n = len(bmp_files)
    os.makedirs(build_dir, exist_ok=True)
    cfg_path = os.path.join(build_dir, 'img_config.h')
    with open(cfg_path, 'w') as f:
        f.write(f'/* Auto-generated by make_chr.py — do not edit */\n')
        f.write(f'#define NUM_IMAGES {n}\n')

    # ---- Write asm/img_data.s ----
    out_path = os.path.join(asm_dir, 'img_data.s')
    print(f'\n[make_chr] Writing {out_path}', file=sys.stderr)

    with open(out_path, 'w') as f:
        f.write('; img_data.s — NES slideshow image data\n')
        f.write('; Generated by tools/make_chr.py  (do not edit by hand)\n')
        f.write(f'; {n} images, each {IMG_W}x{IMG_H} px ({TILES_W}x{TILES_H} tiles)\n')
        f.write('\n')
        f.write('.segment "RODATA"\n')
        f.write('\n')

        # Pointer tables (lo/hi byte arrays)
        f.write('; --- CHR data pointers ---\n')
        f.write('.export _img_chr_lo, _img_chr_hi\n')
        f.write('_img_chr_lo: .byte ' +
                ', '.join(f'<img_chr_{i}' for i in range(n)) + '\n')
        f.write('_img_chr_hi: .byte ' +
                ', '.join(f'>img_chr_{i}' for i in range(n)) + '\n')
        f.write('\n')

        f.write('; --- Nametable data pointers ---\n')
        f.write('.export _img_nt_lo, _img_nt_hi\n')
        f.write('_img_nt_lo:  .byte ' +
                ', '.join(f'<img_nt_{i}' for i in range(n)) + '\n')
        f.write('_img_nt_hi:  .byte ' +
                ', '.join(f'>img_nt_{i}' for i in range(n)) + '\n')
        f.write('\n')

        # Palette data (n × 16 bytes)
        f.write(f'; --- Palette data ({n} images × 16 bytes = {n*16} bytes) ---\n')
        f.write('.export _img_palettes\n')
        f.write('_img_palettes:\n')
        for i, pal in enumerate(all_palettes):
            hex_str = ', '.join(f'${b:02X}' for b in pal)
            f.write(f'    .byte {hex_str}  ; image {i}\n')
        f.write('\n')

        # Attribute data (n × 40 bytes)
        f.write(f'; --- Attribute data ({n} images × 40 bytes = {n*40} bytes) ---\n')
        f.write('.export _img_attrs\n')
        f.write('_img_attrs:\n')
        for i, ab in enumerate(all_attrs):
            for row in range(5):
                hex_str = ', '.join(f'${ab[row*8+j]:02X}' for j in range(8))
                f.write(f'    .byte {hex_str}  ; image {i} attr row {row}\n')
        f.write('\n')

        # LZE-compressed CHR data
        f.write('; --- LZE-compressed CHR tile data ---\n')
        for i, cd in enumerate(all_chr_compressed):
            f.write(f'img_chr_{i}:  ; {len(cd)} bytes\n')
            for off in range(0, len(cd), 16):
                chunk = cd[off:off+16]
                f.write('    .byte ' + ', '.join(f'${b:02X}' for b in chunk) + '\n')
            f.write('\n')

        # LZE-compressed nametable data
        f.write('; --- LZE-compressed nametable data ---\n')
        for i, nt in enumerate(all_nametables):
            f.write(f'img_nt_{i}:  ; {len(nt)} bytes compressed\n')
            for off in range(0, len(nt), 16):
                chunk = nt[off:off+16]
                f.write('    .byte ' + ', '.join(f'${b:02X}' for b in chunk) + '\n')
            f.write('\n')

    # ---- Summary ----
    total_chr   = sum(len(c) for c in all_chr_compressed)
    total_nt    = sum(len(t) for t in all_nametables)
    total_pal   = n * 16
    total_attr  = n * 40
    total_data  = total_chr + total_nt + total_pal + total_attr
    print(f'\n=== make_chr.py summary ===', file=sys.stderr)
    print(f'  Images      : {n}', file=sys.stderr)
    print(f'  Output size : CHR {total_chr}B  NT {total_nt}B (compressed)  '
          f'PAL {total_pal}B  ATTR {total_attr}B  total {total_data}B',
          file=sys.stderr)
    print(f'  Output      : {out_path}', file=sys.stderr)
    print(f'Generated {n} images')

if __name__ == '__main__':
    main()
