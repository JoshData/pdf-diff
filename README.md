pdf-diff
========

Finds differences between two PDF documents:

1. Compares the text layers of two PDF documents and outputs the bounding boxes of changed text in JSON.
2. Rasterizes the changed pages in the PDFs to a PNG and draws red outlines around changed text.

![Example Image Output](example.png)

The script is written in Python 3, and it relies on the `pdftotext` program.

Installation
------------

	sudo apt-get install libxml2-dev libxslt1-dev poppler-utils # on Ubuntu, at least
	sudo pip3 install pillow lxml

	# get my Python extension module for the Google Diff Match Patch library
	# so we can compute differences in text very quickly
	git clone --recursive https://github.com/JoshData/diff_match_patch-python
	cd diff_match_patch-python
	sudo apt-get install python3-dev
	python3 setup.py build
	sudo python3 setup.py install

Running
-------

Turn two PDFs into one large PNG image showing the differences:

	python3 pdf-diff.py before.pdf after.pdf > test.png


Node Version
------------

There's also a node.js version for computing the changes that uses Mozilla's pdf.js instead of `pdftotext`. Getting pdf.js to work in node.js isn't straightforward:

	npm install

	git clone https://github.com/mozilla/pdf.js
	cd pdf.js
	node make singlefile
	cd ..

Compute the changes (writes a JSON file):

	node index.js before.pdf after.pdf | grep -v "^Warning:" > changes.json

(Unfortunately the pdf.js library prints warnings on STDOUT, so we have to filter those out.)

Render the changes:

	python3 pdf-diff.py --changes < changes.json > test.png

`pdftotext` gives bounding boxes for each word in the document while pdf.js only gives bounding boxes for text runs, so the granularity is not as good.
