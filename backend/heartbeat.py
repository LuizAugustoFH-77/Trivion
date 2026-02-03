"""Trivion - Monitor de Heartbeat

Sistema simplificado de heartbeat para detecção de desconexões
e suporte a reconexão de jogadores.

Conceitos de Sistemas Distribuídos:
- Heartbeat para detecção de falhas
- Preservação temporária de estado para reconexão
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Dict, Callable, Awaitable

# Timeout para reconexão (segundos)
TIMEOUT_RECONEXAO = 10


@dataclass
class JogadorDesconectado:
    """Estado de jogador temporariamente desconectado."""
    jogador_id: str
    nome: str
    sala_codigo: str
    pontuacao: int
    papel: str
    em_espera: bool
    timestamp: float


class HeartbeatMonitor:
    """Monitor de conexão simplificado."""
    
    def __init__(self):
        self.clientes: Dict[str, float] = {}  # sid -> ultimo_
        
        self.desconectados: Dict[str, JogadorDesconectado] = {}  # jogador_id -> estado
        self._callback_remover: Optional[Callable] = None
        
    def definir_callback(self, callback_remover: Callable[[str, str], Awaitable[None]]):
        """Define callback para remover jogador após timeout."""
        self._callback_remover = callback_remover
        
    async def registrar(self, sid: str):
        """Registra novo cliente."""
        self.clientes[sid] = time.time()
        
    async def heartbeat(self, sid: str):
        """Atualiza timestamp de heartbeat."""
        self.clientes[sid] = time.time()
        
    async def desconectar(
        self,
        sid: str,
        jogador_id: str,
        nome: str,
        sala_codigo: str,
        pontuacao: int,
        papel: str,
        em_espera: bool
    ):
        """Registra desconexão para possível reconexão."""
        self.clientes.pop(sid, None)
        
        self.desconectados[jogador_id] = JogadorDesconectado(
            jogador_id=jogador_id,
            nome=nome,
            sala_codigo=sala_codigo,
            pontuacao=pontuacao,
            papel=papel,
            em_espera=em_espera,
            timestamp=time.time()
        )
        
        # Agenda limpeza após timeout
        asyncio.create_task(self._limpar_apos_timeout(jogador_id, sala_codigo))
        
    async def _limpar_apos_timeout(self, jogador_id: str, sala_codigo: str):
        """Remove jogador após timeout de reconexão."""
        await asyncio.sleep(TIMEOUT_RECONEXAO)
        
        if jogador_id in self.desconectados:
            del self.desconectados[jogador_id]
            if self._callback_remover:
                await self._callback_remover(sala_codigo, jogador_id)
                
    async def reconectar(self, sid: str, jogador_id: str) -> Optional[JogadorDesconectado]:
        """Tenta reconectar jogador."""
        if jogador_id in self.desconectados:
            estado = self.desconectados.pop(jogador_id)
            self.clientes[sid] = time.time()
            return estado
        return None
        
    def remover(self, sid: str):
        """Remove cliente."""
        self.clientes.pop(sid, None)


# Instância global
heartbeat = HeartbeatMonitor()
