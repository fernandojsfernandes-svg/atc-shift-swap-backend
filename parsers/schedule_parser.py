import pdfplumber
from datetime import date


def parse_schedule_pdf(pdf_path, year=2026, month=3):

    shifts = []

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]

        tables = page.extract_tables()

        for table in tables:
            for row in table:

                if not row:
                    continue

                # ignorar linhas de título
                if not row[0] or not row[0].isdigit():
                    continue

                employee_number = row[0]
                name = row[1]

                # dias começam na coluna 2
                for day_index, code in enumerate(row[2:], start=1):

                    if not code:
                        continue

                    shifts.append({
                        "employee": employee_number,
                        "name": name,
                        "date": date(year, month, day_index),
                        "code": code
                    })

    return shifts