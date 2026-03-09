from parsers.schedule_parser import parse_schedule_pdf

shifts = parse_schedule_pdf("C:/PARSER_ESCALAS/PDF_Escalas/ROTA-E_2026_03.pdf")

for s in shifts:
    print(s)