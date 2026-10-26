"""Derive templates/output_template.xlsx from the client's sample workbook.

Keeps Sheet1's header row, column widths, fonts, number formats and wrap settings, plus one
styled (empty) data row the exporter clones. All call-log data, comments and the other sheets
are removed so no personal data ends up in the template.

    python scripts/build_template.py "../khushi new (2).xlsx"
"""
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]


def build(sample: Path, out: Path) -> None:
    wb = openpyxl.load_workbook(sample)
    ws = wb["Sheet1"]
    for name in [n for n in wb.sheetnames if n != "Sheet1"]:
        del wb[name]
    if ws.max_row > 2:
        ws.delete_rows(3, ws.max_row - 2)
    for row in ws.iter_rows(min_row=1, max_row=2):
        for cell in row:
            if cell.row == 2 or cell.column > 5:
                cell.value = None
                cell.hyperlink = None
    ws.title = "Results"
    ws.auto_filter.ref = None
    # The sample was saved scrolled to row ~2,870: reset the view so exports open at the top.
    ws.sheet_view.topLeftCell = "A1"
    for sel in ws.sheet_view.selection:
        sel.activeCell, sel.sqref = "A2", "A2"
    for idx in [i for i in ws.row_dimensions if i > 2]:
        del ws.row_dimensions[idx]
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"Template written to {out} (headers: {[c.value for c in ws[1][:5]]})")


if __name__ == "__main__":
    build(Path(sys.argv[1]), ROOT / "templates" / "output_template.xlsx")
