import pdfplumber
from datetime import date

VALID_SHIFT_CODES = {
    "M",
    "T",
    "N",
    "MG",
    "Mt",
    "DC",
    "DS"
}

def parse_pdf(pdf_path, year, month):

    shifts = []

    with pdfplumber.open(pdf_path) as pdf:

        page = pdf.pages[0]

        table = page.extract_table()

        for row in table:

            if not row:
                continue

            employee = row[0]
            name = row[1]

            if not employee or not name:
                continue

            # percorrer dias do mês
            for i in range(2, len(row)):

                code = row[i]

                if not code:
                    continue

                if code not in VALID_SHIFT_CODES:
                    continue

                shifts.append({
                    "employee": employee,
                    "name": name,
                    "date": date(year, month, i-1),
                    "code": code
                })

    return shifts