var fs = require("fs");
var exec = require('child_process').exec;
var async = require("async");
var diff_match_patch = require('googlediff');

/* per pdf.js's examples/node/getinfo.js, a hack to be able to load the package */
global.window = global;
global.window.location = { href: "" };
global.navigator = { userAgent: "node" };
global.PDFJS = {};
require("./pdf.js/build/singlefile/build/pdf.combined.js");

function load_document(index, callback) {
  // load the file into a bytes array
  var data = new Uint8Array(fs.readFileSync(process.argv[2 + index]));

  // parse the file
  PDFJS.getDocument(data).then(function (pdfDocument) {
    var page_numbers = [];
    for (var i = 1; i <= pdfDocument.numPages; i++)
      page_numbers.push(i);

    // load the text of each page
    async.mapSeries(
      page_numbers,
      function(page_number, callback) {
        // load the page...
        pdfDocument.getPage(page_number).then(function (page) {
          var viewport = page.getViewport(1.0);
          // load the text...
          page.getTextContent().then(function (textContent) {
            callback(null, { page: page_number, viewport: viewport, text: textContent })
          });
        });
      },
      function(err, results) {
        // Okay now we have the viewport & text of each page.
        // Serialize the text into two things:
        //   alltext: the concatenation of the text strings in the PDF
        //   boxes: an array of text objects in the PDF file, each an object with fields:
        //     page: the 1-based page number
        //     x, y: the coordinates of the text on the page
        //     width, height: the width and height of the text box
        //     text: the text in this box
        //     startIndex: the character position in alltext where this text box starts

        var boxes = [];
        var text = [];
        var textlength = 0;
        results.forEach(function(page) {
          page.text.items.forEach(function (textItem) {
            if (textItem.str.length == 0) return; // not sure if it occurs, but this would cause trouble

            // per pdfjs's examples/text-only/pdf2svg.js
            var tx = PDFJS.Util.transform(
              PDFJS.Util.transform(page.viewport.transform, textItem.transform),
              [1, 0, 0, -1, 0, 0]);

            // record this text box
            boxes.push({
              pdf: { index: index, file: process.argv[index+2] },
              page: { number: page.page, width: page.viewport.width, height: page.viewport.height },
              x: tx[4], y: tx[5], width: textItem.width, height: textItem.height,
              text: textItem.str,
              startIndex: textlength });

            // add to the serialized text and increment the current position
            text.push(textItem.str);
            textlength += textItem.str.length;
          });
        })

        callback({ boxes: boxes, alltext: text.join("") });
      }
    );
  });
}

function mark_difference(hunk_length, offset, boxes, changes) {
  // We're passed an offset and length into a document given to us
  // by the text comparison, and we'll mark the text boxes passed
  // in boxes as having changed content.

  // Discard boxes whose text is entirely before this hunk
  while (boxes.length > 0 && (boxes[0].startIndex + boxes[0].text.length) <= offset)
    boxes.shift();

  // Process the boxes that intersect this hunk. We can't subdivide boxes,
  // so even though not all of the text in the box might be changed we'll
  // mark the whole box as changed.
  while (boxes.length > 0 && boxes[0].startIndex < offset + hunk_length) {
    // Mark this box as changed.
    changes.push(boxes[0]);

    // Discard box. Now that we know it's changed, there's no reason to
    // hold onto it. It can't be marked as changed twice.
    boxes.shift();
  }
}


function compare_documents(doc1, doc2) {
  // Perform a comparison over the serialized text using Google's
  // Diff Match Patch library.
  var dmp = new diff_match_patch();
  var d = dmp.diff_main(doc1.alltext, doc2.alltext);

  // Process each diff hunk one by one and look at their corresponding
  // text boxes in the original PDFs.
  var left_offset = 0;
  var right_offset = 0;
  var changes = [];
  for (var i = 0; i < d.length; i++) {
    if (d[i][0] == 0) {
      // This hunk represents a region in the two text documents that are
      // in common. So nothing to process but advance the counters.
      left_offset += d[i][1].length;
      right_offset += d[i][1].length;

      // Put a marker in the changes so we can line up equivalent parts
      // later.
      if (changes.length > 0 && changes[changes.length-1] !== '*')
        changes.push("*");

    } else if (d[i][0] == -1) {
      // This hunk represents a region of text only in the left document
      // that is d[i][1].length characters long.
      mark_difference(d[i][1].length, left_offset, doc1.boxes, changes);
      left_offset += d[i][1].length;

    } else if (d[i][0] == 1) {
      // This hunk represents a region of text only in the right document
      // that is d[i][1].length characters long.
      mark_difference(d[i][1].length, right_offset, doc2.boxes, changes);
      right_offset += d[i][1].length;
    }

  }

  // Remove any final asterisk.
  if (changes.length > 0 && changes[changes.length-1] === "*")
    changes.pop();

  return changes;
}

function load_documents() {
  // Load the contents of the two PDFs.
  load_document(0, function(doc1) {
    load_document(1, function(doc2) {
      var changes = compare_documents(doc1, doc2);
      console.log(JSON.stringify(changes, null, 4));
    });
  });
}

load_documents();
