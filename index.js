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
            // Normalize the string to remove whitespace padding & normalize internal whitespace.
            var normalized_str = textItem.str;
            normalized_str = normalized_str.replace(/^\s+/, "");
            normalized_str = normalized_str.replace(/\s+$/, "");
            normalized_str = normalized_str.replace(/\s+/, " ");

            // ensure that a space separates box text so words in adjacent boxes don't get shmushed together
            normalized_str += " ";

            // Drop any text boxes that are just whitespace.
            if (normalized_str.length == 0) return;

            // Per pdfjs's examples/text-only/pdf2svg.js, compute the coordinates this way.
            var tx = PDFJS.Util.transform(
              PDFJS.Util.transform(page.viewport.transform, textItem.transform),
              [1, 0, 0, -1, 0, 0]);

            // Record this text box. Note that since the y axis in a PDF goes up but hackers,
            // are used to the opposite, move the y coordinate to the top of the box.
            boxes.push({
              pdf: { index: index, file: process.argv[index+2] },
              page: { number: page.page, width: page.viewport.width, height: page.viewport.height },
              x: tx[4], y: tx[5]-textItem.height, width: textItem.width, height: textItem.height,
              text: normalized_str,
              startIndex: textlength });

            // add to the serialized text and increment the current position
            text.push(normalized_str);
            textlength += normalized_str.length;
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


function compare_documents(docs) {
  // Perform a comparison over the serialized text using Google's
  // Diff Match Patch library.
  var dmp = new diff_match_patch();
  var d = dmp.diff_main(docs[0].alltext, docs[1].alltext);

  // Process each diff hunk one by one and look at their corresponding
  // text boxes in the original PDFs.
  var offsets = [0, 0];
  var changes = [];
  for (var i = 0; i < d.length; i++) {
    if (d[i][0] == 0) {
      // This hunk represents a region in the two text documents that are
      // in common. So nothing to process but advance the counters.
      offsets[0] += d[i][1].length;
      offsets[1] += d[i][1].length;

      // Put a marker in the changes so we can line up equivalent parts
      // later.
      if (changes.length > 0 && changes[changes.length-1] !== '*')
        changes.push("*");

    } else {
      // This hunk represents a region of text only in the left (d[i][0] == -1)
      // or right (d[i][0] == +1) document. The change is d[i][1].length chars long.
      var idx = (d[i][0] == -1 ? 0 : 1);

      // Don't cause a box to be marked as a change only because of leading or
      // trailing whitespace.
      var hunk_offset = offsets[idx];
      var hunk_text = d[i][1];
      while (/^\s/.exec(hunk_text)) {
        hunk_offset++;
        hunk_text = hunk_text.substring(1);
      }
      while (/\s$/.exec(hunk_text)) {
        hunk_text = hunk_text.substring(0, hunk_text.length-1);
      }

      if (hunk_text.length > 0)
        mark_difference(hunk_text.length, hunk_offset, docs[idx].boxes, changes);
      
      offsets[idx] += d[i][1].length;

      // Although the text doesn't exist in the right document, we want to
      // mark the position where that text may have been to indicate an
      // insertion.
      var idx2 = 1 - idx;
      mark_difference(1, offsets[idx2]-1, docs[idx2].boxes, changes);
      mark_difference(0, offsets[idx2]+0, docs[idx2].boxes, changes);
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
      var changes = compare_documents([doc1, doc2]);
      console.log(JSON.stringify(changes, null, 4));
    });
  });
}

load_documents();
