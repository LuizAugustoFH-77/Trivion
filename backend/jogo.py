"""Trivion - Gerenciador de Jogo

Lógica de uma sessão de jogo com relógios de Lamport.

Conceitos de Sistemas Distribuídos:
- Relógios lógicos de Lamport para ordenação de respostas
- Transições de estado síncronas
"""

import asyncio
import time
import logging
from typing import Optional, Callable, Awaitable

from .modelos import Sessao, EstadoJogo, Jogador, Papel
from .utils import calcular_pontuacao

logger = logging.getLogger(__name__)


class RelogioLamport:
    """Relógio lógico de Lamport simplificado.
    
    Conceito: ordena eventos de forma consistente em sistema distribuído.
    Regra: ao receber mensagem, contador = max(local, recebido) + 1
    """
    
    def __init__(self):
        self._contador = 0
        self._lock = asyncio.Lock()
        
    async def incrementar(self) -> int:
        """Incrementa antes de evento local."""
        async with self._lock:
            self._contador += 1
            return self._contador
            
    async def atualizar(self, timestamp_recebido: int) -> int:
        """Atualiza ao receber mensagem (regra de Lamport)."""
        async with self._lock:
            self._contador = max(self._contador, timestamp_recebido) + 1
            return self._contador
            
    def valor(self) -> int:
        return self._contador


