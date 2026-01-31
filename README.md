# Trivion - Quiz Multiplayer em Tempo Real

Trivion é um jogo de quiz multiplayer em tempo real com várias salas, um painel de administração dedicado e um editor de perguntas integrado. Os jogadores entram usando um código de sala (e senha, se for privada), respondem às perguntas ao vivo e veem o ranking ser atualizado instantaneamente.

## Destaques
- Várias salas (públicas e privadas)
- Painel de administração para iniciar/avançar/encerrar partidas
- Editor de perguntas ao criar uma sala
- Pontuação e classificação em tempo real
- Suporte a reconexão
- Modo espectador para jogadores que entram no meio da partida

## Arquitetura
- Backend: FastAPI + Socket.IO (ASGI). Estado das salas/sessões em memória, endpoints REST para gerenciamento de salas/perguntas e eventos em tempo real para o jogo.
- Frontend: HTML/CSS/JS estático. A interface do jogador e do administrador compartilham o mesmo tema e são servidas pelo backend.

## Fluxo do Jogo
1. Crie uma sala e adicione perguntas no editor.
2. Compartilhe o código da sala (e a senha, se for privada).
3. O administrador inicia a partida; os jogadores respondem em tempo real.
4. Resultados, pódio e classificação final são exibidos automaticamente.
5. Os jogadores podem aguardar a próxima partida; o administrador pode iniciar novamente.

## Configuração
Variáveis de ambiente suportadas pelo servidor:
- PORT: porta HTTP do servidor (padrão 8000).
- REDIS_URL ou SIO_REDIS_URL: URL opcional do Redis para habilitar a fila de mensagens do Socket.IO (recomendado para escalonamento horizontal).

## Guia rápido de execução
Siga estes passos para executar a aplicação localmente (Windows/macOS/Linux):

1. Pré-requisitos
   - Python 3.9+ instalado
   - (Opcional) Redis rodando se quiser habilitar escalonamento via Socket.IO

2. Instale dependências

   - Crie e ative um ambiente virtual:
     - Windows (PowerShell): `python -m venv .venv` e `.\.venv\Scripts\Activate.ps1`
     - macOS/Linux: `python -m venv .venv` e `source .venv/bin/activate`

   - Instale os pacotes:
     - `pip install -r requirements.txt`

3. Configure variáveis de ambiente (opcional)
   - `PORT` — porta HTTP (padrão 8000)
   - `REDIS_URL` ou `SIO_REDIS_URL` — URL do Redis para habilitar o gerenciador do Socket.IO

4. Executando em ambiente de desenvolvimento

   - Usando o script de conveniência (Windows):
     - Execute `iniciar_servidor.bat` (abre o servidor e mostra o acesso em http://localhost:8000)

   - Ou diretamente com Python:
     - `python -m backend.principal`

   - Ou usando o Uvicorn (com recarga automática):
     - `uvicorn backend.principal:socket_app --host 0.0.0.0 --port 8000 --reload`

5. Acesso
   - Interface do jogador: `http://localhost:8000/`
   - Painel de administração: `http://localhost:8000/admin`

6. Produção
   - Use um servidor ASGI (Uvicorn/Gunicorn) sem `--reload` e com workers/processos adequados.
   - Considere definir `REDIS_URL` e mover o estado das salas para um armazenamento compartilhado ao escalar horizontalmente (ex.: Redis, DB).

## Observações sobre Escalabilidade
- O Socket.IO está pronto para usar o Redis como fila de mensagens quando a variável REDIS_URL estiver definida.
- O estado das salas/partidas ainda fica em memória; para escalar horizontalmente, mova o estado para um armazenamento compartilhado (ex.: Redis/BD) e coordene os temporizadores entre as instâncias.
