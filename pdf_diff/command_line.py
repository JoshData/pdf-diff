#!/usr/bin/python3

import sys

if sys.version_info[0] < 3:
    sys.exit("ERROR: Python version 3+ is required.")

import json, subprocess, io, os
from lxml import etree
from PIL import Image, ImageDraw, ImageOps

def compute_changes(pdf_fn_1, pdf_fn_2, top_margin=0, bottom_margin=100):
    # Serialize the text in the two PDFs.
    docs = [serialize_pdf(0, pdf_fn_1, top_margin, bottom_margin), serialize_pdf(1, pdf_fn_2, top_margin, bottom_margin)]

    # Compute differences between the serialized text.
    diff = perform_diff(docs[0][1], docs[1][1])
    changes = process_hunks(diff, [docs[0][0], docs[1][0]])

    return changes

def serialize_pdf(i, fn, top_margin, bottom_margin):
    box_generator = pdf_to_bboxes(i, fn, top_margin, bottom_margin)
    box_generator = mark_eol_hyphens(box_generator)

    boxes = []
    text = []
    textlength = 0
    for run in box_generator:
        if run["text"] is None:
            continue

        normalized_text = run["text"].strip()

        # Ensure that each run ends with a space, since pdftotext
        # strips spaces between words. If we do a word-by-word diff,
        # that would be important.
        #
        # But don't put in a space if the box ends in a discretionary
        # hyphen. Instead, remove the hyphen.
        if normalized_text.endswith("\u00AD"):
            normalized_text = normalized_text[0:-1]
        else:
            normalized_text += " "

        run["text"] = normalized_text
        run["startIndex"] = textlength
        run["textLength"] = len(normalized_text)
        boxes.append(run)
        text.append(normalized_text)
        textlength += len(normalized_text)

    text = "".join(text)
    return boxes, text

def pdf_to_bboxes(pdf_index, fn, top_margin=0, bottom_margin=100):
    # Get the bounding boxes of text runs in the PDF.
    # Each text run is returned as a dict.
    box_index = 0
    pdfdict = {
        "index": pdf_index,
        "file": fn,
    }
    xml = subprocess.check_output(["pdftotext", "-bbox", fn, "/dev/stdout"])

    # This avoids PCDATA errors
    codes_to_avoid = [ 0, 1, 2, 3, 4, 5, 6, 7, 8,
                       11, 12,
                       14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, ]

    cleaned_xml = bytes([x for x in xml if x not in codes_to_avoid])

    dom = etree.fromstring(cleaned_xml)
    for i, page in enumerate(dom.findall(".//{http://www.w3.org/1999/xhtml}page")):
        pagedict = {
            "number": i+1,
            "width": float(page.get("width")),
            "height": float(page.get("height"))
        }
        for word in page.findall("{http://www.w3.org/1999/xhtml}word"):
            if float(word.get("yMax")) < (top_margin/100.0)*float(page.get("height")):
                continue
            if float(word.get("yMin")) > (bottom_margin/100.0)*float(page.get("height")):
                continue

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

def mark_eol_hyphens(boxes):
    # Replace end-of-line hyphens with discretionary hyphens so we can weed
    # those out later. Finding the end of a line is hard.
    box = None
    for next_box in boxes:
        if box is not None:
            if box['pdf'] != next_box['pdf'] or box['page'] != next_box['page'] \
                or next_box['y'] >= box['y'] + box['height']/2:
                # box was at the end of a line
                mark_eol_hyphen(box)
            yield box
        box = next_box
    if box is not None:
        # The last box is at the end of a line too.
        mark_eol_hyphen(box)
        yield box

def mark_eol_hyphen(box):
    if box['text'].endswith("-"):
        box['text'] = box['text'][0:-1] + "\u00AD"

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

