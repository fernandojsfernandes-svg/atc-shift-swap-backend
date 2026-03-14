# Deploy online (Render + Vercel)

Guia para colocar a app no ar com **backend no Render** (com PostgreSQL) e **frontend na Vercel**, tudo em modo gratuito na primeira fase.

---

## 1. Pré-requisitos

- Conta em [Render](https://render.com) e [Vercel](https://vercel.com) (login com GitHub).
- Código num repositório **GitHub** (Render e Vercel fazem deploy a partir do repo).

---

## 2. Backend no Render

### 2.1 Base de dados PostgreSQL

1. No dashboard do Render: **New** → **PostgreSQL**.
2. Nome: por exemplo `parser-escalas-db`.
3. Região: escolher a mais próxima.
4. Plano: **Free**.
5. Criar. Quando estiver **Available**, abre a base de dados.
6. Em **Connections** copia o **Internal Database URL** (usa para o backend no mesmo Render) ou **External Database URL** (se o backend estiver noutro sítio). O URL é do tipo `postgresql://user:pass@host/dbname`.

### 2.2 Serviço Web (API)

1. **New** → **Web Service**.
2. Liga o repositório GitHub e escolhe o projeto (ex.: `atc-shift-swap-backend`).
3. Configuração:
   - **Root Directory:** deixar **em branco** (a raiz do repo já é o backend; o `main.py` está na raiz).
   - **Runtime:** Python 3.
   - **Build Command:**  
     `pip install -r requirements.txt`
   - **Start Command:**  
     `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Environment** (variáveis de ambiente) – **Add**:
   - `DATABASE_URL` = (colar o Internal Database URL do passo 2.1).
   - `SECRET_KEY` = (uma string aleatória longa, ex.: gerada em https://randomkeygen.com/).
   - `FRONTEND_URL` = (ainda não tens; depois de fazer o frontend na Vercel, voltas aqui e pões ex.: `https://parser-escalas.vercel.app`).
5. **Create Web Service**. O Render faz o build e deploy. Anota o URL do serviço (ex.: `https://parser-escalas-api.onrender.com`).

### 2.3 CORS depois do frontend estar no ar

Quando tiveres o URL do frontend na Vercel, volta ao Web Service no Render → **Environment** e adiciona/edita:
- `FRONTEND_URL` = `https://teu-projeto.vercel.app` (sem barra no fim).

---

## 3. Frontend na Vercel

1. Em [Vercel](https://vercel.com): **Add New** → **Project** e importa o mesmo repositório GitHub.
2. Configuração:
   - **Root Directory:** `frontend/frontend` (pasta onde está o `package.json` do Vite; no repo o backend está na raiz e o frontend em `frontend/frontend/`).
   - **Framework Preset:** Vite.
   - **Build Command:** `npm run build` (já vem por defeito).
   - **Output Directory:** `dist` (já vem por defeito).
3. **Environment Variables** – **Add**:
   - **Name:** `VITE_API_URL`  
   - **Value:** `https://parser-escalas-api.onrender.com` (o URL do teu Web Service no Render, **sem** barra no fim).
4. **Deploy**. Quando terminar, tens um URL tipo `https://parser-escalas-xxx.vercel.app`.

---

## 4. Ligar frontend ao backend

1. No **Render**, no teu Web Service → **Environment**:  
   - `FRONTEND_URL` = `https://parser-escalas-xxx.vercel.app` (o URL que a Vercel te deu).
2. **Save Changes** (o Render faz redeploy).

A partir daí, ao abrires o URL da Vercel no browser, a app chama a API no Render e o CORS permite porque `FRONTEND_URL` está configurado.

---

## 5. Importar escalas em produção

O botão **Importar escalas** no frontend chama `POST /import/schedules`. Esse endpoint lê PDFs das pastas `PDF_FOLDER_ATUAL` e `PDF_FOLDER_SEGUINTE`. No Render **não tens ficheiros locais**; essas pastas não existem no servidor.

Opções:

- **A)** Desativar ou esconder o botão "Importar escalas" em produção e importar dados **uma vez** a partir do teu PC (script que chama a API com os PDFs ou que insere dados na BD). Não está implementado neste guia.
- **B)** Usar um serviço de ficheiros (ex.: S3, bucket) e configurar `PDF_FOLDER_ATUAL` / `PDF_FOLDER_SEGUINTE` para um caminho acessível no servidor (exige mais alterações no código).
- **C)** Para testes iniciais: importar em local (com PDFs), exportar a BD SQLite e importar esses dados para o PostgreSQL no Render (ferramentas de migração ou scripts ad‑hoc).

Para a **primeira fase** muitas vezes usa-se (A) ou (C) e só depois se automatiza o import em produção.

---

## 6. Variáveis de ambiente – resumo

| Onde      | Variável       | Exemplo / Notas |
|----------|----------------|------------------|
| Render   | `DATABASE_URL` | URL PostgreSQL (Internal) |
| Render   | `SECRET_KEY`   | String aleatória longa |
| Render   | `FRONTEND_URL` | `https://teu-app.vercel.app` |
| Vercel   | `VITE_API_URL` | `https://teu-api.onrender.com` |

---

## 7. Notas

- **Render (free):** o Web Service “adormece” após ~15 min sem pedidos; o primeiro pedido após isso pode demorar 30–60 s.
- **PostgreSQL (free) no Render:** a base pode ser apagada após 90 dias sem uso; o Render avisa.
- **JWT:** em produção usa sempre um `SECRET_KEY` forte e único, nunca o valor de desenvolvimento.
