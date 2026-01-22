"""Trivion - Modelos de Dados"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
import time
import uuid


class EstadoJogo(Enum):
    """Máquina de Estados do Jogo"""
    LOBBY = "lobby"
    CONTAGEM = "contagem"
    PERGUNTA = "pergunta"
    RESULTADOS = "resultados"
    PODIO = "podio"
    RANKING = "ranking"
    FINALIZADO = "finalizado"


@dataclass
class Jogador:
    """Representa um jogador conectado ao sistema."""
    id: str
    nome: str
    id_socket: str
    pontuacao: int = 0
    resposta_atual: Optional[int] = None
    tempo_resposta: Optional[float] = None
    historico_respostas: List[bool] = field(default_factory=list)
    em_espera: bool = False  # True se entrou durante partida ativa
    
    @staticmethod
    def criar(nome: str, id_socket: str, em_espera: bool = False) -> 'Jogador':
        """Cria novo jogador com UUID"""
        return Jogador(
            id=str(uuid.uuid4()),
            nome=nome,
            id_socket=id_socket,
            em_espera=em_espera
        )
    
    def resetar_para_pergunta(self):
        """Limpa resposta atual para nova pergunta"""
        self.resposta_atual = None
        self.tempo_resposta = None
    
    def enviar_resposta(self, resposta: int) -> float:
        """Registra resposta do jogador."""
        self.resposta_atual = resposta
        self.tempo_resposta = time.time()
        return self.tempo_resposta
    
    def adicionar_pontuacao(self, pontos: int, correta: bool):
        """Adiciona pontos e registra no histórico"""
        self.pontuacao += pontos
        self.historico_respostas.append(correta)
    
    def para_dict(self, incluir_resposta: bool = False) -> dict:
        """Serializa para envio via Socket.IO"""
        dados = {
            "id": self.id,
            "nome": self.nome,
            "pontuacao": self.pontuacao,
            "respondeu": self.resposta_atual is not None,
            "em_espera": self.em_espera
        }
        if incluir_resposta:
            dados["resposta"] = self.resposta_atual
        return dados


@dataclass
class Pergunta:
    """Representa uma pergunta do quiz."""
    texto: str
    opcoes: List[str]
    correta: int
    tempo_limite: int = 20
    
    def esta_correta(self, resposta: int) -> bool:
        """Verifica se a resposta está correta"""
        return resposta == self.correta
    
    def para_dict(self, esconder_resposta: bool = True) -> dict:
        """Serializa para envio via Socket.IO."""
        dados = {
            "texto": self.texto,
            "opcoes": self.opcoes,
            "tempo_limite": self.tempo_limite
        }
        if not esconder_resposta:
            dados["correta"] = self.correta
        return dados


@dataclass
class SessaoJogo:
    """Representa uma sessão/sala de jogo."""
    jogadores: Dict[str, Jogador] = field(default_factory=dict)
    jogadores_espera: Dict[str, Jogador] = field(default_factory=dict)
    estado: EstadoJogo = EstadoJogo.LOBBY
    perguntas: List[Pergunta] = field(default_factory=list)
    indice_pergunta_atual: int = -1
    inicio_pergunta_timestamp: Optional[float] = None
    titulo: str = "Quiz de Sistemas Distribuídos"
    
    def adicionar_jogador(self, jogador: Jogador) -> None:
        """Adiciona jogador à sessão"""
        self.jogadores[jogador.id] = jogador
    
    def adicionar_jogador_espera(self, jogador: Jogador) -> None:
        """Adiciona jogador à fila de espera"""
        jogador.em_espera = True
        self.jogadores_espera[jogador.id] = jogador
    
    def mover_espera_para_jogo(self) -> int:
        """Move todos os jogadores da espera para o jogo. Retorna quantidade movida."""
        quantidade = len(self.jogadores_espera)
        for jogador in self.jogadores_espera.values():
            jogador.em_espera = False
            jogador.pontuacao = 0
            jogador.historico_respostas = []
            self.jogadores[jogador.id] = jogador
        self.jogadores_espera.clear()
        return quantidade
    
    def remover_jogador(self, id_jogador: str) -> Optional[Jogador]:
        """Remove jogador da sessão ou da espera"""
        if id_jogador in self.jogadores:
            return self.jogadores.pop(id_jogador)
        if id_jogador in self.jogadores_espera:
            return self.jogadores_espera.pop(id_jogador)
        return None
    
    def obter_jogador_por_sid(self, sid: str) -> Optional[Jogador]:
        """Busca jogador pelo session ID do Socket.IO"""
        for jogador in self.jogadores.values():
            if jogador.id_socket == sid:
                return jogador
        for jogador in self.jogadores_espera.values():
            if jogador.id_socket == sid:
                return jogador
        return None
    
    def nome_eh_unico(self, nome: str) -> bool:
        """Verifica se o nome já está em uso (na sessão ou espera)."""
        nomes_existentes = {j.nome.lower() for j in self.jogadores.values()}
        nomes_existentes |= {j.nome.lower() for j in self.jogadores_espera.values()}

        return nome.lower() not in nomes_existentes

    def nome_disponivel(self, nome: str) -> str:
        """Retorna nome único, adicionando sufixo se necessário."""
        nomes_existentes = {j.nome for j in self.jogadores.values()}
        nomes_existentes |= {j.nome for j in self.jogadores_espera.values()}
        
        if nome not in nomes_existentes:
            return nome
        
        contador = 2
        while f"{nome} ({contador})" in nomes_existentes:
            contador += 1
        return f"{nome} ({contador})"
    
    def obter_pergunta_atual(self) -> Optional[Pergunta]:
        """Retorna pergunta atual ou None"""
        if 0 <= self.indice_pergunta_atual < len(self.perguntas):
            return self.perguntas[self.indice_pergunta_atual]
        return None
    
    def tem_mais_perguntas(self) -> bool:
        """Verifica se há mais perguntas"""
        return self.indice_pergunta_atual < len(self.perguntas) - 1
    
    def resetar_jogadores_para_pergunta(self):
        """Reseta estado de resposta de todos os jogadores"""
        for jogador in self.jogadores.values():
            jogador.resetar_para_pergunta()
    
    def todos_jogadores_responderam(self) -> bool:
        """Verifica se todos responderam"""
        jogadores_ativos = [p for p in self.jogadores.values() if not p.em_espera]
        return all(p.resposta_atual is not None for p in jogadores_ativos)
    
    def obter_ranking(self) -> List[Jogador]:
        """Retorna jogadores ordenados por pontuação (maior primeiro)"""
        jogadores_ativos = [p for p in self.jogadores.values() if not p.em_espera]
        return sorted(jogadores_ativos, key=lambda p: p.pontuacao, reverse=True)
    
    def obter_podio(self) -> List[dict]:
        """Retorna TOP 3 para exibição do pódio"""
        ranking = self.obter_ranking()[:3]
        return [
            {"posicao": i + 1, "nome": p.nome, "pontuacao": p.pontuacao}
            for i, p in enumerate(ranking)
        ]
    
    def obter_leaderboard(self) -> List[dict]:
        """Retorna ranking completo"""
        ranking = self.obter_ranking()
        return [
            {"posicao": i + 1, "nome": p.nome, "pontuacao": p.pontuacao}
            for i, p in enumerate(ranking)
        ]
    
    def para_dict(self) -> dict:
        """Estado completo da sessão para sincronização"""
        return {
            "estado": self.estado.value,
            "titulo": self.titulo,
            "jogadores": [p.para_dict() for p in self.jogadores.values() if not p.em_espera],
            "jogadores_espera": [p.para_dict() for p in self.jogadores_espera.values()],
            "contagem_jogadores": len([p for p in self.jogadores.values() if not p.em_espera]),
            "contagem_espera": len(self.jogadores_espera),
            "pergunta_atual": self.indice_pergunta_atual + 1,
            "total_perguntas": len(self.perguntas)
        }
