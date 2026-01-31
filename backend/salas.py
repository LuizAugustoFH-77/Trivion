"""Trivion - Gerenciador de Salas

Gerencia múltiplas salas de quiz.
"""

import random
import string
import hashlib
from typing import Optional, Dict, Tuple, Callable, Awaitable
import logging

from .modelos import Sala, Sessao, Jogador, Pergunta, Papel, EstadoJogo
from .utils import validar_nome

logger = logging.getLogger(__name__)


def gerar_codigo() -> str:
    """Gera código de 6 caracteres para sala."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def hash_senha(senha: str) -> str:
    """Gera hash da senha."""
    return hashlib.sha256(senha.encode()).hexdigest()


class GerenciadorSalas:
    """Gerencia todas as salas ativas."""
    
    def __init__(self):
        self.salas: Dict[str, Sala] = {}
        self.jogadores: Dict[str, str] = {}  # sid -> codigo_sala
        self._broadcast: Optional[Callable] = None
        
    def definir_broadcast(self, callback: Callable[[str, dict, str], Awaitable[None]]):
        """Define função de broadcast."""
        self._broadcast = callback
        
    async def broadcast(self, codigo: str, evento: str, dados: dict):
        """Envia evento para sala."""
        if self._broadcast:
            await self._broadcast(evento, dados, f"sala_{codigo}")
            
    def criar_sala(self, nome: str, dono_sid: str, publica: bool = True, 
                   senha: Optional[str] = None) -> Sala:
        """Cria nova sala."""
        codigo = gerar_codigo()
        while codigo in self.salas:
            codigo = gerar_codigo()
            
        sala = Sala(
            id=codigo,
            nome=nome,
            codigo=codigo,
            dono_sid=dono_sid,
            publica=publica,
            senha=hash_senha(senha) if senha else None
        )
        
        self.salas[codigo] = sala
        logger.info(f"Sala criada: {codigo} - {nome}")
        return sala
        
    def obter_sala(self, codigo: str) -> Optional[Sala]:
        """Obtém sala pelo código."""
        return self.salas.get(codigo.upper())
        
    def obter_sala_do_jogador(self, sid: str) -> Optional[Sala]:
        """Obtém sala onde o jogador está."""
        codigo = self.jogadores.get(sid)
        return self.salas.get(codigo) if codigo else None
        
    def listar_salas(self) -> list:
        """Lista salas públicas."""
        return [s.para_dict() for s in self.salas.values() if s.publica]
        
    def validar_acesso(self, codigo: str, senha: Optional[str] = None) -> Tuple[bool, str]:
        """Valida acesso à sala."""
        sala = self.obter_sala(codigo)
        if not sala:
            return False, "Sala não encontrada"
            
        if sala.senha and (not senha or hash_senha(senha) != sala.senha):
            return False, "Senha incorreta"
            
        return True, ""
        
    async def entrar_sala(self, codigo: str, nome: str, sid: str, 
                          senha: Optional[str] = None,
                          como_admin: bool = False) -> Tuple[Optional[Jogador], str]:
        """Adiciona jogador à sala."""
        # Valida acesso
        ok, erro = self.validar_acesso(codigo, senha)
        if not ok:
            return None, erro
            
        # Valida nome
        ok, erro = validar_nome(nome)
        if not ok:
            return None, erro
            
        sala = self.obter_sala(codigo)
        
        # Cria jogador
        papel = Papel.ADMIN if como_admin else Papel.JOGADOR
        jogador = Jogador.criar(nome, sid, papel)

        # Se jogo já começou, entra como espectador
        if sala.sessao.estado != EstadoJogo.LOBBY and papel == Papel.JOGADOR:
            jogador.em_espera = True
        
        sala.sessao.adicionar_jogador(jogador)
        self.jogadores[sid] = codigo
        
        logger.info(f"Jogador {nome} entrou na sala {codigo}")
        return jogador, ""

    async def reconectar_jogador(
        self,
        codigo: str,
        jogador_id: str,
        nome: str,
        sid: str,
        pontuacao: int,
        papel: Papel,
        em_espera: bool
    ) -> Optional[Jogador]:
        """Reconecta jogador removido anteriormente."""
        sala = self.obter_sala(codigo)
        if not sala:
            return None

        # Remove eventual instância duplicada por id
        sala.sessao.remover_jogador_por_id(jogador_id)

        # Se o jogo está em andamento, mantém como espectador
        if sala.sessao.estado != EstadoJogo.LOBBY and papel == Papel.JOGADOR:
            em_espera = True

        jogador = Jogador.reconectar(
            jogador_id=jogador_id,
            nome=nome,
            sid=sid,
            pontuacao=pontuacao,
            papel=papel,
            em_espera=em_espera
        )
        sala.sessao.adicionar_jogador(jogador)
        self.jogadores[sid] = codigo
        return jogador

    async def remover_jogador_por_id(self, codigo: str, jogador_id: str) -> Optional[Jogador]:
        """Remove jogador pelo id (usado em limpeza de reconexão)."""
        sala = self.obter_sala(codigo)
        if not sala:
            return None
        return sala.sessao.remover_jogador_por_id(jogador_id)
        
    async def sair_sala(self, sid: str) -> Tuple[Optional[Sala], Optional[Jogador]]:
        """Remove jogador da sala."""
        codigo = self.jogadores.pop(sid, None)
        if not codigo:
            return None, None
            
        sala = self.salas.get(codigo)
        if not sala:
            return None, None
            
        jogador = sala.sessao.remover_jogador(sid)
        
        # Remove sala se vazia
        if not sala.sessao.jogadores:
            del self.salas[codigo]
            logger.info(f"Sala {codigo} removida (vazia)")
            
        return sala, jogador
        
    # === Gerenciamento de Perguntas ===
    
    def adicionar_pergunta(self, codigo: str, texto: str, opcoes: list, 
                           correta: int, tempo: int = 20) -> bool:
        """Adiciona pergunta à sala."""
        sala = self.obter_sala(codigo)
        if not sala:
            return False
            
        pergunta = Pergunta(
            texto=texto,
            opcoes=opcoes,
            correta=correta,
            tempo=tempo
        )
        sala.sessao.perguntas.append(pergunta)
        return True
        
    def obter_perguntas(self, codigo: str) -> list:
        """Lista perguntas da sala."""
        sala = self.obter_sala(codigo)
        if not sala:
            return []
        return [p.para_dict(mostrar_resposta=True) for p in sala.sessao.perguntas]
        
    def remover_pergunta(self, codigo: str, indice: int) -> bool:
        """Remove pergunta pelo índice."""
        sala = self.obter_sala(codigo)
        if not sala or indice < 0 or indice >= len(sala.sessao.perguntas):
            return False
        sala.sessao.perguntas.pop(indice)
        return True
        
    def limpar_perguntas(self, codigo: str) -> bool:
        """Remove todas as perguntas."""
        sala = self.obter_sala(codigo)
        if not sala:
            return False
        sala.sessao.perguntas.clear()
        return True

    def encerrar_sala(self, codigo: str) -> list:
        """Encerra sala e remove todos os jogadores."""
        sala = self.obter_sala(codigo)
        if not sala:
            return []

        sids = list(sala.sessao.jogadores.keys())
        for sid in sids:
            self.jogadores.pop(sid, None)

        del self.salas[codigo]
        logger.info(f"Sala {codigo} encerrada")
        return sids