# Turns a JSON object of PDF changes into a PIL image object.
def render_changes(changes, styles,width):
    # Merge sequential boxes to avoid sequential disjoint rectangles.

    changes = simplify_changes(changes)
    if len(changes) == 0:
        raise Exception("There are no text differences.")

    # Make images for all of the pages named in changes.

    pages = make_pages_images(changes,width)

    # Convert the box coordinates (PDF coordinates) into image coordinates.
    # Then set change["page"] = change["page"]["number"] so that we don't
    # share the page object between changes (since we'll be rewriting page
    # numbers).
    for change in changes:
        if change == "*": continue
        im = pages[change["pdf"]["index"]][change["page"]["number"]]
        change["x"] *= im.size[0]/change["page"]["width"]
        change["y"] *= im.size[1]/change["page"]["height"]
        change["width"] *= im.size[0]/change["page"]["width"]
        change["height"] *= im.size[1]/change["page"]["height"]
        change["page"] = change["page"]["number"]

    # To facilitate seeing how two corresponding pages align, we will
    # break up pages into sub-page images and insert whitespace between
    # them.

    page_groups = realign_pages(pages, changes)

    # Draw red rectangles.

    draw_red_boxes(changes, pages, styles)

    # Zealous crop to make output nicer. We do this after
    # drawing rectangles so that we don't mess up coordinates.

    zealous_crop(page_groups)

    # Stack all of the changed pages into a final PDF.

    img = stack_pages(page_groups)

    return img

def make_pages_images(changes,width):
    pages = [{}, {}]
    for change in changes:
        if change == "*": continue # not handled yet
        pdf_index = change["pdf"]["index"]
        pdf_page = change["page"]["number"]
        if pdf_page not in pages[pdf_index]:
            pages[pdf_index][pdf_page] = pdftopng(change["pdf"]["file"], pdf_page,width)
    return pages

def realign_pages(pages, changes):
    # Split pages into sub-page images at locations of asterisks
    # in the changes where no boxes will cross the split point.
    for pdf in (0, 1):
        for page in list(pages[pdf]): # clone before modifying
            # Re-do all of the page "numbers" to be a tuple of
            # (page, split).
            split_index = 0
            pg = pages[pdf][page]
            del pages[pdf][page]
            pages[pdf][(page, split_index)] = pg
            for box in changes:
                if box != "*" and box["pdf"]["index"] == pdf and box["page"] == page:
                    box["page"] = (page, 0)

            # Look for places to split.
            for i, box in enumerate(changes):
                if box != "*": continue

                # This is a "*" marker, indicating this is a place where the left
                # and right pages line up. Get the lowest y coordinate of a change
                # above this point and the highest y coordinate of a change after
                # this point. If there's no overlap, we can split the PDF here.
                try:
                    y1 = max(b["y"]+b["height"] for j, b in enumerate(changes)
                        if j < i and b != "*" and b["pdf"]["index"] == pdf and b["page"] == (page, split_index))
                    y2 = min(b["y"] for j, b in enumerate(changes)
                        if j > i and b != "*" and b["pdf"]["index"] == pdf and b["page"] == (page, split_index))
                except ValueError:
                    # Nothing either before or after this point, so no need to split.
                    continue
                if y1+1 >= y2:
                    # This is not a good place to split the page.
                    continue

                # Split the PDF page between the bottom of the previous box and
                # the top of the next box.
                split_coord = int(round((y1+y2)/2))

                # Make a new image for the next split-off part.
                im = pages[pdf][(page, split_index)]
                pages[pdf][(page, split_index)] = im.crop([0, 0, im.size[0], split_coord ])
                pages[pdf][(page, split_index+1)] = im.crop([0, split_coord, im.size[0], im.size[1] ])

                # Re-do all of the coordinates of boxes after the split point:
                # map them to the newly split-off part.
                for j, b in enumerate(changes):
                    if j > i and b != "*" and b["pdf"]["index"] == pdf and b["page"] == (page, split_index):
                        b["page"] = (page, split_index+1)
                        b["y"] -= split_coord
                split_index += 1

    # Re-group the pages by where we made a split on both sides.
    page_groups = [({}, {})]
    for i, box in enumerate(changes):
        if box != "*":
            page_groups[-1][ box["pdf"]["index"] ][ box["page"] ] = pages[box["pdf"]["index"]][box["page"]]
        else:
            # Did we split at this location?
            pages_before = set((b["pdf"]["index"], b["page"]) for j, b in enumerate(changes) if j < i and b != "*")
            pages_after = set((b["pdf"]["index"], b["page"]) for j, b in enumerate(changes) if j > i and b != "*")
            if len(pages_before & pages_after) == 0:
                # no page is on both sides of this asterisk, so start a new group
                page_groups.append( ({}, {}) )
    return page_groups

