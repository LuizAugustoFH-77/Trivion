"""
Trivion - Servidor Principal
==============================

Ponto de entrada do sistema. Combina FastAPI (REST API) com
Socket.IO (comunicação em tempo real) em um único servidor.

CONCEITOS DE SISTEMAS DISTRIBUÍDOS:
------------------------------------
1. SERVIDOR CENTRALIZADO: Um único ponto que coordena todos os clientes
2. API REST: Para operações de controle (admin)
3. WEBSOCKETS: Para comunicação bidirecional em tempo real
4. CONCORRÊNCIA: Tratamento de múltiplas conexões simultâneas com asyncio

Para executar:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

import os
from pathlib import Path
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import logging

from .game_manager import GameManager

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# INICIALIZAÇÃO DO SERVIDOR
# =============================================================================

# Cria aplicação FastAPI
# FastAPI é um framework moderno para APIs REST com suporte a async/await
app = FastAPI(
    title="Trivion - Quiz Distribuído",
    description="Sistema de quiz em tempo real inspirado no Kahoot",
    version="1.0.0"
)

# Cria servidor Socket.IO
# CONCEITO: Socket.IO fornece comunicação bidirecional em tempo real
# com fallback automático para polling se WebSockets não estiver disponível
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',  # Em produção, restringir origens
    logger=True,
    engineio_logger=False
)

# Combina FastAPI + Socket.IO em uma única aplicação ASGI
# CONCEITO: ASGI (Asynchronous Server Gateway Interface) permite
# que múltiplos protocolos coexistam no mesmo servidor
socket_app = socketio.ASGIApp(sio, app)

# Gerenciador do jogo (singleton)
game_manager = GameManager()


# =============================================================================
# CALLBACK DE BROADCAST
# =============================================================================

async def broadcast_to_all(event: str, data: dict):
    """
    Função de broadcast: envia evento para todos os clientes conectados.
    
    CONCEITO: Difusão (Broadcast)
    Em sistemas distribuídos, broadcast é fundamental para manter
    todos os nós sincronizados. Aqui enviamos para o room 'game'
    que contém todos os jogadores.
    """
    await sio.emit(event, data, room='game')


# Registra callback no game manager
game_manager.set_broadcast_callback(broadcast_to_all)


# =============================================================================
# EVENTOS SOCKET.IO (COMUNICAÇÃO EM TEMPO REAL)
# =============================================================================

@sio.event
async def connect(sid, environ):
    """
    Evento de conexão de novo cliente.
    
    CONCEITO: Handshake de Conexão
    Quando um cliente conecta, ele ainda não está no jogo.
    Precisa enviar evento 'join' com seu nome para entrar.
    """
    logger.info(f"Cliente conectado: {sid}")
    # Adiciona ao room 'game' para receber broadcasts
    await sio.enter_room(sid, 'game')


@sio.event
async def disconnect(sid):
    """
    Evento de desconexão de cliente.
    
    CONCEITO: Tolerância a Falhas
    Quando um cliente desconecta (fechou aba, perdeu conexão, etc),
    removemos seu estado e notificamos os demais jogadores.
    """
    logger.info(f"Cliente desconectado: {sid}")
    await game_manager.remove_player(sid)


@sio.event
async def join(sid, data):
    """
    Evento: Jogador quer entrar no jogo.
    
    Payload esperado: { "name": "Nome do Jogador" }
    
    CONCEITO: Registro de Cliente
    O cliente se registra no sistema fornecendo um identificador
    (nome). O servidor cria um ID único e confirma a entrada.
    """
    try:
        name = data.get("name", "").strip()
        if not name:
            await sio.emit("error", {"message": "Nome é obrigatório"}, room=sid)
            return
        
        if len(name) > 20:
            name = name[:20]
        
        player = await game_manager.add_player(name, sid)
        
        # Confirma entrada para o cliente
        await sio.emit("welcome", {
            "player": player.to_dict(),
            "state": game_manager.get_session_state()
        }, room=sid)
        
    except Exception as e:
        logger.error(f"Erro no join: {e}")
        await sio.emit("error", {"message": "Erro ao entrar no jogo"}, room=sid)


@sio.event
async def answer(sid, data):
    """
    Evento: Jogador envia resposta.
    
    Payload esperado: { "answer": 0-3, "timestamp": milliseconds }
    
    CONCEITO: Processamento de Eventos Distribuídos
    Múltiplos jogadores podem enviar respostas simultaneamente.
    O game_manager usa locks para processar cada resposta de forma
    thread-safe, garantindo consistência.
    """
    try:
        answer_index = data.get("answer")
        client_timestamp = data.get("timestamp", 0)
        
        if answer_index is None or not isinstance(answer_index, int):
            await sio.emit("error", {"message": "Resposta inválida"}, room=sid)
            return
        
        if answer_index < 0 or answer_index > 3:
            await sio.emit("error", {"message": "Índice de resposta inválido"}, room=sid)
            return
        
        await game_manager.handle_answer(sid, answer_index, client_timestamp)
        
    except Exception as e:
        logger.error(f"Erro ao processar resposta: {e}")


@sio.event
async def get_state(sid):
    """
    Evento: Cliente solicita estado atual.
    
    CONCEITO: Sincronização de Estado
    Útil para reconexão ou quando o cliente precisa atualizar seu estado.
    """
    await sio.emit("state", game_manager.get_session_state(), room=sid)


# =============================================================================
# ROTAS REST (PAINEL ADMIN)
# =============================================================================

@app.post("/api/game/start")
async def start_game():
    """
    Inicia o jogo (somente admin).
    
    CONCEITO: Controle Centralizado
    O administrador (apresentador) controla quando o jogo começa.
    Isso garante que todos os jogadores iniciem ao mesmo tempo.
    """
    try:
        await game_manager.start_game()
        return {"status": "ok", "message": "Jogo iniciado"}
    except Exception as e:
        logger.error(f"Erro ao iniciar jogo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/game/next")
async def next_question():
    """Avança para a próxima pergunta."""
    try:
        await game_manager.next_question()
        return {"status": "ok", "message": "Próxima pergunta"}
    except Exception as e:
        logger.error(f"Erro ao avançar pergunta: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/game/leaderboard")
async def show_leaderboard():
    """Mostra leaderboard completo após pódio."""
    try:
        await game_manager.show_leaderboard()
        return {"status": "ok", "message": "Leaderboard exibido"}
    except Exception as e:
        logger.error(f"Erro ao mostrar leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/game/reset")
async def reset_game():
    """Reinicia o jogo."""
    try:
        await game_manager.reset_game()
        return {"status": "ok", "message": "Jogo reiniciado"}
    except Exception as e:
        logger.error(f"Erro ao reiniciar jogo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/game/state")
async def get_game_state():
    """Retorna estado atual do jogo."""
    return game_manager.get_session_state()


@app.get("/api/game/stats")
async def get_answer_stats():
    """Retorna estatísticas de respostas atuais."""
    return game_manager.get_answer_stats()


# =============================================================================
# ARQUIVOS ESTÁTICOS (FRONTEND)
# =============================================================================

# Caminho para a pasta frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def serve_index():
    """Serve a página principal do jogador."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin")
async def serve_admin():
    """Serve a página do administrador."""
    return FileResponse(FRONTEND_DIR / "admin.html")


# Monta arquivos estáticos (CSS, JS)
if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


# =============================================================================
# PONTO DE ENTRADA
# =============================================================================

# A aplicação combinada (FastAPI + Socket.IO)
# Use 'app' para desenvolvimento local, 'socket_app' para produção

def create_app():
    """Factory function para criar a aplicação ASGI"""
    return socket_app


if __name__ == "__main__":
    # Desenvolvimento local
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "backend.main:socket_app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
