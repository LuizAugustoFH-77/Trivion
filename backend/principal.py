"""Trivion - Servidor Principal

Sistema de quiz em tempo real com múltiplas salas.

Conceitos de Sistemas Distribuídos:
- Relógios lógicos de Lamport (ordenação de respostas)
- Heartbeat para detecção de falhas
"""

import os
import logging
from pathlib import Path
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List

from .salas import GerenciadorSalas
from .jogo import GerenciadorJogo
from .heartbeat import heartbeat
from .modelos import Papel

# Logging simples
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("trivion")

# FastAPI
app = FastAPI(title="Trivion", version="3.0.0")

# Socket.IO manager (opcional para escala horizontal)
redis_url = os.environ.get("REDIS_URL") or os.environ.get("SIO_REDIS_URL")
socket_manager = None
if redis_url:
    try:
        socket_manager = socketio.AsyncRedisManager(redis_url)
        logger.info("Socket.IO Redis manager habilitado")
    except Exception as exc:
        logger.warning(f"Falha ao inicializar Redis manager: {exc}")

# Socket.IO
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    ping_timeout=20,
    ping_interval=10,
    client_manager=socket_manager
)
socket_app = socketio.ASGIApp(sio, app)

# Gerenciadores
salas = GerenciadorSalas()
jogos: dict[str, GerenciadorJogo] = {}


def obter_jogo(codigo: str) -> Optional[GerenciadorJogo]:
    """Obtém ou cria gerenciador de jogo para uma sala."""
    if codigo not in jogos:
        sala = salas.obter_sala(codigo)
        if sala:
            jogo = GerenciadorJogo(sala.sessao, codigo)
            
            async def broadcast(evento: str, dados: dict):
                await sio.emit(evento, dados, room=f"sala_{codigo}")
                
            jogo.definir_broadcast(broadcast)
            jogos[codigo] = jogo
            
    return jogos.get(codigo)


# === EVENTOS SOCKET.IO ===

@sio.event
async def connect(sid, environ):
    """Nova conexão."""
    logger.info(f"Cliente conectado: {sid}")
    await heartbeat.registrar(sid)


@sio.event
async def disconnect(sid):
    """Desconexão."""
    logger.info(f"Cliente desconectado: {sid}")
    
    resultado = await salas.sair_sala(sid)
    if resultado[0] and resultado[1]:
        sala, jogador = resultado

        # Registra para reconexão
        await heartbeat.desconectar(
            sid,
            jogador.id,
            jogador.nome,
            sala.codigo,
            jogador.pontuacao,
            jogador.papel.value,
            jogador.em_espera
        )

        # Notifica sala com lista atualizada
        await sio.emit("jogador_saiu", {
            "jogador_id": jogador.id,
            "nome": jogador.nome,
            "temporario": True,
            "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
        }, room=f"sala_{sala.codigo}")


@sio.on("pong_heartbeat")
async def ao_pong(sid, dados):
    """Resposta ao heartbeat."""
    await heartbeat.heartbeat(sid)


@sio.on("reconectar")
async def ao_reconectar(sid, dados):
    """Tenta reconectar jogador."""
    jogador_id = dados.get("jogador_id")
    
    estado = await heartbeat.reconectar(sid, jogador_id)
    if estado:
        logger.info(f"Reconexão: {estado.nome} -> {estado.sala_codigo}")
        sala = salas.obter_sala(estado.sala_codigo)
        if not sala:
            await sio.emit("reconexao_falhou", {
                "mensagem": "Sala não encontrada"
            }, room=sid)
            return

        jogador = await salas.reconectar_jogador(
            codigo=estado.sala_codigo,
            jogador_id=estado.jogador_id,
            nome=estado.nome,
            sid=sid,
            pontuacao=estado.pontuacao,
            papel=Papel(estado.papel),
            em_espera=estado.em_espera
        )
        if not jogador:
            await sio.emit("reconexao_falhou", {
                "mensagem": "Não foi possível reconectar"
            }, room=sid)
            return

        await sio.enter_room(sid, f"sala_{estado.sala_codigo}")
        await sio.emit("reconexao_sucesso", {
            "jogador_id": jogador.id,
            "nome": jogador.nome,
            "sala_codigo": estado.sala_codigo,
            "pontuacao": jogador.pontuacao,
            "em_espera": jogador.em_espera
        }, room=sid)

        await sio.emit("jogador_entrou", {
            "jogador": jogador.para_dict(),
            "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
        }, room=f"sala_{estado.sala_codigo}")

        await sio.emit("estado", sala.sessao.para_dict(), room=sid)
    else:
        await sio.emit("reconexao_falhou", {
            "mensagem": "Sessão expirada"
        }, room=sid)


