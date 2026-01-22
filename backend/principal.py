"""Trivion - Servidor Principal"""

import os
from pathlib import Path
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import logging

from .gerenciador_jogo import GerenciadorJogo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Aplicação FastAPI
app = FastAPI(
    title="Trivion - Quiz Distribuído",
    description="Sistema de quiz em tempo real",
    version="1.0.0"
)

# Servidor Socket.IO
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=False
)

socket_app = socketio.ASGIApp(sio, app)

# Gerenciador do jogo
gerenciador_jogo = GerenciadorJogo()


# Callback de transmissão
async def transmitir_para_todos(evento: str, dados: dict):
    """Envia evento para todos os clientes conectados."""
    await sio.emit(evento, dados, room='jogo')


gerenciador_jogo.definir_callback_transmissao(transmitir_para_todos)


# === EVENTOS SOCKET.IO ===

@sio.event
async def connect(sid, environ):
    """Conexão de novo cliente."""
    logger.info(f"Cliente conectado: {sid}")
    await sio.enter_room(sid, 'jogo')


@sio.event
async def disconnect(sid):
    """Desconexão de cliente."""
    logger.info(f"Cliente desconectado: {sid}")
    await gerenciador_jogo.remover_jogador(sid)


@sio.on("entrar")
async def ao_entrar(sid, dados):
    """Jogador quer entrar no jogo."""
    try:
        nome = dados.get("nome", "").strip()
        if not nome:
            await sio.emit("erro", {"mensagem": "Nome é obrigatório"}, room=sid)
            return
        
        if len(nome) > 20:
            nome = nome[:20]
        
        jogador = await gerenciador_jogo.adicionar_jogador(nome, sid)
        
        # Jogador em espera recebe resposta diferente
        if jogador.em_espera:
            await sio.emit("em_espera", {
                "jogador": jogador.para_dict(),
                "mensagem": "Aguardando a próxima partida..."
            }, room=sid)
        else:
            await sio.emit("bem_vindo", {
                "jogador": jogador.para_dict(),
                "estado": gerenciador_jogo.obter_estado_sessao()
            }, room=sid)
        
    except ValueError as ve:
        # Erro de validação (nome duplicado ou ofensivo)
        await sio.emit("erro", {"mensagem": str(ve)}, room=sid)
    except Exception as e:
        logger.error(f"Erro ao entrar: {e}")
        await sio.emit("erro", {"mensagem": "Erro ao entrar no jogo"}, room=sid)


@sio.on("responder")
async def ao_responder(sid, dados):
    """Jogador envia resposta."""
    try:
        indice_resposta = dados.get("resposta")
        timestamp_cliente = dados.get("timestamp", 0)
        
        if indice_resposta is None or not isinstance(indice_resposta, int):
            await sio.emit("erro", {"mensagem": "Resposta inválida"}, room=sid)
            return
        
        if indice_resposta < 0 or indice_resposta > 3:
            await sio.emit("erro", {"mensagem": "Índice de resposta inválido"}, room=sid)
            return
        
        await gerenciador_jogo.processar_resposta(sid, indice_resposta, timestamp_cliente)
        
    except Exception as e:
        logger.error(f"Erro ao processar resposta: {e}")


@sio.on("obter_estado")
async def ao_obter_estado(sid):
    """Cliente solicita estado atual."""
    await sio.emit("estado", gerenciador_jogo.obter_estado_sessao(), room=sid)


# === ROTAS REST (ADMIN) ===

@app.post("/api/jogo/iniciar")
async def iniciar_jogo():
    """Inicia o jogo."""
    try:
        sucesso = await gerenciador_jogo.iniciar_jogo()
        if sucesso:
            return {"status": "ok", "mensagem": "Jogo iniciado"}
        return {"status": "erro", "mensagem": "Não foi possível iniciar o jogo"}
    except Exception as e:
        logger.error(f"Erro ao iniciar jogo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jogo/proxima")
async def proxima_pergunta():
    """Avança para a próxima pergunta."""
    try:
        sucesso = await gerenciador_jogo.proxima_pergunta()
        if sucesso:
            return {"status": "ok", "mensagem": "Próxima pergunta"}
        return {"status": "erro", "mensagem": "Ação não permitida no estado atual"}
    except Exception as e:
        logger.error(f"Erro ao avançar pergunta: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jogo/ranking")
async def mostrar_ranking():
    """Mostra ranking completo após pódio."""
    try:
        sucesso = await gerenciador_jogo.mostrar_ranking()
        if sucesso:
            return {"status": "ok", "mensagem": "Ranking exibido"}
        return {"status": "erro", "mensagem": "Ação não permitida no estado atual"}
    except Exception as e:
        logger.error(f"Erro ao mostrar ranking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jogo/encerrar")
async def encerrar_jogo():
    """Encerra o jogo e volta ao lobby."""
    try:
        sucesso = await gerenciador_jogo.encerrar_jogo()
        if sucesso:
            return {"status": "ok", "mensagem": "Jogo encerrado"}
        return {"status": "erro", "mensagem": "Erro ao encerrar jogo"}
    except Exception as e:
        logger.error(f"Erro ao encerrar jogo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jogo/estado")
async def obter_estado_jogo():
    """Retorna estado atual do jogo."""
    return gerenciador_jogo.obter_estado_sessao()


@app.get("/api/jogo/stats")
async def obter_stats_respostas():
    """Retorna estatísticas de respostas atuais."""
    return gerenciador_jogo.obter_estatisticas_respostas()


# === ARQUIVOS ESTÁTICOS ===

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def serve_index():
    """Página principal do jogador."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/admin")
async def serve_admin():
    """Página do administrador."""
    return FileResponse(FRONTEND_DIR / "admin.html")


if FRONTEND_DIR.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "backend.principal:socket_app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
