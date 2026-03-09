import pdfplumber
from datetime import date

PDF_PATH = "C:/PARSER_ESCALAS/PDF_Escalas/ROTA-E_2026_03.pdf"


def parse_pdf():

    shifts = []

    with pdfplumber.open(PDF_PATH) as pdf:

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

                shifts.append({
                    "employee": employee,
                    "name": name,
                    "date": date(2026, 3, i-1),
                    "code": code
                })

    return shifts