# === EVENTOS DE SALA ===

@sio.on("listar_salas")
async def ao_listar_salas(sid):
    """Lista salas públicas."""
    await sio.emit("salas_disponiveis", {"salas": salas.listar_salas()}, room=sid)


@sio.on("criar_sala")
async def ao_criar_sala(sid, dados):
    """Cria nova sala."""
    nome = dados.get("nome", "").strip()
    if not nome:
        await sio.emit("erro", {"mensagem": "Nome obrigatório"}, room=sid)
        return
        
    sala = salas.criar_sala(
        nome=nome,
        dono_sid=sid,
        publica=dados.get("publica", True),
        senha=dados.get("senha")
    )
    
    await sio.enter_room(sid, f"sala_{sala.codigo}")
    await sio.emit("sala_criada", {
        "sala": sala.para_dict(),
        "codigo": sala.codigo
    }, room=sid)


@sio.on("entrar_sala")
async def ao_entrar_sala(sid, dados):
    """Entra em sala existente."""
    codigo = dados.get("codigo", "").strip().upper()
    nome = dados.get("nome", "").strip()[:15]
    
    if not codigo or not nome:
        await sio.emit("erro", {"mensagem": "Código e nome obrigatórios"}, room=sid)
        return
        
    jogador, erro = await salas.entrar_sala(
        codigo=codigo,
        nome=nome,
        sid=sid,
        senha=dados.get("senha"),
        como_admin=dados.get("como_admin", False)
    )
    
    if not jogador:
        await sio.emit("erro", {"mensagem": erro}, room=sid)
        return
        
    sala = salas.obter_sala(codigo)
    await sio.enter_room(sid, f"sala_{codigo}")
    
    await sio.emit("bem_vindo", {
        "jogador": jogador.para_dict(),
        "sala": sala.para_dict(),
        "estado": sala.sessao.para_dict()
    }, room=sid)
    
    await sio.emit("jogador_entrou", {
        "jogador": jogador.para_dict(),
        "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
    }, room=f"sala_{codigo}")


@sio.on("sair_sala")
async def ao_sair_sala(sid):
    """Sai da sala."""
    resultado = await salas.sair_sala(sid)
    if resultado[0] and resultado[1]:
        sala, jogador = resultado
        await sio.leave_room(sid, f"sala_{sala.codigo}")
        await sio.emit("saiu_sala", {}, room=sid)
        await sio.emit("jogador_saiu", {
            "jogador_id": jogador.id,
            "nome": jogador.nome,
            "temporario": False,
            "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
        }, room=f"sala_{sala.codigo}")


# === EVENTOS DE JOGO ===

@sio.on("responder")
async def ao_responder(sid, dados):
    """Jogador responde."""
    sala = salas.obter_sala_do_jogador(sid)
    if not sala:
        return
        
    jogo = obter_jogo(sala.codigo)
    if not jogo:
        return
        
    resposta = dados.get("resposta")
    timestamp = dados.get("timestamp", 0)
    
    if resposta is None or not isinstance(resposta, int) or resposta < 0 or resposta > 3:
        await sio.emit("erro", {"mensagem": "Resposta inválida"}, room=sid)
        return
        
    await jogo.processar_resposta(sid, resposta, timestamp)


@sio.on("obter_estado")
async def ao_obter_estado(sid):
    """Retorna estado atual."""
    sala = salas.obter_sala_do_jogador(sid)
    if sala:
        await sio.emit("estado", sala.sessao.para_dict(), room=sid)


# === API REST ===

class PerguntaRequest(BaseModel):
    texto: str
    opcoes: List[str]
    correta: int
    tempo_limite: int = 20


@app.get("/api/salas")
async def api_listar_salas():
    return {"salas": salas.listar_salas()}