def draw_red_boxes(changes, pages, styles):
    # Draw red boxes around changes.

    for change in changes:
        if change == "*": continue # not handled yet

        # 'box', 'strike', 'underline'
        style = styles[change["pdf"]["index"]]

        # the Image of the page
        im = pages[change["pdf"]["index"]][change["page"]]

        # draw it
        draw = ImageDraw.Draw(im)

        if style == "box":
            draw.rectangle((
                change["x"], change["y"],
                (change["x"]+change["width"]), (change["y"]+change["height"]),
                ), outline="red")
        elif style == "strike":
            draw.line((
                change["x"], change["y"]+change["height"]/2,
                change["x"]+change["width"], change["y"]+change["height"]/2
                ), fill="red")
        elif style == "underline":
            draw.line((
                change["x"], change["y"]+change["height"],
                change["x"]+change["width"], change["y"]+change["height"]
                ), fill="red")

        del draw

def zealous_crop(page_groups):
    # Zealous crop all of the pages. Vertical margins can be cropped
    # however, but be sure to crop all pages the same horizontally.
    for idx in (0, 1):
        # min horizontal extremes
        minx = None
        maxx = None
        width = None
        for grp in page_groups:
            for pdf in grp[idx].values():
                bbox = ImageOps.invert(pdf.convert("L")).getbbox()
                if bbox is None: continue # empty
                minx = min(bbox[0], minx) if minx is not None else bbox[0]
                maxx = max(bbox[2], maxx) if maxx is not None else bbox[2]
                width = max(width, pdf.size[0]) if width is not None else pdf.size[0]
        if width != None:
            minx = max(0, minx-int(.02*width)) # add back some margins
            maxx = min(width, maxx+int(.02*width))
            # do crop
        for grp in page_groups:
            for pg in grp[idx]:
                im = grp[idx][pg]
                bbox = ImageOps.invert(im.convert("L")).getbbox() # .invert() requires a grayscale image
                if bbox is None: bbox = [0, 0, im.size[0], im.size[1]] # empty page
                vpad = int(.02*im.size[1])
                im = im.crop( (0, max(0, bbox[1]-vpad), im.size[0], min(im.size[1], bbox[3]+vpad) ) )
                if os.environ.get("HORZCROP", "1") != "0":
                    im = im.crop( (minx, 0, maxx, im.size[1]) )
                grp[idx][pg] = im

