# pdf-diff

Finds differences between two PDF documents:

1. Compares the text layers of two PDF documents and outputs the bounding boxes of changed text in JSON.
2. Rasterizes the changed pages in the PDFs to a PNG and draws red outlines around changed text.

![Example Image Output](example.png)

The script is written in Python 3, and it relies on the `pdftotext` program.

## Installation

### Ubuntu

    sudo apt-get install python3-lxml poppler-utils

### OS X

    brew install libxml2 poppler

### All operating systems

    sudo pip3 install -r requirements.txt

## Running

Turn two PDFs into one large PNG image showing the differences:

    python3 pdf-diff.py before.pdf after.pdf > test.png
