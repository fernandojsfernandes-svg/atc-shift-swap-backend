# Lista: colocar a beta online

Segue por ordem. Marca `[x]` quando concluído.

---

## 0. Antes de começar

- [ ] Código no **Git** (GitHub/GitLab/Bitbucket) com o último `push`.
- [ ] Conta em **Render** (https://render.com) e, se usares frontend estático, **Vercel** (https://vercel.com) ou outro.

---

## 1. Base de dados PostgreSQL (Render)

- [ ] No Render: **New** → **PostgreSQL** (nome, região, plano).
- [ ] Depois de criada, abre a base → copia **Internal Database URL** (começa por `postgresql://...`).  
  → Vais usar no passo 3 como `DATABASE_URL`.

---

## 2. Repositório e pasta no Render

- [ ] **New** → **Web Service** → liga o repositório Git.
- [ ] **Root Directory:** se o repo tiver só `backend_min` na raiz, deixa vazio **ou** aponta para a pasta onde está `main.py` e `requirements.txt`.
- [ ] **Runtime:** Python 3.
- [ ] **Build command:** `pip install -r requirements.txt`
- [ ] **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## 3. Variáveis de ambiente (backend no Render)

Na página **Environment** do Web Service, adiciona (ajusta valores):

| Variável | Valor / notas |
|----------|----------------|
| `DATABASE_URL` | Cola a Internal URL do PostgreSQL (passo 1). |
| `SECRET_KEY` | String longa e aleatória (JWT). |
| `PYTHON_VERSION` | `3.11.0` (ou a versão que o Render sugerir). |
| `FRONTEND_URL` | **Depois** do passo 8: URL exata do site (ex. `https://xxx.vercel.app`). Podes adicionar já um placeholder e corrigir no fim. |
| `PDF_FOLDER_ATUAL` | Se usares disco: `/var/data/pdf_escalas/atual` (ver passo 4). |
| `PDF_FOLDER_SEGUINTE` | `/var/data/pdf_escalas/seguinte` |
| `CLEAR_SCHEDULES_SECRET` | (Opcional) Segredo para `POST /import/clear-schedules`. |

- [ ] Variáveis guardadas → **Manual Deploy** ou espera o deploy automático.

---

## 4. Disco para PDF (opcional mas recomendado para import no servidor)

- [ ] No Web Service → **Disks** → **Add Disk** → mount path: `/var/data/pdf_escalas` (tamanho, ex. 1 GB — pode ser plano pago).
- [ ] **Render Shell** (se disponível no teu plano) e executa:  
  `sh scripts/render-mkdir-pdf-dirs.sh`  
  ou:  
  `mkdir -p /var/data/pdf_escalas/atual /var/data/pdf_escalas/seguinte`
- [ ] Copia os **PDF** para `atual` e `seguinte` (wget/scp conforme `DEPLOY_BETA_LIMPO.md`).

Se **não** usares disco ainda, o import só funciona quando tiveres PDF acessíveis nesses caminhos no servidor.

---

## 5. Primeiro teste da API

- [ ] Abre `https://<nome-do-teu-servico>.onrender.com/` — deve responder JSON com mensagem da API.
- [ ] Abre `https://<...>/docs` — Swagger deve carregar.

---

## 6. Limpar (se a base já tinha lixo de testes) e importar escalas

Só depois dos PDF estarem no servidor e das variáveis `PDF_FOLDER_*` corretas.

- [ ] `POST /import/clear-schedules` com body `{"confirm":"APAGAR_TODAS_AS_ESCALAS"}` (+ header se usares `CLEAR_SCHEDULES_SECRET`).
- [ ] `POST /import/schedules`

No Windows (na pasta `backend_min`):

```powershell
.\scripts\beta-clear-and-import.ps1 -ApiBase "https://<teu-api>.onrender.com" -ClearSchedulesSecret "SE_USARES"
```

- [ ] Confirma em `/docs` um `GET` de escalas (ex. schedules) que os dados batem certo.

---

## 7. CORS

- [ ] `FRONTEND_URL` = URL **exata** do frontend (com `https://`, sem barra no fim).
- [ ] Se usares preview Vercel extra: `CORS_EXTRA_ORIGINS` com esse URL.
- [ ] **Save** → redeploy se necessário.

---

## 8. Frontend (ex.: Vercel)

- [ ] **New Project** → importa o **mesmo** repo.
- [ ] **Root Directory:** `frontend/frontend` (onde está o `package.json` do Vite).
- [ ] **Framework:** Vite (ou “Other” com `npm run build` / output `dist`).
- [ ] **Environment Variables** (build):  
  `VITE_API_URL` = `https://<teu-api>.onrender.com` **sem barra final**.

- [ ] Deploy → abre o URL do Vercel e testa login / escalas.

---

## 9. Fecho

- [ ] Volta ao Render (backend) e confirma que `FRONTEND_URL` é o URL final do Vercel.
- [ ] Testa no browser: login, carregar escala, uma ação de troca se aplicável.

---

## Documentação de apoio

- `DEPLOY_BETA_LIMPO.md` — detalhe PDF, disco, curl.
- `render.yaml.example` — blueprint Render com disco (opcional).
- `.env.example` — modelo de variáveis.

Se algo falhar num passo, anota a **mensagem de erro** e o **número do passo** — assim dá para corrigir de forma objetiva.
