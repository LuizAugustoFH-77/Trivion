"""
Trivion - Gerenciador de Jogo
==============================

Este é o coração do sistema distribuído. O GameManager coordena
todas as operações do jogo e garante a sincronização entre clientes.

CONCEITOS DE SISTEMAS DISTRIBUÍDOS IMPLEMENTADOS:
--------------------------------------------------
1. COORDENADOR CENTRAL: O servidor é o único que pode mudar o estado do jogo
2. BROADCAST: Mensagens são enviadas para todos os clientes simultaneamente
3. EXCLUSÃO MÚTUA: Locks protegem operações críticas (respostas simultâneas)
4. CONSISTÊNCIA: Servidor é a "fonte única de verdade"
5. TOLERÂNCIA A FALHAS: Tratamento de desconexões de clientes
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Callable, Awaitable
import logging

from .models import GameSession, GameState, Player, Question
from .scoring import calculate_score

# Configuração de logging para debug
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GameManager:
    """
    Gerenciador central do jogo.
    
    CONCEITO: Coordenador em Sistemas Distribuídos
    Em arquiteturas centralizadas, um nó (o servidor) atua como
    coordenador, tomando todas as decisões e propagando-as para
    os demais nós (clientes). Isso simplifica a consistência mas
    cria um ponto único de falha (single point of failure).
    """
    
    def __init__(self):
        self.session = GameSession()
        self._broadcast_callback: Optional[Callable[[str, dict], Awaitable[None]]] = None
        self._timer_task: Optional[asyncio.Task] = None
        
        # CONCEITO: Exclusão Mútua (Mutual Exclusion)
        # Este lock garante que apenas uma operação crítica
        # (como processar uma resposta) execute por vez,
        # evitando condições de corrida (race conditions).
        self._answer_lock = asyncio.Lock()
        
        # Carrega perguntas do arquivo JSON
        self._load_questions()
    
    def set_broadcast_callback(self, callback: Callable[[str, dict], Awaitable[None]]):
        """
        Define a função de callback para broadcast de mensagens.
        
        CONCEITO: Inversão de Controle / Dependency Injection
        O GameManager não conhece os detalhes do Socket.IO.
        Ele apenas chama o callback quando precisa enviar mensagens.
        """
        self._broadcast_callback = callback
    
    def _load_questions(self):
        """Carrega perguntas do arquivo JSON"""
        try:
            questions_path = Path(__file__).parent.parent / "data" / "questions.json"
            with open(questions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.session.title = data.get("title", "Quiz")
            self.session.questions = [
                Question(
                    text=q["text"],
                    options=q["options"],
                    correct=q["correct"],
                    time_limit=q.get("time_limit", 20)
                )
                for q in data["questions"]
            ]
            logger.info(f"Carregadas {len(self.session.questions)} perguntas")
        except Exception as e:
            logger.error(f"Erro ao carregar perguntas: {e}")
            # Perguntas de fallback
            self.session.questions = [
                Question(
                    text="O que é um sistema distribuído?",
                    options=[
                        "Um único computador potente",
                        "Múltiplos computadores trabalhando juntos",
                        "Um sistema operacional",
                        "Um tipo de banco de dados"
                    ],
                    correct=1
                )
            ]
    
    async def broadcast(self, event: str, data: dict):
        """
        Envia mensagem para TODOS os clientes conectados.
        
        CONCEITO: Broadcast (Difusão)
        Em sistemas distribuídos, broadcast é o envio de uma mensagem
        para todos os nós do sistema. Aqui usamos para garantir que
        todos os jogadores recebam a mesma informação ao mesmo tempo.
        """
        if self._broadcast_callback:
            await self._broadcast_callback(event, data)
            logger.info(f"Broadcast: {event}")
    
    async def add_player(self, name: str, sid: str) -> Player:
        """
        Adiciona novo jogador à sessão.
        
        CONCEITO: Registro de Clientes
        Em sistemas distribuídos, novos nós devem se "registrar"
        com o coordenador para participar do sistema.
        """
        player = Player.create(name, sid)
        self.session.add_player(player)
        
        # Notifica todos sobre o novo jogador
        await self.broadcast("player_joined", {
            "player": player.to_dict(),
            "players": [p.to_dict() for p in self.session.players.values()],
            "count": len(self.session.players)
        })
        
        logger.info(f"Jogador '{name}' entrou (ID: {player.id})")
        return player
    
    async def remove_player(self, sid: str):
        """
        Remove jogador desconectado.
        
        CONCEITO: Tolerância a Falhas
        Sistemas distribuídos devem lidar com falhas de nós.
        Quando um cliente desconecta, removemos seu estado
        e notificamos os demais.
        """
        player = self.session.get_player_by_sid(sid)
        if player:
            self.session.remove_player(player.id)
            await self.broadcast("player_left", {
                "player_id": player.id,
                "player_name": player.name,
                "players": [p.to_dict() for p in self.session.players.values()],
                "count": len(self.session.players)
            })
            logger.info(f"Jogador '{player.name}' saiu")
    
    async def start_game(self):
        """
        Inicia o jogo (chamado pelo admin).
        
        CONCEITO: Coordenação de Início
        O coordenador decide quando o jogo começa, garantindo
        que todos os clientes iniciem no mesmo momento.
        """
        if self.session.state != GameState.LOBBY:
            logger.warning("Jogo já iniciado")
            return
        
        if len(self.session.players) < 1:
            logger.warning("Nenhum jogador conectado")
            return
        
        self.session.current_question_index = -1
        await self._next_question()
    
    async def _next_question(self):
        """
        Avança para a próxima pergunta.
        
        CONCEITO: Sincronização de Estado
        Todos os clientes recebem a mesma pergunta no mesmo momento.
        O servidor controla o tempo, garantindo sincronização.
        """
        if not self.session.has_more_questions():
            await self._show_podium()
            return
        
        # Reseta estado dos jogadores
        self.session.reset_players_for_question()
        self.session.current_question_index += 1
        
        # Countdown 3-2-1
        self.session.state = GameState.COUNTDOWN
        await self.broadcast("countdown", {"seconds": 3})
        await asyncio.sleep(1)
        await self.broadcast("countdown", {"seconds": 2})
        await asyncio.sleep(1)
        await self.broadcast("countdown", {"seconds": 1})
        await asyncio.sleep(1)
        
        # Mostra pergunta
        self.session.state = GameState.QUESTION
        question = self.session.get_current_question()
        self.session.question_start_time = time.time()
        
        await self.broadcast("question", {
            "index": self.session.current_question_index,
            "total": len(self.session.questions),
            "question": question.to_dict(hide_answer=True)
        })
        
        # Inicia timer
        self._start_timer(question.time_limit)
    
    def _start_timer(self, seconds: int):
        """Inicia countdown do timer"""
        if self._timer_task:
            self._timer_task.cancel()
        self._timer_task = asyncio.create_task(self._run_timer(seconds))
    
    async def _run_timer(self, seconds: int):
        """
        Executa o timer da pergunta.
        
        CONCEITO: Relógio do Sistema
        O servidor mantém o tempo oficial do jogo.
        Os clientes recebem atualizações do timer, mas não
        podem manipulá-lo (segurança).
        """
        try:
            for remaining in range(seconds, 0, -1):
                await self.broadcast("timer", {"remaining": remaining})
                await asyncio.sleep(1)
            
            # Tempo esgotado
            await self.broadcast("timer", {"remaining": 0})
            await asyncio.sleep(0.5)
            await self._show_results()
            
        except asyncio.CancelledError:
            logger.info("Timer cancelado")
    
    async def handle_answer(self, sid: str, answer: int, client_timestamp: float):
        """
        Processa resposta de um jogador.
        
        CONCEITO: Exclusão Mútua (Mutual Exclusion)
        O lock garante que respostas simultâneas de diferentes
        jogadores sejam processadas uma por vez, evitando
        inconsistências no estado.
        
        CONCEITO: Ordenação Causal
        Usamos o timestamp do servidor para determinar quem
        respondeu primeiro, não confiando no timestamp do cliente.
        """
        async with self._answer_lock:  # EXCLUSÃO MÚTUA
            if self.session.state != GameState.QUESTION:
                logger.warning("Resposta recebida fora do tempo de pergunta")
                return
            
            player = self.session.get_player_by_sid(sid)
            if not player:
                logger.warning(f"Jogador não encontrado: {sid}")
                return
            
            if player.current_answer is not None:
                logger.warning(f"Jogador {player.name} já respondeu")
                return
            
            # Registra resposta com timestamp do SERVIDOR
            player.submit_answer(answer)
            
            # Notifica que jogador respondeu (sem revelar a resposta)
            await self.broadcast("player_answered", {
                "player_id": player.id,
                "answered_count": sum(1 for p in self.session.players.values() if p.current_answer is not None),
                "total_players": len(self.session.players)
            })
            
            logger.info(f"Jogador '{player.name}' respondeu: {answer}")
            
            # Se todos responderam, mostra resultados imediatamente
            if self.session.all_players_answered():
                if self._timer_task:
                    self._timer_task.cancel()
                await asyncio.sleep(0.5)
                await self._show_results()
    
    async def _show_results(self):
        """
        Mostra resultados da pergunta atual.
        
        CONCEITO: Consistência de Estado
        Todos os clientes recebem os mesmos resultados calculados
        pelo servidor, garantindo que todos vejam o mesmo placar.
        """
        self.session.state = GameState.RESULTS
        question = self.session.get_current_question()
        
        # Calcula pontuação de cada jogador
        results = []
        for player in self.session.players.values():
            is_correct = False
            points = 0
            response_time_ms = 0
            
            if player.current_answer is not None:
                is_correct = question.is_correct(player.current_answer)
                if player.answer_time and self.session.question_start_time:
                    response_time_ms = (player.answer_time - self.session.question_start_time) * 1000
                    points = calculate_score(
                        is_correct=is_correct,
                        response_time_ms=response_time_ms,
                        max_time_ms=question.time_limit * 1000
                    )
            
            player.add_score(points, is_correct)
            
            results.append({
                "player_id": player.id,
                "player_name": player.name,
                "answer": player.current_answer,
                "correct": is_correct,
                "points_earned": points,
                "response_time_ms": int(response_time_ms),
                "total_score": player.score
            })
        
        # Ordena por pontuação para ranking parcial
        results.sort(key=lambda x: x["total_score"], reverse=True)
        
        # Estatísticas de respostas
        answer_distribution = [0, 0, 0, 0]
        for player in self.session.players.values():
            if player.current_answer is not None:
                answer_distribution[player.current_answer] += 1
        
        await self.broadcast("results", {
            "correct_answer": question.correct,
            "results": results,
            "ranking": [{"position": i+1, "name": r["player_name"], "score": r["total_score"]} 
                       for i, r in enumerate(results)],
            "distribution": answer_distribution,
            "has_more": self.session.has_more_questions()
        })
        
        logger.info(f"Resultados da pergunta {self.session.current_question_index + 1} enviados")
    
    async def next_question(self):
        """Avança para próxima pergunta (chamado pelo admin)"""
        if self.session.state == GameState.RESULTS:
            await self._next_question()
    
    async def _show_podium(self):
        """
        Exibe o pódio (TOP 3).
        
        CONCEITO: Agregação de Resultados
        O servidor agrega os dados de todos os clientes
        para calcular o ranking final.
        """
        self.session.state = GameState.PODIUM
        
        await self.broadcast("podium", {
            "podium": self.session.get_podium()
        })
        
        logger.info("Pódio exibido")
    
    async def show_leaderboard(self):
        """Exibe leaderboard completo (chamado pelo admin)"""
        if self.session.state == GameState.PODIUM:
            self.session.state = GameState.LEADERBOARD
            
            await self.broadcast("leaderboard", {
                "leaderboard": self.session.get_leaderboard()
            })
            
            logger.info("Leaderboard exibido")
    
    async def reset_game(self):
        """
        Reinicia o jogo.
        
        CONCEITO: Reset de Estado
        Limpa todo o estado distribuído e notifica clientes
        para retornarem ao estado inicial (LOBBY).
        """
        if self._timer_task:
            self._timer_task.cancel()
        
        # Mantém jogadores mas reseta pontuações
        for player in self.session.players.values():
            player.score = 0
            player.answers_history = []
            player.reset_for_question()
        
        self.session.state = GameState.LOBBY
        self.session.current_question_index = -1
        self.session.question_start_time = None
        
        await self.broadcast("reset", {
            "message": "Jogo reiniciado",
            "state": self.session.to_dict()
        })
        
        logger.info("Jogo reiniciado")
    
    def get_session_state(self) -> dict:
        """Retorna estado atual da sessão"""
        return self.session.to_dict()
    
    def get_answer_stats(self) -> dict:
        """Retorna estatísticas de respostas (para admin)"""
        answered = sum(1 for p in self.session.players.values() if p.current_answer is not None)
        return {
            "answered": answered,
            "total": len(self.session.players),
            "waiting": len(self.session.players) - answered
        }
