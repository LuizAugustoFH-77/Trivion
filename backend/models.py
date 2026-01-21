"""
Trivion - Modelos de Dados
===========================

Este módulo define as estruturas de dados principais do sistema.

CONCEITO DE SISTEMAS DISTRIBUÍDOS: Estado Compartilhado
---------------------------------------------------------
Em sistemas distribuídos, é crucial definir claramente quais dados
são compartilhados entre os nós (clientes) e como eles são sincronizados.
Estas classes representam o "estado" que será replicado para todos os clientes.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
import time
import uuid


class GameState(Enum):
    """
    Máquina de Estados do Jogo
    
    CONCEITO: Consistência de Estado
    Em sistemas distribuídos, todos os clientes devem concordar sobre
    o estado atual do sistema. O servidor atua como "fonte única de verdade"
    (single source of truth), evitando inconsistências.
    
    Estados:
    - LOBBY: Aguardando jogadores entrarem
    - COUNTDOWN: Contagem regressiva antes da pergunta (3-2-1)
    - QUESTION: Pergunta ativa, jogadores podem responder
    - RESULTS: Mostrando resultado da pergunta atual
    - PODIUM: Exibindo TOP 3 com animação
    - LEADERBOARD: Ranking final completo
    - FINISHED: Jogo encerrado
    """
    LOBBY = "lobby"
    COUNTDOWN = "countdown"
    QUESTION = "question"
    RESULTS = "results"
    PODIUM = "podium"
    LEADERBOARD = "leaderboard"
    FINISHED = "finished"


@dataclass
class Player:
    """
    Representa um jogador conectado ao sistema.
    
    CONCEITO: Identificação Única em Sistemas Distribuídos
    Cada cliente precisa de um identificador único (UUID) para que o servidor
    possa rastrear suas ações e estado. O sid (session ID) do Socket.IO
    muda a cada reconexão, mas o player_id permanece constante.
    """
    id: str                              # UUID único do jogador
    name: str                            # Nome exibido
    sid: str                             # Session ID do Socket.IO (pode mudar)
    score: int = 0                       # Pontuação total acumulada
    current_answer: Optional[int] = None # Resposta da pergunta atual (índice 0-3)
    answer_time: Optional[float] = None  # Timestamp de quando respondeu
    answers_history: List[bool] = field(default_factory=list)  # Histórico de acertos
    
    @staticmethod
    def create(name: str, sid: str) -> 'Player':
        """Factory method para criar novo jogador com UUID"""
        return Player(
            id=str(uuid.uuid4()),
            name=name,
            sid=sid
        )
    
    def reset_for_question(self):
        """Limpa resposta atual para nova pergunta"""
        self.current_answer = None
        self.answer_time = None
    
    def submit_answer(self, answer: int) -> float:
        """
        Registra resposta do jogador.
        Retorna o timestamp para cálculo de pontuação.
        """
        self.current_answer = answer
        self.answer_time = time.time()
        return self.answer_time
    
    def add_score(self, points: int, correct: bool):
        """Adiciona pontos e registra no histórico"""
        self.score += points
        self.answers_history.append(correct)
    
    def to_dict(self, include_answer: bool = False) -> dict:
        """Serializa para envio via Socket.IO"""
        data = {
            "id": self.id,
            "name": self.name,
            "score": self.score,
            "has_answered": self.current_answer is not None
        }
        if include_answer:
            data["answer"] = self.current_answer
        return data


@dataclass
class Question:
    """
    Representa uma pergunta do quiz.
    
    O campo 'correct' indica o índice (0-3) da resposta correta.
    O campo 'time_limit' define quantos segundos os jogadores têm para responder.
    """
    text: str                    # Texto da pergunta
    options: List[str]           # Lista de 4 opções de resposta
    correct: int                 # Índice da resposta correta (0-3)
    time_limit: int = 20         # Tempo limite em segundos
    
    def is_correct(self, answer: int) -> bool:
        """Verifica se a resposta está correta"""
        return answer == self.correct
    
    def to_dict(self, hide_answer: bool = True) -> dict:
        """
        Serializa para envio via Socket.IO.
        Por segurança, não envia a resposta correta junto com a pergunta.
        """
        data = {
            "text": self.text,
            "options": self.options,
            "time_limit": self.time_limit
        }
        if not hide_answer:
            data["correct"] = self.correct
        return data


@dataclass 
class QuestionResult:
    """Resultado de uma pergunta para um jogador específico"""
    player_id: str
    player_name: str
    answer: Optional[int]
    correct: bool
    points_earned: int
    response_time_ms: int
    total_score: int


@dataclass
class GameSession:
    """
    Representa uma sessão/sala de jogo.
    
    CONCEITO: Gerenciamento de Estado Centralizado
    O servidor mantém TODO o estado do jogo nesta classe.
    Qualquer mudança aqui é propagada para todos os clientes via broadcast.
    Isso garante CONSISTÊNCIA - todos veem os mesmos dados.
    """
    players: Dict[str, Player] = field(default_factory=dict)  # player_id -> Player
    state: GameState = GameState.LOBBY
    questions: List[Question] = field(default_factory=list)
    current_question_index: int = -1
    question_start_time: Optional[float] = None
    title: str = "Quiz de Sistemas Distribuídos"
    
    def add_player(self, player: Player) -> None:
        """Adiciona jogador à sessão"""
        self.players[player.id] = player
    
    def remove_player(self, player_id: str) -> Optional[Player]:
        """Remove jogador da sessão"""
        return self.players.pop(player_id, None)
    
    def get_player_by_sid(self, sid: str) -> Optional[Player]:
        """Busca jogador pelo session ID do Socket.IO"""
        for player in self.players.values():
            if player.sid == sid:
                return player
        return None
    
    def get_current_question(self) -> Optional[Question]:
        """Retorna pergunta atual ou None"""
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None
    
    def has_more_questions(self) -> bool:
        """Verifica se há mais perguntas"""
        return self.current_question_index < len(self.questions) - 1
    
    def reset_players_for_question(self):
        """Reseta estado de resposta de todos os jogadores"""
        for player in self.players.values():
            player.reset_for_question()
    
    def all_players_answered(self) -> bool:
        """Verifica se todos responderam"""
        return all(p.current_answer is not None for p in self.players.values())
    
    def get_ranking(self) -> List[Player]:
        """Retorna jogadores ordenados por pontuação (maior primeiro)"""
        return sorted(self.players.values(), key=lambda p: p.score, reverse=True)
    
    def get_podium(self) -> List[dict]:
        """Retorna TOP 3 para exibição do pódio"""
        ranking = self.get_ranking()[:3]
        return [
            {"position": i + 1, "name": p.name, "score": p.score}
            for i, p in enumerate(ranking)
        ]
    
    def get_leaderboard(self) -> List[dict]:
        """Retorna ranking completo"""
        ranking = self.get_ranking()
        return [
            {"position": i + 1, "name": p.name, "score": p.score}
            for i, p in enumerate(ranking)
        ]
    
    def to_dict(self) -> dict:
        """Estado completo da sessão para sincronização"""
        return {
            "state": self.state.value,
            "title": self.title,
            "players": [p.to_dict() for p in self.players.values()],
            "player_count": len(self.players),
            "current_question": self.current_question_index + 1,
            "total_questions": len(self.questions)
        }
