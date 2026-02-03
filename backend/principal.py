"""Trivion - Servidor Principal

Sistema de quiz em tempo real com múltiplas salas.

Conceitos de Sistemas Distribuídos:
- Relógios lógicos de Lamport (ordenação de respostas)
- Heartbeat para detecção de falhas
"""

import os
import logging
import asyncio
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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

# WebSocket nativo (FastAPI)
PING_INTERVAL = 5
PING_TIMEOUT = 15


class ConnectionManager:
    def __init__(self):
        self.conexoes: dict[str, WebSocket] = {}
        self.salas: dict[str, set[str]] = {}
        self._ping_tasks: dict[str, asyncio.Task] = {}

    async def conectar(self, websocket: WebSocket) -> str:
        await websocket.accept()
        sid = str(uuid.uuid4())
        self.conexoes[sid] = websocket
        await heartbeat.registrar(sid)
        self._ping_tasks[sid] = asyncio.create_task(self._loop_ping(sid))
        return sid

    async def desconectar(self, sid: str):
        self._cancelar_ping(sid)
        self.remover_de_todas_as_salas(sid)
        self.conexoes.pop(sid, None)
        heartbeat.remover(sid)

    def _cancelar_ping(self, sid: str):
        task = self._ping_tasks.pop(sid, None)
        if task:
            task.cancel()

    async def _loop_ping(self, sid: str):
        while sid in self.conexoes:
            await asyncio.sleep(PING_INTERVAL)
            ultimo = heartbeat.clientes.get(sid, 0)
            if time.time() - ultimo > PING_TIMEOUT:
                logger.info(f"Heartbeat expirou para {sid}")
                await self._forcar_desconexao(sid)
                break
            await self.enviar_para_sid(sid, "ping_heartbeat", {})

    async def _forcar_desconexao(self, sid: str):
        ws = self.conexoes.get(sid)
        if ws:
            try:
                await ws.close()
            except Exception:
                pass

    def entrar_sala(self, sid: str, sala: str):
        self.salas.setdefault(sala, set()).add(sid)

    def sair_sala(self, sid: str, sala: str):
        if sala in self.salas:
            self.salas[sala].discard(sid)
            if not self.salas[sala]:
                del self.salas[sala]

    def remover_de_todas_as_salas(self, sid: str):
        for sala in list(self.salas.keys()):
            self.salas[sala].discard(sid)
            if not self.salas[sala]:
                del self.salas[sala]

    async def enviar_para_sid(self, sid: str, tipo: str, dados: dict):
        ws = self.conexoes.get(sid)
        if ws:
            await ws.send_json({"tipo": tipo, "dados": dados})

    async def broadcast_sala(self, sala: str, tipo: str, dados: dict):
        for sid in list(self.salas.get(sala, set())):
            await self.enviar_para_sid(sid, tipo, dados)


manager = ConnectionManager()

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
                await manager.broadcast_sala(f"sala_{codigo}", evento, dados)
                
            jogo.definir_broadcast(broadcast)
            jogos[codigo] = jogo
            
    return jogos.get(codigo)


# WEBSOCKET

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    sid = await manager.conectar(websocket)
    logger.info(f"Cliente conectado: {sid}")
    try:
        while True:
            mensagem = await websocket.receive_json()
            await heartbeat.heartbeat(sid)
            await _rotear_mensagem(sid, mensagem)
    except WebSocketDisconnect:
        logger.info(f"Cliente desconectado: {sid}")
    finally:
        await _processar_desconexao(sid)


async def _processar_desconexao(sid: str):
    resultado = await salas.sair_sala(sid)
    if resultado[0] and resultado[1]:
        sala, jogador = resultado

        await heartbeat.desconectar(
            sid,
            jogador.id,
            jogador.nome,
            sala.codigo,
            jogador.pontuacao,
            jogador.papel.value,
            jogador.em_espera
        )

        await manager.broadcast_sala(f"sala_{sala.codigo}", "jogador_saiu", {
            "jogador_id": jogador.id,
            "nome": jogador.nome,
            "temporario": True,
            "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
        })

    await manager.desconectar(sid)


async def _rotear_mensagem(sid: str, mensagem: dict):
    tipo = (mensagem or {}).get("tipo")
    dados = (mensagem or {}).get("dados") or {}

    if tipo == "pong_heartbeat":
        await heartbeat.heartbeat(sid)
        return

    if tipo == "reconectar":
        await _ao_reconectar(sid, dados)
        return

    if tipo == "listar_salas":
        await manager.enviar_para_sid(sid, "salas_disponiveis", {"salas": salas.listar_salas()})
        return

    if tipo == "criar_sala":
        await _ao_criar_sala(sid, dados)
        return

    if tipo == "entrar_sala":
        await _ao_entrar_sala(sid, dados)
        return

    if tipo == "sair_sala":
        await _ao_sair_sala(sid)
        return

    if tipo == "responder":
        await _ao_responder(sid, dados)
        return

    if tipo == "obter_estado":
        await _ao_obter_estado(sid)
        return

    await manager.enviar_para_sid(sid, "erro", {"mensagem": "Tipo de mensagem inválido"})


