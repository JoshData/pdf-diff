#!/usr/bin/python3

import sys, json, subprocess, io
from lxml import etree
from PIL import Image, ImageDraw, ImageOps

def compute_changes(pdf_fn_1, pdf_fn_2):
    # Serialize the text in the two PDFs.
    docs = [serialize_pdf(0, pdf_fn_1), serialize_pdf(1, pdf_fn_2)]

    # Compute differences between the serialized text.
    diff = perform_diff(docs[0][1], docs[1][1])
    changes = process_hunks(diff, [docs[0][0], docs[1][0]])

    return changes

def serialize_pdf(i, fn):
    boxes = []
    text = []
    textlength = 0
    for run in pdf_to_bboxes(i, fn):
        normalized_text = run["text"]

        # Ensure that each run ends with a space, since pdftotext
        # strips spaces between words. If we do a word-by-word diff,
        # that would be important.
        normalized_text = normalized_text.strip() + " "

        run["text"] = normalized_text
        run["startIndex"] = textlength
        run["textLength"] = len(normalized_text)
        boxes.append(run)
        text.append(normalized_text)
        textlength += len(normalized_text)

    text = "".join(text)
    return boxes, text

def pdf_to_bboxes(pdf_index, fn):
    # Get the bounding boxes of text runs in the PDF.
    # Each text run is returned as a dict.
    box_index = 0
    pdfdict = {
        "index": pdf_index,
        "file": fn,
    }
    xml = subprocess.check_output(["pdftotext", "-bbox", fn, "/dev/stdout"])
    dom = etree.fromstring(xml)
    for i, page in enumerate(dom.findall(".//{http://www.w3.org/1999/xhtml}page")):
        pagedict = {
            "number": i+1,
            "width": float(page.get("width")),
            "height": float(page.get("height"))
        }
        for word in page.findall("{http://www.w3.org/1999/xhtml}word"):
            yield {
                "index": box_index,
                "pdf": pdfdict,
                "page": pagedict,
                "x": float(word.get("xMin")),
                "y": float(word.get("yMin")),
                "width": float(word.get("xMax"))-float(word.get("xMin")),
                "height": float(word.get("yMax"))-float(word.get("yMin")),
                "text": word.text,
                }
            box_index += 1

def perform_diff(doc1text, doc2text):
    import diff_match_patch
    return diff_match_patch.diff(
        doc1text,
        doc2text,
        timelimit=0,
        checklines=False)

def process_hunks(hunks, boxes):
    # Process each diff hunk one by one and look at their corresponding
    # text boxes in the original PDFs.
    offsets = [0, 0]
    changes = []
    for op, oplen in hunks:
        if op == "=":
            # This hunk represents a region in the two text documents that are
            # in common. So nothing to process but advance the counters.
            offsets[0] += oplen;
            offsets[1] += oplen;

            # Put a marker in the changes so we can line up equivalent parts
            # later.
            if len(changes) > 0 and changes[-1] != '*':
                changes.append("*");

        elif op in ("-", "+"):
            # This hunk represents a region of text only in the left (op == "-")
            # or right (op == "+") document. The change is oplen chars long.
            idx = 0 if (op == "-") else 1

            mark_difference(oplen, offsets[idx], boxes[idx], changes)

            offsets[idx] += oplen

            # Although the text doesn't exist in the other document, we want to
            # mark the position where that text may have been to indicate an
            # insertion.
            idx2 = 1 - idx
            mark_difference(1, offsets[idx2]-1, boxes[idx2], changes)
            mark_difference(0, offsets[idx2]+0, boxes[idx2], changes)

        else:
            raise ValueError(op)

    # Remove any final asterisk.
    if len(changes) > 0 and changes[-1] == "*":
        changes.pop()

    return changes

def mark_difference(hunk_length, offset, boxes, changes):
  # We're passed an offset and length into a document given to us
  # by the text comparison, and we'll mark the text boxes passed
  # in boxes as having changed content.

  # Discard boxes whose text is entirely before this hunk
  while len(boxes) > 0 and (boxes[0]["startIndex"] + boxes[0]["textLength"]) <= offset:
    boxes.pop(0)

  # Process the boxes that intersect this hunk. We can't subdivide boxes,
  # so even though not all of the text in the box might be changed we'll
  # mark the whole box as changed.
  while len(boxes) > 0 and boxes[0]["startIndex"] < offset + hunk_length:
    # Mark this box as changed. Discard the box. Now that we know it's changed,
    # there's no reason to hold onto it. It can't be marked as changed twice.
    changes.append(boxes.pop(0))

# Turns a JSON object of PDF changes into a PNG and writes it to stream.
def render_changes(changes, stream):
    # Merge sequential boxes to avoid sequential disjoint rectangles.
    
    changes = simplify_changes(changes)

    # Make images for all of the pages named in changes.

    pages = make_pages_images(changes)

    # Draw red rectangles.

    draw_red_boxes(changes, pages)

    # Zealous crop to make output nicer. We do this after
    # drawing rectangles so that we don't mess up coordinates.

    zealous_crop(pages)

    # Stack all of the changed pages into a final PDF.

    img = stack_pages(pages)

    # Write it out.

    img.save(stream, "PNG")


def make_pages_images(changes):
    pages = [{}, {}]
    for change in changes:
        if change == "*": continue # not handled yet
        pdf_index = change["pdf"]["index"]
        pdf_page = change["page"]["number"]
        if pdf_page not in pages[pdf_index]:
            pages[pdf_index][pdf_page] = pdftopng(change["pdf"]["file"], pdf_page)
    return pages

def draw_red_boxes(changes, pages):
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

def zealous_crop(pages):
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

def stack_pages(pages):
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

    return img

def simplify_changes(boxes):
    # Combine changed boxes when they were sequential in the input.
    # Our bounding boxes may be on a word-by-word basis, which means
    # neighboring boxes will lead to discontiguous rectangles even
    # though they are probably the same semantic change.
    changes = []
    for b in boxes:
        if len(changes) > 0 and changes[-1] != "*" and b != "*" \
            and changes[-1]["pdf"] == b["pdf"] \
            and changes[-1]["page"] == b["page"] \
            and changes[-1]["index"]+1 == b["index"] \
            and changes[-1]["y"] == b["y"] \
            and changes[-1]["height"] == b["height"]:
            changes[-1]["width"] = b["x"]+b["width"] - changes[-1]["x"]
            changes[-1]["text"] += b["text"]
            changes[-1]["index"] += 1 # so that in the next iteration we can expand it again
            continue
        changes.append(b)
    return changes

# Rasterizes a page of a PDF.
def pdftopng(pdffile, pagenumber, width=900):
    pngbytes = subprocess.check_output(["/usr/bin/pdftoppm", "-f", str(pagenumber), "-l", str(pagenumber), "-scale-to", str(width), "-png", pdffile])
    im = Image.open(io.BytesIO(pngbytes))
    return im.convert("RGBA")

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--changes":
        # to just do the rendering part
        render_changes(json.load(sys.stdin), sys.stdout.buffer)
        sys.exit(0)

    if len(sys.argv) <= 1:
        print("Usage: python3 pdf-diff.py before.pdf after.pdf > changes.png", file=sys.stderr)
        sys.exit(1)

    changes = compute_changes(sys.argv[1], sys.argv[2])
    render_changes(changes, sys.stdout.buffer)
