"""Trivion - Modelos de Dados

Dataclasses para representar entidades do jogo.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
import uuid


class EstadoJogo(str, Enum):
    """Estados possíveis do jogo."""
    LOBBY = "lobby"
    CONTAGEM = "contagem"
    PERGUNTA = "pergunta"
    RESULTADOS = "resultados"
    PODIO = "podio"
    FINALIZADO = "finalizado"


class Papel(str, Enum):
    """Papel do usuário na sala."""
    JOGADOR = "jogador"
    ADMIN = "admin"


@dataclass
class Jogador:
    """Representa um jogador."""
    id: str
    nome: str
    sid: str
    pontuacao: int = 0
    resposta_atual: Optional[int] = None
    tempo_resposta: Optional[float] = None
    pontos_ultima_pergunta: int = 0
    papel: Papel = Papel.JOGADOR
    em_espera: bool = False
    
    @classmethod
    def criar(cls, nome: str, sid: str, papel: Papel = Papel.JOGADOR):
        return cls(
            id=str(uuid.uuid4())[:8],
            nome=nome,
            sid=sid,
            papel=papel
        )

    @classmethod
    def reconectar(
        cls,
        jogador_id: str,
        nome: str,
        sid: str,
        pontuacao: int = 0,
        papel: Papel = Papel.JOGADOR,
        em_espera: bool = False
    ):
        return cls(
            id=jogador_id,
            nome=nome,
            sid=sid,
            pontuacao=pontuacao,
            papel=papel,
            em_espera=em_espera
        )
    
    def resetar(self):
        """Reseta para nova pergunta."""
        self.resposta_atual = None
        self.tempo_resposta = None
        self.pontos_ultima_pergunta = 0
        
    def para_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "pontuacao": self.pontuacao,
            "pontos_ultima_pergunta": self.pontos_ultima_pergunta,
            "papel": self.papel.value,
            "respondeu": self.resposta_atual is not None,
            "em_espera": self.em_espera
        }


@dataclass
class Pergunta:
    """Representa uma pergunta do quiz."""
    texto: str
    opcoes: List[str]
    correta: int
    tempo: int = 20
    
    def para_dict(self, mostrar_resposta: bool = False):
        d = {
            "texto": self.texto,
            "opcoes": self.opcoes,
            "tempo": self.tempo
        }
        if mostrar_resposta:
            d["correta"] = self.correta
        return d


@dataclass
class Sessao:
    """Sessão de jogo de uma sala."""
    jogadores: Dict[str, Jogador] = field(default_factory=dict)
    perguntas: List[Pergunta] = field(default_factory=list)
    estado: EstadoJogo = EstadoJogo.LOBBY
    pergunta_atual: int = -1
    tempo_inicio: Optional[float] = None
    
    def adicionar_jogador(self, jogador: Jogador):
        self.jogadores[jogador.sid] = jogador
        
    def remover_jogador(self, sid: str) -> Optional[Jogador]:
        return self.jogadores.pop(sid, None)
        
    def obter_jogador(self, sid: str) -> Optional[Jogador]:
        return self.jogadores.get(sid)

    def obter_jogador_por_id(self, jogador_id: str) -> Optional[Jogador]:
        for jogador in self.jogadores.values():
            if jogador.id == jogador_id:
                return jogador
        return None

    def remover_jogador_por_id(self, jogador_id: str) -> Optional[Jogador]:
        for sid, jogador in list(self.jogadores.items()):
            if jogador.id == jogador_id:
                return self.jogadores.pop(sid, None)
        return None
        
    def obter_pergunta(self) -> Optional[Pergunta]:
        if 0 <= self.pergunta_atual < len(self.perguntas):
            return self.perguntas[self.pergunta_atual]
        return None
        
    def tem_mais_perguntas(self) -> bool:
        return self.pergunta_atual < len(self.perguntas) - 1
        
    def resetar_respostas(self):
        for j in self.jogadores.values():
            j.resetar()
            
    def todos_responderam(self) -> bool:
        jogadores_ativos = [j for j in self.jogadores.values() 
                          if j.papel == Papel.JOGADOR and not j.em_espera]
        return all(j.resposta_atual is not None for j in jogadores_ativos)
        
    def ranking(self) -> List[Jogador]:
        jogadores = [j for j in self.jogadores.values() 
                    if j.papel == Papel.JOGADOR]
        return sorted(jogadores, key=lambda j: j.pontuacao, reverse=True)
        
    def para_dict(self):
        return {
            "estado": self.estado.value,
            "jogadores": [j.para_dict() for j in self.jogadores.values()],
            "pergunta_atual": self.pergunta_atual,
            "total_perguntas": len(self.perguntas),
            "pergunta": self.obter_pergunta().para_dict() if self.obter_pergunta() else None
        }


@dataclass
class Sala:
    """Representa uma sala de jogo."""
    id: str
    nome: str
    codigo: str
    dono_sid: str
    sessao: Sessao = field(default_factory=Sessao)
    publica: bool = True
    senha: Optional[str] = None
    
    def para_dict(self):
        return {
            "codigo": self.codigo,
            "nome": self.nome,
            "publica": self.publica,
            "jogadores": len(self.sessao.jogadores),
            "estado": self.sessao.estado.value
        }