async def _ao_reconectar(sid: str, dados: dict):
    jogador_id = dados.get("jogador_id")
    estado = await heartbeat.reconectar(sid, jogador_id)
    if estado:
        logger.info(f"Reconexão: {estado.nome} -> {estado.sala_codigo}")
        sala = salas.obter_sala(estado.sala_codigo)
        if not sala:
            await manager.enviar_para_sid(sid, "reconexao_falhou", {
                "mensagem": "Sala não encontrada"
            })
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
            await manager.enviar_para_sid(sid, "reconexao_falhou", {
                "mensagem": "Não foi possível reconectar"
            })
            return

        manager.entrar_sala(sid, f"sala_{estado.sala_codigo}")
        await manager.enviar_para_sid(sid, "reconexao_sucesso", {
            "jogador_id": jogador.id,
            "nome": jogador.nome,
            "sala_codigo": estado.sala_codigo,
            "pontuacao": jogador.pontuacao,
            "em_espera": jogador.em_espera
        })

        await manager.broadcast_sala(f"sala_{estado.sala_codigo}", "jogador_entrou", {
            "jogador": jogador.para_dict(),
            "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
        })

        await manager.enviar_para_sid(sid, "estado", sala.sessao.para_dict())
    else:
        await manager.enviar_para_sid(sid, "reconexao_falhou", {
            "mensagem": "Sessão expirada"
        })


async def _ao_criar_sala(sid: str, dados: dict):
    nome = dados.get("nome", "").strip()
    if not nome:
        await manager.enviar_para_sid(sid, "erro", {"mensagem": "Nome obrigatório"})
        return

    sala = salas.criar_sala(
        nome=nome,
        dono_sid=sid,
        publica=dados.get("publica", True),
        senha=dados.get("senha")
    )

    manager.entrar_sala(sid, f"sala_{sala.codigo}")
    await manager.enviar_para_sid(sid, "sala_criada", {
        "sala": sala.para_dict(),
        "codigo": sala.codigo
    })


async def _ao_entrar_sala(sid: str, dados: dict):
    codigo = dados.get("codigo", "").strip().upper()
    nome = dados.get("nome", "").strip()[:15]

    if not codigo or not nome:
        await manager.enviar_para_sid(sid, "erro", {"mensagem": "Código e nome obrigatórios"})
        return

    jogador, erro = await salas.entrar_sala(
        codigo=codigo,
        nome=nome,
        sid=sid,
        senha=dados.get("senha"),
        como_admin=dados.get("como_admin", False)
    )

    if not jogador:
        await manager.enviar_para_sid(sid, "erro", {"mensagem": erro})
        return

    sala = salas.obter_sala(codigo)
    manager.entrar_sala(sid, f"sala_{codigo}")

    await manager.enviar_para_sid(sid, "bem_vindo", {
        "jogador": jogador.para_dict(),
        "sala": sala.para_dict(),
        "estado": sala.sessao.para_dict()
    })

    await manager.broadcast_sala(f"sala_{codigo}", "jogador_entrou", {
        "jogador": jogador.para_dict(),
        "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
    })


async def _ao_sair_sala(sid: str):
    resultado = await salas.sair_sala(sid)
    if resultado[0] and resultado[1]:
        sala, jogador = resultado
        manager.sair_sala(sid, f"sala_{sala.codigo}")
        await manager.enviar_para_sid(sid, "saiu_sala", {})
        await manager.broadcast_sala(f"sala_{sala.codigo}", "jogador_saiu", {
            "jogador_id": jogador.id,
            "nome": jogador.nome,
            "temporario": False,
            "jogadores": [j.para_dict() for j in sala.sessao.jogadores.values()]
        })


async def _ao_responder(sid: str, dados: dict):
    sala = salas.obter_sala_do_jogador(sid)
    if not sala:
        return

    jogo = obter_jogo(sala.codigo)
    if not jogo:
        return

    resposta = dados.get("resposta")
    timestamp = dados.get("timestamp", 0)

    if resposta is None or not isinstance(resposta, int) or resposta < 0 or resposta > 3:
        await manager.enviar_para_sid(sid, "erro", {"mensagem": "Resposta inválida"})
        return

    await jogo.processar_resposta(sid, resposta, timestamp)


async def _ao_obter_estado(sid: str):
    sala = salas.obter_sala_do_jogador(sid)
    if sala:
        await manager.enviar_para_sid(sid, "estado", sala.sessao.para_dict())


# API REST

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

    await manager.broadcast_sala(f"sala_{codigo}", "sala_encerrada", {
        "mensagem": "Sala encerrada pelo administrador"
    })

    for sid in sids:
        manager.sair_sala(sid, f"sala_{codigo}")
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
    uvicorn.run("backend.principal:app", host="0.0.0.0", port=port, reload=True)
