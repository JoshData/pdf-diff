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
