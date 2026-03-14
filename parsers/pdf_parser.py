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

    # Muito próximo de branco: ignorar (rotação base)
    if r > 240 and g > 240 and b > 240:
        return None

    # Cinza claro / tom claro (ex.: Abril com tons ligeiramente diferentes): tratar como rotação
    # Só consideramos "troca" (gray_light/gray_dark) para cinzas mais escuros (~169 e ~128)
    if r > 175 and g > 175 and b > 175:
        return None

    def in_range(x, center, tol=6):
        return center - tol <= x <= center + tol

    # Vermelho forte (ex.: BHT)
    if in_range(r, 255) and in_range(g, 0) and in_range(b, 0):
        return "red"

    # Rosa claro (ex.: trabalho extra / troca, a confirmar)
    if in_range(r, 255) and in_range(g, 192) and in_range(b, 192):
        return "pink"

    # Cinzas (dois tons distintos; cinza claro ~169, escuro ~128)
    if in_range(r, 169) and in_range(g, 169) and in_range(b, 169):
        return "gray_light"

    if in_range(r, 128) and in_range(g, 128) and in_range(b, 128):
        return "gray_dark"

    # Verde-lima (ferias/licenças/marcadores de ausência neste PDF)
    if in_range(r, 173) and in_range(g, 255) and in_range(b, 47):
        return "lime"

    # Amarelo (trabalho suplementar / extraordinário – surge após o BHT vermelho)
    if r >= 200 and g >= 200 and b <= 230:
        return "yellow"

    # Cabeçalhos / blocos informativos (podemos ignorar na lógica de turnos)
    if in_range(r, 78) and in_range(g, 177) and in_range(b, 6):
        return "green_header"

    if in_range(r, 173) and in_range(g, 216) and in_range(b, 230):
        return "blue_header"

    # Outras cores (inclui futuros amarelos puros, etc.)
    return "other"


def _process_page_fallback(page, year, month, shifts):
    """Fallback sem deteção de tabelas: extrai texto e preenche shifts (sem cores)."""
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
            if not code or code not in VALID_SHIFT_CODES:
                continue
            try:
                day = i - 1
                if day < 1 or day > 31:
                    continue
                d = date(year, month, day)
            except ValueError:
                continue
            shifts.append({
                "employee": employee,
                "name": name,
                "date": d,
                "code": code,
                "color_rgb": None,
                "color_bucket": None,
            })


def _process_page_with_tables(page, year, month, shifts):
    """Processa uma página com deteção de tabelas (inclui cores)."""
    tables = page.find_tables()
    if not tables:
        _process_page_fallback(page, year, month, shifts)
        return
    table = tables[0]
    extracted_table = table.extract()
    page_image = page.to_image().original
    header_row = extracted_table[0] if extracted_table else None
    base_codes: dict[int, str] = {}
    if header_row:
        for i in range(2, len(header_row)):
            header_cell = header_row[i]
            if not header_cell:
                continue
            parts = str(header_cell).splitlines()
            if not parts:
                continue
            base_code = parts[-1].strip()
            if base_code in VALID_SHIFT_CODES:
                base_codes[i] = base_code
    for row_idx, row in enumerate(extracted_table):
        if not row or row_idx == 0:
            continue
        employee = row[0]
        name = row[1] if len(row) > 1 else None
        if not employee or not name:
            continue
        for i in range(2, len(row)):
            cell_value = row[i]
            if not cell_value:
                base_code = base_codes.get(i)
                if not base_code:
                    continue
                code = base_code
            else:
                code = cell_value
            if code not in VALID_SHIFT_CODES:
                continue
            try:
                day = i - 1
                if day < 1 or day > 31:
                    continue
                d = date(year, month, day)
            except ValueError:
                continue
            try:
                cell_box = table.rows[row_idx].cells[i]
            except (IndexError, AttributeError):
                cell_box = None
            rgb = _get_cell_color(page_image, cell_box)
            bucket = _bucket_color(rgb)
            shifts.append({
                "employee": employee,
                "name": name,
                "date": d,
                "code": code,
                "color_rgb": rgb,
                "color_bucket": bucket,
            })


def parse_pdf(pdf_path, year, month):
    """
    Lê o PDF da escala (todas as páginas) e devolve uma lista de dicts com:
    - employee, name, date, code
    - color_rgb (tuple) e color_bucket (string simples ou None)
    """
    shifts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            if tables:
                _process_page_with_tables(page, year, month, shifts)
            else:
                _process_page_fallback(page, year, month, shifts)
    return shifts
