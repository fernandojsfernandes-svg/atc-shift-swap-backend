# Deploy online – Passo a passo

Seguir por ordem. Quando disser "anota o URL", guarda num sítio (bloco de notas) para usar mais tarde.

---

## Fase 0 – Ter o código no GitHub

Neste projeto (Opção A), o repositório tem **backend na raiz** (main.py, database.py, etc.) e a pasta **`frontend/frontend`** com o Vite (package.json, src, etc.). Ou seja: na raiz está o backend; o frontend está em `frontend/frontend/`.

Se já tiveres o frontend no mesmo repo (como no atc-shift-swap-backend), podes saltar para a **Fase 1**. Caso contrário:

1. Cria um repositório no [GitHub](https://github.com) e faz push do código (backend + pasta frontend).
2. Confirma no GitHub que na raiz aparecem ficheiros como `main.py` e a pasta `frontend` (e dentro dela `frontend/package.json`).

---

## Fase 1 – Render (backend + base de dados)

### Passo 1.1 – Criar conta e base de dados

4. Abre [https://render.com](https://render.com) e faz login (pode ser com **GitHub**).
5. No dashboard, clica em **New +** e escolhe **PostgreSQL**.
6. Preenche:
   - **Name:** `parser-escalas-db` (ou outro nome).
   - **Region:** escolhe a mais próxima (ex.: Frankfurt).
   - **Plan:** **Free**.
7. Clica **Create Database**. Espera até o estado ficar **Available** (pode levar 1–2 minutos).
8. Clica no nome da base de dados que criaste. Na secção **Connections**:
   - Copia o **Internal Database URL** (começa por `postgresql://`).
   - **Anota este URL** (vais colá-lo no Passo 1.3). Guarda num sítio seguro; contém a palavra-passe.

### Passo 1.2 – Criar o serviço da API

9. No dashboard do Render, clica de novo em **New +** e escolhe **Web Service**.
10. Se te pedir para ligar o GitHub, autoriza e escolhe a conta/repositório onde está o projeto.
11. Escolhe o **repositório** do projeto (ex.: `atc-shift-swap-backend`).
12. Preenche:
    - **Name:** `parser-escalas-api` (ou outro nome; será parte do URL).
    - **Region:** a mesma que a base de dados.
    - **Branch:** `main` (ou a branch que usas).
    - **Root Directory:** deixa **em branco** (a raiz do repositório já é o backend – o `main.py` está na raiz).
    - **Runtime:** **Python 3**.
    - **Build Command:**  
      `pip install -r requirements.txt`
    - **Start Command:**  
      `uvicorn main:app --host 0.0.0.0 --port $PORT`
13. **Ainda não cliques em Create Web Service.** Primeiro vamos pôr as variáveis de ambiente.

### Passo 1.3 – Variáveis de ambiente no Render

14. Na mesma página, desce até **Environment** (ou **Environment Variables**).
15. Clica **Add Environment Variable** e adiciona **uma de cada vez**:

    | Key             | Value |
    |-----------------|--------|
    | `DATABASE_URL`  | Cola aqui o **Internal Database URL** que copiaste no Passo 1.1 (o que começa por `postgresql://`). |
    | `SECRET_KEY`    | Uma frase longa e aleatória. Ex.: abre [https://randomkeygen.com/](https://randomkeygen.com/) e copia uma "CodeIgniter Encryption Keys" ou escreve 40+ caracteres à sorte. |
    | `FRONTEND_URL`  | Por agora escreve **`https://placeholder.vercel.app`** (só para não deixar vazio; vamos trocar no Passo 2.4). |

16. Clica **Create Web Service**. O Render vai fazer o build e o deploy (pode demorar 2–5 minutos).
17. Quando terminar, no topo da página do serviço aparece o **URL** (ex.: `https://parser-escalas-api.onrender.com`). **Anota este URL** – é o URL da tua API.

### Passo 1.4 – Testar a API

18. Abre no browser: **`https://TEU-URL.onrender.com/docs`** (substitui pelo URL que anotaste). Deves ver a documentação Swagger da API. Se der erro, espera mais um pouco (o servidor free às vezes demora a acordar).

---

## Fase 2 – Vercel (frontend)

### Passo 2.1 – Criar projeto na Vercel

19. Abre [https://vercel.com](https://vercel.com) e faz login com **GitHub**.
20. Clica **Add New…** → **Project**.
21. Importa o **mesmo repositório** que usaste no Render (ex.: `atc-shift-swap-backend`). Se não aparecer, clica em **Configure GitHub** e autoriza a Vercel a ver os repositórios.
22. Depois de escolher o repo, na página de configuração do projeto:
    - **Project Name:** pode deixar o que vem ou mudar.
    - **Root Directory:** clica em **Edit** e escreve **`frontend/frontend`** (pasta onde está o `package.json` do Vite). No teu repo a estrutura é: raiz = backend, `frontend/frontend/package.json` = frontend.
    - **Framework Preset:** deve detetar **Vite**. Se não, escolhe **Vite**.
    - **Build Command:** deixa `npm run build`.
    - **Output Directory:** deixa `dist`.

### Passo 2.2 – Variável da API no frontend

23. Na mesma página, abre a secção **Environment Variables**.
24. **Name:** `VITE_API_URL`  
    **Value:** o URL da API do Render **sem barra no fim** (ex.: `https://parser-escalas-api.onrender.com`).  
    **Environment:** marca **Production** (e se quiseres também Preview).
25. Clica **Deploy**. A Vercel faz o build e o deploy (1–3 minutos).
26. No fim, aparece o URL do teu site (ex.: `https://parser-escalas-xxx.vercel.app`). **Anota este URL** – é o teu frontend.

### Passo 2.3 – Abrir o site

27. Abre no browser o URL que anotaste (ex.: `https://parser-escalas-xxx.vercel.app`). Deves ver a aplicação das escalas.  
28. Se ao carregar escalas der erro de rede ou CORS: falta ligar o frontend ao backend no Render (Passo 2.4).

### Passo 2.4 – Ligar o frontend ao backend (CORS)

29. Volta ao [Render](https://render.com) → **Dashboard** → clica no teu **Web Service** (a API).
30. Abre o separador **Environment** (menu lateral).
31. Encontra a variável **`FRONTEND_URL`** e clica em **Edit** (ou **Add** se não existir).
32. Põe o **URL exato do frontend na Vercel**, **sem barra no fim** (ex.: `https://parser-escalas-xxx.vercel.app`). Guarda.
33. O Render faz redeploy sozinho. Espera 1–2 minutos e abre de novo o site na Vercel; tenta carregar a escala. Deve passar a funcionar.

---

## Fase 3 – Verificar

34. **Frontend (Vercel):** abres o URL do site e vês a interface.
35. **Carregar escala:** escolhes número de funcionário, mês/ano e carregas em "Carregar escala". Se a base de dados estiver vazia, pode dar "User not found" – é esperado até haver dados (import em produção é outro passo).
36. **API (Render):** `https://TEU-API.onrender.com/docs` continua a abrir o Swagger.

---

## Resumo dos URLs e variáveis

| Onde anotar | O quê |
|-------------|--------|
| Render → PostgreSQL → Connections | **Internal Database URL** → usar em `DATABASE_URL` |
| Render → Web Service → topo da página | **URL da API** (ex.: `https://xxx.onrender.com`) → usar em `VITE_API_URL` na Vercel |
| Vercel → Project → Domains | **URL do site** (ex.: `https://xxx.vercel.app`) → usar em `FRONTEND_URL` no Render |

---

## Problemas comuns

- **"Failed to fetch" / CORS:** confirma que no Render tens `FRONTEND_URL` exatamente igual ao URL da Vercel (com `https://`, sem `/` no fim).
- **"User not found" ao carregar escala:** a base de dados em produção está vazia. O botão "Importar escalas" no site não consegue ler PDFs do teu PC; para ter dados em produção precisas de importar de outra forma (ver secção 5 do `DEPLOY.md`).
- **API demora muito na primeira vez:** no plano free o Render adormece o serviço; o primeiro pedido após uns minutos pode demorar 30–60 s.

Quando tiveres estes passos feitos, a app está online. Para importar escalas em produção, vê a secção **5. Importar escalas em produção** no ficheiro `DEPLOY.md`.
