"""
Reads the uploaded expense export file and returns a list of plain
row dicts. Despite the assignment calling it "expenses_export.csv",
the actual provided file is a real .xlsx - this parser is built
against the file we were actually given, not the name in the prompt.

Deliberately does NOT do any cleaning, validation, or anomaly
detection - its only job is "turn a spreadsheet row into a plain
Python dict." That separation keeps this file trivial to test in
isolation, and keeps anomaly_detector.py free of any file-format
concerns.
"""

import openpyxl


EXPECTED_COLUMNS = [
    "date", "description", "paid_by", "amount",
    "currency", "split_type", "split_with", "split_details", "notes",
]


class RowParseError(Exception):
    """Raised for a single row that couldn't be read at all."""
    pass


def parse_expense_file(file_path_or_buffer):
    """
    Returns a list of dicts: [{"row_number": 2, "data": {...}}, ...]

    row_number matches the actual Excel row (header = row 1, so the
    first data row is row 2) - this is deliberate, so anomaly reports
    reference the same row numbers a human would see opening the file
    directly, not a re-indexed position.

    Each row is parsed independently. A single bad row is recorded
    with an error marker rather than raising - the whole file must
    never fail to import because of one corrupted row.
    """
    workbook = openpyxl.load_workbook(file_path_or_buffer, data_only=True)
    sheet = workbook.active

    header_row = [cell.value for cell in sheet[1]]
    header_map = {}
    for expected_col in EXPECTED_COLUMNS:
        try:
            header_map[expected_col] = header_row.index(expected_col)
        except ValueError:
            header_map[expected_col] = None  # column missing entirely from this file

    rows = []
    for row_number, row_cells in enumerate(sheet.iter_rows(min_row=2), start=2):
        try:
            row_data = {}
            for column_name, column_index in header_map.items():
                if column_index is None:
                    row_data[column_name] = None
                else:
                    cell_value = row_cells[column_index].value
                    row_data[column_name] = cell_value
            rows.append({"row_number": row_number, "data": row_data, "parse_error": None})
        except Exception as e:
            # Never let one malformed row take down the whole import.
            rows.append({
                "row_number": row_number,
                "data": {},
                "parse_error": f"Could not read row {row_number}: {e}",
            })

    return rows