def stack_pages(page_groups):
    # Compute the dimensions of the final image.
    col_height = [0, 0]
    col_width = 0
    page_group_spacers = []
    for grp in page_groups:
        for idx in (0, 1):
            for im in grp[idx].values():
                col_height[idx] += im.size[1]
                col_width = max(col_width, im.size[0])

        dy = col_height[1] - col_height[0]
        if abs(dy) < 10: dy = 0 # don't add tiny spacers
        page_group_spacers.append( (dy if dy > 0 else 0, -dy if dy < 0 else 0)  )
        col_height[0] += page_group_spacers[-1][0]
        col_height[1] += page_group_spacers[-1][1]

    height = max(col_height)

    # Draw image with some background lines.
    img = Image.new("RGBA", (col_width*2+1, height), "#F3F3F3")
    draw = ImageDraw.Draw(img)
    for x in range(0, col_width*2+1, 50):
        draw.line( (x, 0, x, img.size[1]), fill="#E3E3E3")

    # Paste in the page.
    for idx in (0, 1):
        y = 0
        for i, grp in enumerate(page_groups):
            for pg in sorted(grp[idx]):
                pgimg = grp[idx][pg]
                img.paste(pgimg, (0 if idx == 0 else (col_width+1), y))
                if pg[0] > 1 and pg[1] == 0:
                    # Draw lines between physical pages. Since we split
                    # pages into sub-pages, check that the sub-page index
                    # pg[1] is the start of a logical page. Draw lines
                    # above pages, but not on the first page pg[0] == 1.
                    draw.line( (0 if idx == 0 else col_width, y, col_width*(idx+1), y), fill="black")
                y += pgimg.size[1]
            y += page_group_spacers[i][idx]

    # Draw a vertical line between the two sides.
    draw.line( (col_width, 0, col_width, height), fill="black")

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
def pdftopng(pdffile, pagenumber,width):
    pngbytes = subprocess.check_output(["pdftoppm", "-f", str(pagenumber), "-l", str(pagenumber), "-scale-to", str(width), "-png", pdffile])
    im = Image.open(io.BytesIO(pngbytes))
    return im.convert("RGBA")

def main():
    import argparse

    description = ('Calculates the differences between two specified files in PDF format '
                   '(or changes specified on standard input) and outputs to standard output '
                   'side-by-side images with the differences marked (in PNG format).')
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('files', nargs='*', # Use '*' to allow --changes with zero files
                        help='calculate differences between the two named files')
    parser.add_argument('-c', '--changes', action='store_true', default=False, 
                        help='read change description from standard input, ignoring files')
    parser.add_argument('-s', '--style', metavar='box|strike|underline,box|stroke|underline', 
                        default='strike,underline',
                        help='how to mark the differences in the two files (default: strike, underline)')
    parser.add_argument('-f', '--format', choices=['png','gif','jpeg','ppm','tiff'], default='png',
                        help='output format in which to render (default: png)')
    parser.add_argument('-t', '--top-margin', metavar='margin', default=0., type=float,
                        help='top margin (ignored area) end in percent of page height (default 0.0)')
    parser.add_argument('-b', '--bottom-margin', metavar='margin', default=100., type=float,
                        help='bottom margin (ignored area) begin in percent of page height (default 100.0)')
    parser.add_argument('-r', '--result-width', default=900, type=int,
                        help='width of the result image (width of image in px)')
    args = parser.parse_args()

    def invalid_usage(msg):
        sys.stderr.write('ERROR: %s%s' % (msg, os.linesep))
        parser.print_usage(sys.stderr)
        sys.exit(1)

    # Validate style
    style = args.style.split(',')
    if len(style) != 2:
        invalid_usage('Exactly two style values must be specified, if --style is used.')
    for i in [0,1]:
        if style[i] != 'box' and style[i] != 'strike' and style[i] != 'underline':
            invalid_usage('--style values must be box, strike or underline, not "%s".' % (style[i]))

    # Ensure one of files or --changes are specified
    if len(args.files) == 0 and not args.changes:
        invalid_usage('Please specify files to compare, or use --changes option.')

    if args.changes:
        # to just do the rendering part
        img = render_changes(json.load(sys.stdin), style, args.result_width)
        img.save(sys.stdout.buffer, args.format.upper())
        sys.exit(0)

    # Ensure enough file are specified
    if len(args.files) != 2:
        invalid_usage('Insufficient number of files to compare; please supply exactly 2.')

    changes = compute_changes(args.files[0], args.files[1], top_margin=float(args.top_margin), bottom_margin=float(args.bottom_margin))
    img = render_changes(changes, style, args.result_width)
    img.save(sys.stdout.buffer, args.format.upper())


if __name__ == "__main__":
    main()
