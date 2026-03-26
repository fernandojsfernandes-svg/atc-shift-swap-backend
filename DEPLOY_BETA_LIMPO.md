# Beta online: base “limpa” e import das escalas atuais

Este guia descreve como deixar o ambiente de **testes online** sem dados antigos de escalas/trocas e voltar a carregar só as **escalas atuais** a partir dos PDF.

## O que fica e o que é apagado

| Mantém | Remove |
|--------|--------|
| Utilizadores (`users`) | Turnos (`shifts`), escalas mensais (`monthly_schedules`) |
| Equipas (`teams`), tipos de turno (`shift_types`) | Pedidos de troca, notificações, histórico de trocas, ciclos, etc. |

Ou seja: **limpa tudo o que é escala importada e tudo o que depende de turnos**, para poderes fazer um **import limpo** com os PDF correntes.

## Pré-requisitos no servidor (beta)

1. **Base de dados** PostgreSQL (ou outra) já configurada em `DATABASE_URL`.
2. **PDF no servidor** — o import corre **no backend**: as pastas `PDF_FOLDER_ATUAL` e `PDF_FOLDER_SEGUINTE` têm de existir **no disco do host** e conter os ficheiros (ex.: `A_2026_3.pdf`).  
   - No Windows local usas por defeito `C:/PARSER_ESCALAS/PDF_Escalas/...`.  
   - Na nuvem (Render, Railway, VPS) define variáveis com **caminhos Linux**, por exemplo `/var/data/pdf_escalas/atual`, e coloca lá os PDF (upload, volume, deploy com ficheiros, etc.).
3. **CORS** — `FRONTEND_URL` (e se precisares `CORS_EXTRA_ORIGINS`) já apontam para o site da beta.
4. **Proteger a limpeza em produção** — define `CLEAR_SCHEDULES_SECRET` no painel do host e usa o mesmo valor no header `X-Clear-Schedules-Secret` ao chamar a API (ver abaixo).

## Render.com: disco persistente e pastas PDF

No **plano gratuito** o sistema de ficheiros do serviço é **efémero**: ficheiros que não estão no disco persistente perdem-se em cada *deploy*. Para guardar os PDF entre *deploys*, usa um **Persistent Disk**.

### Caminhos alinhados (recomendados)

| O quê | Valor |
|--------|--------|
| Montagem do disco | `/var/data/pdf_escalas` |
| Mês atual (PDF) | `/var/data/pdf_escalas/atual` |
| Mês seguinte (PDF) | `/var/data/pdf_escalas/seguinte` |
| Variável `PDF_FOLDER_ATUAL` | `/var/data/pdf_escalas/atual` |
| Variável `PDF_FOLDER_SEGUINTE` | `/var/data/pdf_escalas/seguinte` |

### Passos no painel Render

1. **Web Service** do backend → **Disks** → **Add Disk**.  
2. **Mount path**: `/var/data/pdf_escalas` (nome interno do disco, ex. `pdf-escalas`; tamanho, ex. 1 GB — disco pago em muitos planos).  
3. **Environment** do mesmo serviço → adiciona (ou confirma):
   - `PDF_FOLDER_ATUAL` = `/var/data/pdf_escalas/atual`
   - `PDF_FOLDER_SEGUINTE` = `/var/data/pdf_escalas/seguinte`
4. **Redeploy** para aplicar o disco (se o Render pedir).

### Criar subpastas `atual` e `seguinte`

No primeiro arranque o disco pode estar vazio. Abre **Render Shell** (ou SSH, conforme o plano) no serviço e executa:

```sh
sh scripts/render-mkdir-pdf-dirs.sh
```

Ou manualmente:

```sh
mkdir -p /var/data/pdf_escalas/atual /var/data/pdf_escalas/seguinte
```

### Colocar os ficheiros PDF no servidor

O import lê ficheiros `*.pdf` dessas pastas (nomes esperados: `{equipa}_{ano}_{mes}.pdf`). Opções práticas:

1. **URL temporária** — aloja um zip ou os PDF num sítio com link direto e, no Shell, `wget`/`curl` para `/var/data/pdf_escalas/atual/` (e idem para `seguinte`).  
2. **Máquina com acesso** — se o plano tiver **SSH**, `scp` a partir do teu PC.  
3. **Repositório** — só para ficheiros pequenos e não sensíveis: copiar PDF para uma pasta do repo e um *build* que os copia para o disco (mais trabalhoso; o habitual é disco + upload manual).

Depois de os PDF estarem no sítio certo, chama `POST /import/schedules` (Passo 2 abaixo).

### Blueprint YAML

Na raiz do projeto existe `render.yaml.example` com o disco e as variáveis `PDF_FOLDER_*` já alinhadas. Podes copiar para `render.yaml` e ajustar o nome do serviço / `rootDir` se o Git tiver monorepo.

## Passo 1 — Limpar escalas e dados de trocas

`POST` para `{API_URL}/import/clear-schedules` com corpo JSON:

```json
{
  "confirm": "APAGAR_TODAS_AS_ESCALAS"
}
```

- Se `CLEAR_SCHEDULES_SECRET` estiver definido no ambiente, envia também o header:  
  `X-Clear-Schedules-Secret: <o mesmo valor>`.

**Exemplo com curl** (substitui `https://teu-api.onrender.com`):

```bash
curl -sS -X POST "https://teu-api.onrender.com/import/clear-schedules" \
  -H "Content-Type: application/json" \
  -H "X-Clear-Schedules-Secret: O_TEU_SEGREDO" \
  -d "{\"confirm\":\"APAGAR_TODAS_AS_ESCALAS\"}"
```

Sem segredo configurado, omite o header `-H "X-Clear-Schedules-Secret:..."`.

## Passo 2 — Importar as escalas atuais

Garante que os PDF estão nas pastas configuradas (`PDF_FOLDER_ATUAL` / `PDF_FOLDER_SEGUINTE`). Depois:

`POST` para `{API_URL}/import/schedules` (sem body).

```bash
curl -sS -X POST "https://teu-api.onrender.com/import/schedules"
```

A resposta JSON indica equipas processadas, avisos e ficheiros ignorados.

## Passo 3 — Verificar

- Abre `/docs` no mesmo URL da API e testa `GET /schedules/...` ou usa o frontend da beta.
- Confirma logins com números de funcionário que existam após o import.

## Script PowerShell (Windows)

Na pasta `backend_min/scripts/` existe `beta-clear-and-import.ps1`:

```powershell
.\scripts\beta-clear-and-import.ps1 -ApiBase "https://teu-api.onrender.com" -ClearSchedulesSecret "O_TEU_SEGREDO"
```

Se não usares segredo, omite `-ClearSchedulesSecret`.

## Ordem recomendada para um deploy “novo”

1. Deploy do backend com `DATABASE_URL` vazio ou base nova → as tabelas criam-se com `create_all` ao arrancar.
2. (Opcional) Se já havia dados de teste na mesma base: executar **Passo 1** (limpar).
3. Colocar os PDF atuais nas pastas do servidor e definir `PDF_FOLDER_*`.
4. Executar **Passo 2** (import).
5. Deploy do frontend com `VITE_API_URL` apontando para esta API.

## Nota sobre utilizadores

O import **cria ou atualiza** utilizadores a partir dos PDF (por `employee_number`). Se precisares de passwords conhecidas para testes, isso é gestão de utilizadores à parte (ou fluxo futuro de convites).
