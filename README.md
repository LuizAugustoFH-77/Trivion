# Trivion - Quiz em Tempo Real

## Deploy no Render.com

### Pré-requisitos
- Conta no [Render.com](https://render.com)
- Repositório Git (GitHub, GitLab ou Bitbucket)

### Passo a Passo

#### 1. Suba o código para o GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/SEU_USUARIO/trivion.git
git push -u origin main
```

#### 2. Crie o Web Service no Render

1. Acesse [dashboard.render.com](https://dashboard.render.com)
2. Clique em **"New +"** → **"Web Service"**
3. Conecte seu repositório GitHub
4. Selecione o repositório `trivion`

#### 3. Configure o serviço

| Campo | Valor |
|-------|-------|
| **Name** | `trivion` |
| **Region** | Escolha a mais próxima |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.principal:socket_app --host 0.0.0.0 --port $PORT` |

#### 4. Variáveis de ambiente (opcional)

Não são necessárias para este projeto.

#### 5. Deploy

Clique em **"Create Web Service"** e aguarde o deploy (~2-3 minutos).

### URLs após deploy

- **Jogadores**: `https://trivion.onrender.com/`
- **Admin**: `https://trivion.onrender.com/admin`

### Observações

- O plano gratuito do Render "adormece" após 15 min sem uso
- A primeira requisição após adormecimento leva ~30s
- Para uso contínuo, considere o plano pago

---

## Desenvolvimento Local

```bash
pip install -r requirements.txt
uvicorn backend.principal:socket_app --reload --host 0.0.0.0 --port 8000
```

Acesse em http://localhost:8000