class GerenciadorJogo:
    """Gerencia lógica de uma partida."""
    
    def __init__(self, sessao: Sessao, sala_codigo: str):
        self.sessao = sessao
        self.sala_codigo = sala_codigo
        self.relogio = RelogioLamport()
        self._broadcast: Optional[Callable] = None
        self._timer_task: Optional[asyncio.Task] = None
        
    def definir_broadcast(self, callback: Callable[[str, dict], Awaitable[None]]):
        """Define função de broadcast para a sala."""
        self._broadcast = callback
        
    async def broadcast(self, evento: str, dados: dict):
        """Envia evento para todos os jogadores."""
        if self._broadcast:
            await self._broadcast(evento, dados)
            
    async def iniciar(self) -> bool:
        """Inicia o jogo."""
        if self.sessao.estado != EstadoJogo.LOBBY:
            return False
            
        if not self.sessao.perguntas:
            return False
            
        self.sessao.estado = EstadoJogo.CONTAGEM
        await self.broadcast("contagem", {"segundos": 3})
        
        await asyncio.sleep(3)
        await self._proxima_pergunta()
        return True
        
    async def _proxima_pergunta(self):
        """Avança para próxima pergunta."""
        self.sessao.pergunta_atual += 1
        self.sessao.resetar_respostas()
        
        pergunta = self.sessao.obter_pergunta()
        if not pergunta:
            await self._exibir_podio()
            return
            
        self.sessao.estado = EstadoJogo.PERGUNTA
        self.sessao.tempo_inicio = time.time()
        
        # Incrementa relógio antes de enviar
        ts = await self.relogio.incrementar()
        
        await self.broadcast("pergunta", {
            "pergunta": pergunta.para_dict(),
            "numero": self.sessao.pergunta_atual + 1,
            "total": len(self.sessao.perguntas),
            "timestamp": ts
        })
        
        # Timer da pergunta
        self._timer_task = asyncio.create_task(self._timer(pergunta.tempo))
        
    async def _timer(self, segundos: int):
        """Timer da pergunta."""
        await asyncio.sleep(segundos)
        if self.sessao.estado == EstadoJogo.PERGUNTA:
            await self._mostrar_resultados()
            
    async def processar_resposta(self, sid: str, resposta: int, 
                                  timestamp_cliente: int) -> bool:
        """Processa resposta usando relógio de Lamport."""
        if self.sessao.estado != EstadoJogo.PERGUNTA:
            return False
            
        jogador = self.sessao.obter_jogador(sid)
        if not jogador or jogador.resposta_atual is not None:
            return False
        if jogador.em_espera or jogador.papel == Papel.ADMIN:
            return False
            
        # Atualiza relógio de Lamport
        ts = await self.relogio.atualizar(timestamp_cliente)
        
        # Calcula tempo de resposta
        tempo_ms = (time.time() - self.sessao.tempo_inicio) * 1000
        pergunta = self.sessao.obter_pergunta()
        
        jogador.resposta_atual = resposta
        jogador.tempo_resposta = tempo_ms
        
        # Calcula pontuação
        correta = resposta == pergunta.correta
        pontos = calcular_pontuacao(correta, tempo_ms, pergunta.tempo * 1000)
        jogador.pontuacao += pontos
        
        logger.debug(f"Resposta de {jogador.nome}: {resposta} (ts={ts}, pontos={pontos})")
        
        await self.broadcast("jogador_respondeu", {
            "jogador_id": jogador.id,
            "total_respostas": sum(1 for j in self.sessao.jogadores.values() 
                                   if j.resposta_atual is not None)
        })
        
        # Se todos responderam, mostra resultados
        if self.sessao.todos_responderam():
            if self._timer_task:
                self._timer_task.cancel()
            await self._mostrar_resultados()
            
        return True
        
    async def _mostrar_resultados(self):
        """Mostra resultados da pergunta."""
        self.sessao.estado = EstadoJogo.RESULTADOS
        pergunta = self.sessao.obter_pergunta()
        
        # Estatísticas de respostas
        stats = [0, 0, 0, 0]
        for j in self.sessao.jogadores.values():
            if j.resposta_atual is not None and 0 <= j.resposta_atual <= 3:
                stats[j.resposta_atual] += 1
                
        await self.broadcast("resultados", {
            "correta": pergunta.correta,
            "estatisticas": stats,
            "ranking": [j.para_dict() for j in self.sessao.ranking()[:5]]
        })
        
        # Auto-avança para próxima pergunta ou pódio
        await asyncio.sleep(5)
        
        if self.sessao.tem_mais_perguntas():
            await self._proxima_pergunta()
        else:
            await self._exibir_podio()
            
    async def proxima(self) -> bool:
        """Admin avança manualmente."""
        if self.sessao.estado == EstadoJogo.RESULTADOS:
            if self.sessao.tem_mais_perguntas():
                await self._proxima_pergunta()
            else:
                await self._exibir_podio()
            return True
        return False
        
    async def _exibir_podio(self):
        """Exibe pódio final."""
        self.sessao.estado = EstadoJogo.PODIO
        ranking = self.sessao.ranking()
        
        # Revelação dramática
        await self.broadcast("podio_inicio", {})
        await asyncio.sleep(2)
        
        # Revela 3º, 2º, 1º
        for i, pos in enumerate([2, 1, 0]):
            if pos < len(ranking):
                await asyncio.sleep(1.5)
                await self.broadcast("podio_posicao", {
                    "posicao": pos + 1,
                    "jogador": ranking[pos].para_dict()
                })
                
        await asyncio.sleep(2)
        await self.broadcast("podio_completo", {
            "ranking": [j.para_dict() for j in ranking]
        })
        
        self.sessao.estado = EstadoJogo.FINALIZADO
        
    async def encerrar(self) -> bool:
        """Encerra jogo e volta ao lobby."""
        if self._timer_task:
            self._timer_task.cancel()
            
        self.sessao.estado = EstadoJogo.LOBBY
        self.sessao.pergunta_atual = -1
        self.sessao.resetar_respostas()
        
        # Reseta pontuações
        for j in self.sessao.jogadores.values():
            j.pontuacao = 0
            j.em_espera = False
            
        await self.broadcast("jogo_encerrado", {
            "mensagem": "Jogo encerrado",
            "jogadores": [j.para_dict() for j in self.sessao.jogadores.values()]
        })
        return True