@app.get("/api/salas/{codigo}")
async def api_obter_sala(codigo: str):
    sala = salas.obter_sala(codigo)
    if not sala:
        raise HTTPException(404, "Sala não encontrada")
    return sala.para_dict()


@app.get("/api/salas/{codigo}/perguntas")
async def api_listar_perguntas(codigo: str):
    return {"perguntas": salas.obter_perguntas(codigo)}


@app.post("/api/salas/{codigo}/perguntas")
async def api_adicionar_pergunta(codigo: str, p: PerguntaRequest):
    if not salas.adicionar_pergunta(codigo, p.texto, p.opcoes, p.correta, p.tempo_limite):
        raise HTTPException(404, "Sala não encontrada")
    return {"status": "ok"}


@app.delete("/api/salas/{codigo}/perguntas/{indice}")
async def api_remover_pergunta(codigo: str, indice: int):
    if not salas.remover_pergunta(codigo, indice):
        raise HTTPException(404, "Pergunta não encontrada")
    return {"status": "ok"}


@app.delete("/api/salas/{codigo}/perguntas")
async def api_limpar_perguntas(codigo: str):
    if not salas.limpar_perguntas(codigo):
        raise HTTPException(404, "Sala não encontrada")
    return {"status": "ok"}


@app.post("/api/salas/{codigo}/jogo/iniciar")
async def api_iniciar_jogo(codigo: str):
    jogo = obter_jogo(codigo.upper())
    if not jogo:
        raise HTTPException(404, "Sala não encontrada")
    if await jogo.iniciar():
        return {"status": "ok"}
    return {"status": "erro", "mensagem": "Não foi possível iniciar"}


@app.post("/api/salas/{codigo}/jogo/proxima")
async def api_proxima_pergunta(codigo: str):
    jogo = obter_jogo(codigo.upper())
    if not jogo:
        raise HTTPException(404, "Sala não encontrada")
    if await jogo.proxima():
        return {"status": "ok"}
    return {"status": "erro"}


@app.post("/api/salas/{codigo}/jogo/encerrar")
async def api_encerrar_jogo(codigo: str):
    jogo = obter_jogo(codigo.upper())
    if not jogo:
        raise HTTPException(404, "Sala não encontrada")
    await jogo.encerrar()
    return {"status": "ok"}


@app.get("/api/salas/{codigo}/jogo/estado")
async def api_estado_jogo(codigo: str):
    sala = salas.obter_sala(codigo.upper())
    if not sala:
        raise HTTPException(404, "Sala não encontrada")
    return sala.sessao.para_dict()


@app.delete("/api/salas/{codigo}")
async def api_excluir_sala(codigo: str):
    codigo = codigo.upper()
    sala = salas.obter_sala(codigo)
    if not sala:
        raise HTTPException(404, "Sala não encontrada")

    # Cancela jogo/timer se existir
    jogo = jogos.pop(codigo, None)
    if jogo and jogo._timer_task:
        jogo._timer_task.cancel()

    sids = salas.encerrar_sala(codigo)

    # Limpa reconexões pendentes da sala
    for jogador_id, estado in list(heartbeat.desconectados.items()):
        if estado.sala_codigo == codigo:
            del heartbeat.desconectados[jogador_id]

    await sio.emit("sala_encerrada", {
        "mensagem": "Sala encerrada pelo administrador"
    }, room=f"sala_{codigo}")

    for sid in sids:
        await sio.leave_room(sid, f"sala_{codigo}")
        heartbeat.remover(sid)

    return {"status": "ok"}

@app.get("/api/saude")
async def api_saude():
    return {"status": "ok", "versao": "3.0.0"}


# === ARQUIVOS ESTÁTICOS ===

FRONTEND = Path(__file__).parent.parent / "frontend"


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/admin")
async def admin():
    return FileResponse(FRONTEND / "admin.html")


@app.get("/sala/{codigo}")
async def sala_page(codigo: str):
    return FileResponse(FRONTEND / "index.html")


@app.get("/admin/{codigo}")
async def admin_sala_page(codigo: str):
    return FileResponse(FRONTEND / "admin.html")


if FRONTEND.exists():
    app.mount("/css", StaticFiles(directory=FRONTEND / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND / "js"), name="js")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.principal:socket_app", host="0.0.0.0", port=port, reload=True)
