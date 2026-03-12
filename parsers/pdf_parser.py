import pdfplumber
from datetime import date
from collections import Counter


VALID_SHIFT_CODES = {
    "M",
    "T",
    "N",
    "MG",
    "Mt",
    "DC",
    "DS",
}


def _get_cell_color(image, cell_box):
    """
    Devolve a cor RGB mais frequente dentro da célula (x0, top, x1, bottom),
    ou None se não houver pixels.
    """
    if not cell_box:
        return None

    cropped_image = image.crop(cell_box)
    pixels = list(cropped_image.convert("RGB").getdata())
    if not pixels:
        return None

    color_counts = Counter(pixels)
    most_common = color_counts.most_common(1)[0][0]
    return most_common


def _bucket_color(rgb):
    """
    Agrupa cores em baldes simples (vermelho, rosa, cinza_claro, cinza_escuro, etc.).
    Ainda não atribui significado operacional (BHT, extra, saída de noite, ...).
    """
    if rgb is None:
        return None

    r, g, b = rgb

    # Muito próximo de branco: ignorar
    if r > 240 and g > 240 and b > 240:
        return None

    def in_range(x, center, tol=6):
        return center - tol <= x <= center + tol

    # Vermelho forte (ex.: BHT)
    if in_range(r, 255) and in_range(g, 0) and in_range(b, 0):
        return "red"

    # Rosa claro (ex.: trabalho extra / troca, a confirmar)
    if in_range(r, 255) and in_range(g, 192) and in_range(b, 192):
        return "pink"

    # Cinzas (dois tons diferentes)
    if in_range(r, 169) and in_range(g, 169) and in_range(b, 169):
        return "gray_light"

    if in_range(r, 128) and in_range(g, 128) and in_range(b, 128):
        return "gray_dark"

    # Verde-lima (ferias/licenças/marcadores de ausência neste PDF)
    if in_range(r, 173) and in_range(g, 255) and in_range(b, 47):
        return "lime"

    # Cabeçalhos / blocos informativos (podemos ignorar na lógica de turnos)
    if in_range(r, 78) and in_range(g, 177) and in_range(b, 6):
        return "green_header"

    if in_range(r, 173) and in_range(g, 216) and in_range(b, 230):
        return "blue_header"

    # Outras cores (inclui futuros amarelos puros, etc.)
    return "other"


def parse_pdf(pdf_path, year, month):
    """
    Lê o PDF da escala e devolve uma lista de dicts com:
    - employee, name, date, code
    - color_rgb (tuple) e color_bucket (string simples ou None)
    """

    shifts = []

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]

        # Tentar usar detecção de tabelas (para termos as caixas das células)
        tables = page.find_tables()
        if not tables:
            # Fallback para a lógica antiga, sem cores
            table = page.extract_table()
            for row in table or []:
                if not row:
                    continue

                employee = row[0]
                name = row[1]

                if not employee or not name:
                    continue

                for i in range(2, len(row)):
                    code = row[i]
                    if not code:
                        continue
                    if code not in VALID_SHIFT_CODES:
                        continue

                    shifts.append(
                        {
                            "employee": employee,
                            "name": name,
                            "date": date(year, month, i - 1),
                            "code": code,
                            "color_rgb": None,
                            "color_bucket": None,
                        }
                    )

            return shifts

        table = tables[0]
        extracted_table = table.extract()
        page_image = page.to_image().original

        for row_idx, row in enumerate(extracted_table):
            if not row:
                continue

            employee = row[0]
            name = row[1] if len(row) > 1 else None

            if not employee or not name:
                continue

            # percorrer dias do mês (colunas a partir do índice 2)
            for i in range(2, len(row)):
                code = row[i]
                if not code:
                    continue
                if code not in VALID_SHIFT_CODES:
                    continue

                # Obter a caixa da célula correspondente
                try:
                    cell_box = table.rows[row_idx].cells[i]
                except (IndexError, AttributeError):
                    cell_box = None

                rgb = _get_cell_color(page_image, cell_box)
                bucket = _bucket_color(rgb)

                shifts.append(
                    {
                        "employee": employee,
                        "name": name,
                        "date": date(year, month, i - 1),
                        "code": code,
                        "color_rgb": rgb,
                        "color_bucket": bucket,
                    }
                )

    return shifts
