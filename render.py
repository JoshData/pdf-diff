#!/usr/bin/python3

import sys, json, subprocess, io
from PIL import Image, ImageDraw, ImageOps

# Rasterizes a page of a PDF.
def pdftopng(pdffile, pagenumber, width=900):
    pngbytes = subprocess.check_output(["/usr/bin/pdftoppm", "-f", str(pagenumber), "-l", str(pagenumber), "-scale-to", str(width), "-png", pdffile])
    im = Image.open(io.BytesIO(pngbytes))
    return im.convert("RGBA")

# Load all of the pages named in changes.

changes = json.load(sys.stdin)

pages = [{}, {}]
for change in changes:
    if change == "*": continue # not handled yet
    if change["page"]["number"] not in pages[change["pdf"]["index"]]:
        pages[change["pdf"]["index"]][change["page"]["number"]] = pdftopng(change["pdf"]["file"], change["page"]["number"])

# Draw red boxes around changes.

for change in changes:
    if change == "*": continue # not handled yet

    im = pages[change["pdf"]["index"]][change["page"]["number"]]

    coords = (
        change["x"] * im.size[0]/change["page"]["width"],
        change["y"] * im.size[1]/change["page"]["height"],
        (change["x"]+change["width"]) * im.size[0]/change["page"]["width"],
        (change["y"]+change["height"]) * im.size[1]/change["page"]["height"],
        )

    draw = ImageDraw.Draw(im)
    draw.rectangle(coords, outline="red")
    del draw

# Zealous crop all of the pages. Vertical margins can be cropped
# however, but be sure to crop all pages the same horizontally.
for idx in (0, 1):
    # min horizontal extremes
    minx = None
    maxx = None
    width = None
    for pdf in pages[idx].values():
        bbox = ImageOps.invert(pdf.convert("L")).getbbox()
        minx = min(bbox[0], minx) if minx else bbox[0]
        maxx = min(bbox[2], maxx) if maxx else bbox[2]
        width = pdf.size[0]
    if width != None:
        minx = max(0, minx-int(.02*width)) # add back some margins
        maxx = min(width, maxx+int(.02*width))
    # do crop
    for pg in pages[idx]:
        im = pages[idx][pg]
        bbox = ImageOps.invert(im.convert("L")).getbbox() # .invert() requires a grayscale image
        vpad = int(.02*im.size[1])
        pages[idx][pg] = im.crop( (minx, max(0, bbox[1]-vpad), maxx, min(im.size[1], bbox[3]+vpad) ) )

# Stack all of the changed pages into a final PDF.

# Compute the dimensions of the final image.
height = 0
width = [0, 0]
for idx in (0, 1):
    side_height = 0
    for pdf in pages[idx].values():
        side_height += pdf.size[1]
        width[idx] = max(width[idx], pdf.size[0])
    height = max(height, side_height)

# Paste in the page.
img = Image.new("RGBA", (sum(width), height))
draw = ImageDraw.Draw(img)
for idx in (0, 1):
    y = 0
    for pg in sorted(pages[idx]):
        pgimg = pages[idx][pg]
        img.paste(pgimg, (idx * width[0], y))
        draw.line( (0 if idx == 0 else width[0], y, sum(width[0:idx+1]), y), fill="black")
        y += pgimg.size[1]

# Draw a vertical line between the two sides.
draw.line( (width[0], 0, width[0], height), fill="black")

del draw

# Write it out.

img.save(sys.stdout.buffer, "PNG")


