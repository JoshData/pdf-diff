import sys

import pdf_diff.command_line as command_line


def test_identical_pdfs_report_no_differences(monkeypatch, capsys):
    # Two identical PDFs produce an empty change list.
    monkeypatch.setattr(command_line, "compute_changes",
                        lambda *args, **kwargs: [])
    monkeypatch.setattr(sys, "argv", ["pdf-diff", "a.pdf", "b.pdf"])
    try:
        command_line.main()
    except SystemExit as exc:
        code = exc.code
    else:
        code = None
    assert code == 0
    assert "no differences" in capsys.readouterr().err.lower()
