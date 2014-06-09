pdf-diff
========

Finds differences between two PDF documents:

1. Compares the text layers of two PDF documents and outputs the bounding boxes of changed text.
2. Rasterizes the changed pages in the PDFs to a PNG and draws red outlines around changed text.

Unfortunately while I started this project in node.js, I couldn't figure out how to quickly do the rendering part in node.js and so I switched to Python where I had some similar code laying around already.

Installation
------------

	# for the comparison tool

	npm install

	git clone https://github.com/mozilla/pdf.js
	cd pdf.js
	node make singlefile
	cd ..

	# for the renderer

	sudo pip3 install pillow

Running
-------

Compute the changes (writes a JSON file):

	node index.js before.pdf after.pdf | grep -v "^Warning:" > changes.json

(Unfortunately the pdf.js library prints warnings on STDOUT, so we have to filter those out.)

Render the changes (turns the PDFs + JSON file into a big PNG image):

	python3 render.py < changes.json > test.png


