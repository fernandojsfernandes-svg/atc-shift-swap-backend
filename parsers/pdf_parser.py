import pdfplumber
from datetime import date
from collections import Counter
import re
import unicodedata


# Aceitar qualquer código curto alfanumérico (domínios ATC).
# Exemplos: "M", "T", "N", "MG", "Mt", "DC", "DS", "IB", "MT", "TR", "A1", "T2".
# Não normalizamos case: "MT" != "Mt" (importante para regras futuras).
SHIFT_CODE_RE = re.compile(r"^[A-Za-z]{1,3}\d{0,2}$")

def _normalize_pdf_shift_code(code) -> str:
    """
    Normaliza o texto extraído do PDF.
    - Remove whitespace interior (ex.: "I B" -> "IB")
    - Mantém case (MT vs Mt são códigos distintos no teu domínio).
    """
    c = (str(code) if code is not None else "").strip()
    # junta tokens para lidar com "I B" ou "M t"
    c = "".join(c.split())
    return c


def _is_shift_code(code: str) -> bool:
    if not code:
        return False
    return SHIFT_CODE_RE.match(code) is not None


def _normalize_text_for_match(text: str) -> str:
    """Lower + sem acentos para comparações robustas de cabeçalhos/secções."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t.lower()


def _is_qualification_section_row(row) -> bool:
    """
    True se a linha indicar o início da secção "Em qualificação".
    Regra do negócio: essa linha e as seguintes não devem ser processadas.
    """
    if not row:
        return False
    probe = " ".join((str(c) if c is not None else "") for c in row[:5]).strip()
    if not probe:
        return False
    p = _normalize_text_for_match(probe)
    return "em qualificacao" in p


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

    def in_range(x, center, tol=6):
        return center - tol <= x <= center + tol

    # Vermelho forte (ex.: BHT)
    if in_range(r, 255) and in_range(g, 0) and in_range(b, 0):
        return "red"

    # Rosa claro (ex.: mudança de funções)
    # Nota: esta deteção tem de vir antes do filtro "quase branco",
    # caso contrário RGB como (255,192,192) seria descartado.
    if in_range(r, 255) and in_range(g, 192) and in_range(b, 192):
        return "pink"

    # Muito próximo de branco: ignorar (rotação base)
    if r > 240 and g > 240 and b > 240:
        return None

    # Cinza claro / tom claro (ex.: Abril com tons ligeiramente diferentes): tratar como rotação
    # Só consideramos "troca" (gray_light/gray_dark) para cinzas mais escuros (~169 e ~128)
    if r > 175 and g > 175 and b > 175:
        return None

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


def _employee_and_name(col0, col1):
    """
    Determina qual célula é número de funcionário e qual é nome.
    Em alguns PDFs (ex.: equipas D e E) a ordem pode ser (nome, número) em vez de (número, nome).
    Se uma célula for só dígitos e a outra não, usamos a de dígitos como employee.
    """
    a = (col0 or "").strip()
    b = (col1 or "").strip() if col1 is not None else ""
    if not a or not b:
        return None, None
    a_digit = a.isdigit()
    b_digit = b.isdigit()
    if a_digit and not b_digit:
        return a, b
    if b_digit and not a_digit:
        return b, a
    return a, b  # default: primeira col = employee, segunda = name


def _employee_and_name_from_row(row, max_cols=4):
    """
    Procura número de funcionário e nome nas primeiras colunas da linha.
    Útil quando o PDF tem coluna extra (ex.: col 0 vazia, número na col 1, nome na col 2).
    Devolve (employee, name, day_start) onde day_start é o índice da primeira coluna de dias.
    """
    candidates = []
    last_used_idx = -1
    for i in range(min(max_cols, len(row))):
        c = (row[i] or "").strip()
        if c:
            candidates.append(c)
            last_used_idx = i
    if len(candidates) < 2:
        return None, None, 2
    employee = next((c for c in candidates if c.isdigit()), None)
    name = next((c for c in candidates if not c.isdigit()), None)
    day_start = last_used_idx + 1 if last_used_idx >= 0 else 2
    return employee, name, day_start


def _process_page_fallback(page, year, month, shifts):
    """Fallback sem deteção de tabelas: extrai texto e preenche shifts (sem cores)."""
    table = page.extract_table()
    for row in table or []:
        if not row:
            continue
        if _is_qualification_section_row(row):
            break
        employee, name = _employee_and_name(row[0], row[1] if len(row) > 1 else None)
        day_start = 2
        if not employee or not name:
            employee, name, day_start = _employee_and_name_from_row(row)
        if not employee or not name:
            continue
        for i in range(day_start, len(row)):
            code = _normalize_pdf_shift_code(row[i])
            if not _is_shift_code(code):
                continue
            try:
                day = i - day_start + 1
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
            base_code = _normalize_pdf_shift_code(base_code)
            if _is_shift_code(base_code):
                base_codes[i] = base_code
    for row_idx, row in enumerate(extracted_table):
        if not row or row_idx == 0:
            continue
        if _is_qualification_section_row(row):
            break
        employee, name = _employee_and_name(row[0], row[1] if len(row) > 1 else None)
        day_start = 2
        if not employee or not name:
            employee, name, day_start = _employee_and_name_from_row(row)
        if not employee or not name:
            continue
        for i in range(day_start, len(row)):
            cell_value = row[i]
            if not cell_value:
                base_code = base_codes.get(i)
                if not base_code:
                    continue
                code = base_code
            else:
                code = _normalize_pdf_shift_code(cell_value)
            if not _is_shift_code(code):
                continue
            try:
                day = i - day_start + 1
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


def detect_schedule_month_year_from_pdf(pdf_path: str) -> tuple[int, int] | None:
    """
    Lê o texto da 1.ª página e tenta identificar mês + ano (cabeçalho típico «ABRIL 2026»).
    Usado para validar o nome do ficheiro (Equipa_ano_mês.pdf) contra o conteúdo real.
    Se o PDF for só imagem ou sem texto, devolve None (importação segue só com o nome).
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return None
            text_raw = pdf.pages[0].extract_text() or ""
    except Exception:
        return None
    if not text_raw.strip():
        return None
    t = _normalize_text_for_match(text_raw)
    # Ordem: "marco" cobre MARÇO/MARCO após normalização
    month_order = [
        ("janeiro", 1),
        ("fevereiro", 2),
        ("marco", 3),
        ("abril", 4),
        ("maio", 5),
        ("junho", 6),
        ("julho", 7),
        ("agosto", 8),
        ("setembro", 9),
        ("outubro", 10),
        ("novembro", 11),
        ("dezembro", 12),
    ]
    earliest: int | None = None
    best_month: int | None = None
    for name, num in month_order:
        pos = t.find(name)
        if pos != -1 and (earliest is None or pos < earliest):
            earliest = pos
            best_month = num
    if best_month is None:
        return None
    m = re.search(r"20\d{2}", text_raw)
    if not m:
        return None
    return int(m.group()), best_month


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
