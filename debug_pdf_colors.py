import sys
from collections import Counter

import pdfplumber


def get_cell_color(image, cell):
    """
    Recebe a imagem da página e a caixa da célula (x0, top, x1, bottom).
    Devolve a cor RGB mais frequente dentro da célula.
    """
    if not cell:
        return None

    # cell é um tuple (x0, top, x1, bottom)
    cropped_image = image.crop(cell)
    pixels = list(cropped_image.convert("RGB").getdata())
    if not pixels:
        return None

    color_counts = Counter(pixels)
    most_common = color_counts.most_common(1)[0][0]
    return most_common


def demo(pdf_path):
    """
    Abre o PDF, olha para a 1.ª página e imprime
    as células cuja cor de fundo não é branca.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        page_image = page.to_image().original
        tables = page.find_tables()

        if not tables:
            print("Não foram encontradas tabelas na 1.ª página.")
            return

        for t_index, table in enumerate(tables):
            extracted_table = table.extract()
            print(f"\n--- Tabela {t_index} ---")

            for row_idx, row in enumerate(table.rows):
                for col_idx, cell_box in enumerate(row.cells):
                    cell_color = get_cell_color(page_image, cell_box)
                    if cell_color is None:
                        continue

                    # Ignorar fundo (quase) branco
                    r, g, b = cell_color
                    if (r, g, b) == (255, 255, 255):
                        continue

                    text = extracted_table[row_idx][col_idx]
                    print(
                        f"linha={row_idx}, coluna={col_idx}, texto={text!r}, "
                        f"cor RGB={cell_color}"
                    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python debug_pdf_colors.py CAMINHO_PARA_PDF")
        sys.exit(1)

    pdf_path = sys.argv[1]
    demo(pdf_path)

