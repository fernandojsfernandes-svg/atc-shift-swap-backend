# Passo a passo: beta online (Render + Vercel)

Guia detalhado para quem nunca usou Render/Vercel. Reserva **~1–2 h** na primeira vez (esperas de deploy incluídos).

---

## Fase A — Código no Git

1. Abre uma consola na pasta do projeto (a que tem `backend_min` ou a raiz do repo).
2. Confirma o estado:
   ```bash
   git status
   ```
3. Se houver alterações por commitar:
   ```bash
   git add .
   git commit -m "Preparar deploy beta"
   git push
   ```
4. Se ainda **não** tens repositório remoto: cria um repositório vazio no **GitHub** → segue as instruções “push an existing repository”.

**Checkpoint:** no GitHub vês os ficheiros (`main.py`, `frontend/frontend/`, etc.).

---

## Fase B — Conta Render e base PostgreSQL

1. Vai a https://render.com → regista-te ou inicia sessão.
2. No dashboard: botão **New +** → **PostgreSQL**.
3. Preenche:
   - **Name:** ex. `atc-escalas-db`
   - **Region:** escolhe a mais próxima (ex. Frankfurt).
   - **PostgreSQL Version:** a que o Render sugerir (15+).
   - **Plan:** o gratuito ou pago conforme o teu caso.
4. Cria a base (**Create Database**).
5. Quando estiver **Available**, abre a base → secção **Connections**.
6. Copia **Internal Database URL** (começa por `postgresql://` ou `postgres://`).  
   **Guarda** num bloco de notas — é o `DATABASE_URL`.

**Checkpoint:** tens um URL longo copiado (não partilhes publicamente).

---

## Fase C — Backend (Web Service) no Render

1. **New +** → **Web Service** (não “Static Site”).
2. **Connect** o repositório GitHub e autoriza o Render se pedir.
3. Escolhe o **repositório** e o **branch** (geralmente `main`).
4. Preenche o formulário:

| Campo | Valor |
|--------|--------|
| **Name** | ex. `atc-shift-swap-api` |
| **Region** | Igual ou próxima da base de dados. |
| **Root Directory** | Se no GitHub a raiz **já é** `backend_min` (com `main.py` dentro), deixa **vazio**. Se o repo tiver pasta `backend_min/` dentro de outra raiz, escreve: `backend_min` |
| **Runtime** | **Python 3** |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

5. Escolhe o **plano** (Free pode “dormir” após inatividade — para beta pode servir).
6. **Advanced** → **Add Environment Variable** (podes adicionar já ou no passo seguinte):

| Key | Value |
|-----|--------|
| `DATABASE_URL` | Cola o **Internal Database URL** da Fase B (inteiro). |
| `SECRET_KEY` | Uma frase longa aleatória (ex. 40+ caracteres). Podes gerar: PowerShell `[guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()` |
| `PYTHON_VERSION` | `3.11.0` |

7. **Create Web Service** — o primeiro deploy demora vários minutos.

**Erro comum:** “Build failed” → verifica **Root Directory** (tem de ser a pasta onde está `requirements.txt`).

**Checkpoint:** nos **Logs** vês algo como `Uvicorn running` e `Application startup complete`.

---

## Fase D — URL da API e teste

1. No topo da página do serviço vês o URL: `https://XXXX.onrender.com`
2. Abre no browser: `https://XXXX.onrender.com/` → deve aparecer JSON tipo `{"message":"ATC Shift Swap API",...}`
3. Abre `https://XXXX.onrender.com/docs` → Swagger.

**Checkpoint:** `/docs` abre.

---

## Fase E — Disco PDF (quando quiseres import no servidor)

> Plano **Free** do Web Service **pode não ter** Persistent Disk. Se não adicionares disco, o import no servidor só funciona se conseguires noutro caminho (avançado). Para a maioria: **upgrade** ou plano que permita **Disk**.

1. Web Service → **Disks** → **Add Disk**
2. **Name:** `pdf-escalas`
3. **Mount Path:** `/var/data/pdf_escalas`
4. **Size:** ex. 1 GB
5. Guarda → pode pedir **redeploy**
6. **Environment** → confirma:
   - `PDF_FOLDER_ATUAL` = `/var/data/pdf_escalas/atual`
   - `PDF_FOLDER_SEGUINTE` = `/var/data/pdf_escalas/seguinte`
7. **Shell** (se existir no plano) e executa:
   ```sh
   mkdir -p /var/data/pdf_escalas/atual /var/data/pdf_escalas/seguinte
   ```
8. Coloca os ficheiros **.pdf** nas pastas (métodos em `DEPLOY_BETA_LIMPO.md`).

---

## Fase F — Limpar e importar escalas

Só quando os PDF já estão no servidor.

1. No PC, na pasta `backend_min`:
   ```powershell
   .\scripts\beta-clear-and-import.ps1 -ApiBase "https://XXXX.onrender.com"
   ```
   Se definiste `CLEAR_SCHEDULES_SECRET` no Render, adiciona:  
   `-ClearSchedulesSecret "o_mesmo_valor"`

2. Ou no Swagger `/docs`: **Try it out** em `POST /import/clear-schedules` e depois `POST /import/schedules`.

**Checkpoint:** resposta JSON com `Schedules imported` ou lista de equipas.

---

## Fase G — Frontend na Vercel

1. https://vercel.com → **Sign up** / login (podes usar “Continue with GitHub”).
2. **Add New** → **Project** → importa o **mesmo** repositório.
3. **Configure Project:**
   - **Root Directory:** `frontend/frontend` (clica **Edit** e escreve exatamente isto).
   - **Framework Preset:** Vite (deteta sozinho muitas vezes).
   - **Build Command:** `npm run build` (por defeito).
   - **Output Directory:** `dist`
4. **Environment Variables** → **Add**:
   - **Name:** `VITE_API_URL`
   - **Value:** `https://XXXX.onrender.com` (o URL da API **sem** barra no fim)
5. **Deploy**

**Checkpoint:** a Vercel dá um URL tipo `https://yyy.vercel.app` — abre e testa a app.

---

## Fase H — CORS (ligar frontend à API)

1. Render → Web Service → **Environment**
2. Adiciona ou edita:
   - **FRONTEND_URL** = `https://yyy.vercel.app` (URL **exato** do passo G, `https://`, **sem** `/` no fim)
3. **Save** → espera redeploy automático ou **Manual Deploy**

**Checkpoint:** no site Vercel, login e pedidos à API já não dão erro de CORS no consola do browser (F12 → Network).

---

## Se algo falhar

| Sintoma | Onde olhar |
|---------|------------|
| Build falha no Render | Logs do build; **Root Directory**; `requirements.txt` |
| 502 / serviço a dormir (Free) | Primeiro pedido após minutos parado pode demorar |
| CORS no browser | `FRONTEND_URL` exatamente igual ao site Vercel; HTTPS |
| Import sem PDF | Disco montado, pastas criadas, PDF com nomes `A_2026_3.pdf` etc. |
| Login falha | Utilizadores criados pelo import; `SECRET_KEY` não mudar entre deploys se já há tokens |

---

## Ordem mínima sem disco (só API a responder)

A + B + C + D — já tens API online. Disco + import (E + F) quando tiveres PDF no servidor. G + H quando tiveres frontend.

Documentos relacionados: `CHECKLIST_DEPLOY.md`, `DEPLOY_BETA_LIMPO.md`.
