# pdf-diff

Finds differences between two PDF documents:

1. Compares the text layers of two PDF documents and outputs the bounding boxes of changed text in JSON.
2. Rasterizes the changed pages in the PDFs to a PNG and draws red outlines around changed text.

![Example Image Output](example.png)

The script is written in Python 3, and it relies on the `pdftotext` program.

## Requirements
    
    libxml2 >= 2.7.0, libxslt >= 1.1.23, poppler
## Requirements installation for Ubuntu:
    
    sudo apt-get install python3-lxml poppler-utils
## Requirements installation for OS X:
    
    brew install libxml2 libxslt poppler
## Installation

From PyPI:

    pip install pdf-diff

From source:

    sudo python3 setup.py install
## Running

Turn two PDFs into one large PNG image showing the differences:

    pdf-diff before.pdf after.pdf > comparison_output.png

## Maintainer Notes

To deploy:

	python3 -m pip install --user --upgrade setuptools wheel twine
	python3 setup.py sdist bdist_wheel
	python3 -m twine upload dist/*

## Function flow diagram

```
compute_changes
│
├── serialize_pdf (called twice)
│    ├── pdf_to_bboxes
│    ├── mark_eol_hyphens
│    │    └── mark_eol_hyphen
│    └── Processes bounding boxes and text
│
├── perform_diff
│    └── Calls external `fast_diff_match_patch`
│
└── process_hunks
     ├── Iterates through diff hunks
     └── mark_difference (called multiple times)

render_changes
│
├── simplify_changes
├── make_pages_images
│    └── pdftopng (converts PDF pages to images)
├── realign_pages
│    ├── Splits pages into sub-pages
│    └── Adjusts box coordinates
├── draw_red_boxes
│    └── Annotates images with rectangles or lines
└── zealous_crop
     └── Crops the image to reduce unnecessary margins

stack_pages
│
└── Combines processed images into a final output
```

