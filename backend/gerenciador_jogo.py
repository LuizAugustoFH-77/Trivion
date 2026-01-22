"""Trivion - Gerenciador de Jogo"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Callable, Awaitable
import logging

from .modelos import SessaoJogo, EstadoJogo, Jogador, Pergunta
from .pontuacao import calcular_pontuacao
from .banco import BancoDados

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GerenciadorJogo:
    """Gerenciador central do jogo."""
    
    def __init__(self):
        self.sessao = SessaoJogo()
        self._callback_transmissao: Optional[Callable[[str, dict], Awaitable[None]]] = None
        self._tarefa_timer: Optional[asyncio.Task] = None
        self._lock_resposta = asyncio.Lock()
        self._lock_acao = asyncio.Lock()  # Previne ações simultâneas do admin
        self.banco = BancoDados()
        self._carregar_perguntas()
    
    def definir_callback_transmissao(self, callback: Callable[[str, dict], Awaitable[None]]):
        """Define a função de callback para broadcast."""
        self._callback_transmissao = callback
    
    def _carregar_perguntas(self):
        """Carrega perguntas do arquivo JSON e sincroniza com o DB"""
        try:
            caminho_perguntas = Path(__file__).parent.parent / "data" / "questions.json"
            with open(caminho_perguntas, "r", encoding="utf-8") as f:
                dados = json.load(f)
            
            self.sessao.titulo = dados.get("title", "Quiz")

            # Sincroniza com o banco de dados
            self.banco.sincronizar_perguntas(dados["questions"])

            # Carrega do banco de dados
            perguntas_db = self.banco.obter_perguntas()

            self.sessao.perguntas = [
                Pergunta(
                    texto=q["text"],
                    opcoes=q["options"],
                    correta=q["correct"],
                    tempo_limite=q.get("time_limit", 20)
                )
                for q in perguntas_db
            ]
            logger.info(f"Carregadas {len(self.sessao.perguntas)} perguntas do banco de dados")
        except Exception as e:
            logger.error(f"Erro ao carregar perguntas: {e}")
            self.sessao.perguntas = [
                Pergunta(
                    texto="O que é um sistema distribuído?",
                    opcoes=[
                        "Um único computador potente",
                        "Múltiplos computadores trabalhando juntos",
                        "Um sistema operacional",
                        "Um tipo de banco de dados"
                    ],
                    correta=1
                )
            ]
    
    async def transmitir(self, evento: str, dados: dict):
        """Envia mensagem para todos os clientes conectados."""
        if self._callback_transmissao:
            await self._callback_transmissao(evento, dados)
            logger.info(f"Broadcast: {evento}")
    
    async def adicionar_jogador(self, nome: str, sid: str) -> Jogador:
        """Adiciona novo jogador à sessão ou fila de espera."""
        # Verificação de segurança: palavras ofensivas
        palavras_proibidas = {"admin", "root", "palavrao", "bosta", "merda", "puta"}
        # Verifica palavras inteiras
        palavras_nome = set(nome.lower().split())
        if not palavras_nome.isdisjoint(palavras_proibidas):
             raise ValueError("Nome contém termos não permitidos")

        # Verificação de segurança: impedir duplicatas (strict mode)
        if not self.sessao.nome_eh_unico(nome):
             raise ValueError("Este nome já está em uso. Por favor escolha outro.")

        # Se passou, usa o nome original (já sabemos que é único)
        nome_final = nome
        
        # Se partida está em andamento, coloca na fila de espera
        if self.sessao.estado != EstadoJogo.LOBBY:
            jogador = Jogador.criar(nome_final, sid, em_espera=True)
            self.sessao.adicionar_jogador_espera(jogador)
            
            await self.transmitir("jogador_espera", {
                "jogador": jogador.para_dict(),
                "contagem_espera": len(self.sessao.jogadores_espera)
            })
            
            logger.info(f"Jogador '{nome_final}' adicionado à fila de espera")
            return jogador
        
        # Partida não iniciada, adiciona normalmente
        jogador = Jogador.criar(nome_final, sid)
        self.sessao.adicionar_jogador(jogador)
        
        await self.transmitir("jogador_entrou", {
            "jogador": jogador.para_dict(),
            "jogadores": [p.para_dict() for p in self.sessao.jogadores.values()],
            "contagem": len(self.sessao.jogadores)
        })
        
        logger.info(f"Jogador '{nome_final}' entrou (ID: {jogador.id})")
        return jogador
    
    async def remover_jogador(self, sid: str):
        """Remove jogador desconectado."""
        jogador = self.sessao.obter_jogador_por_sid(sid)
        if jogador:
            em_espera = jogador.em_espera
            self.sessao.remover_jogador(jogador.id)
            
            if em_espera:
                await self.transmitir("jogador_espera_saiu", {
                    "id_jogador": jogador.id,
                    "contagem_espera": len(self.sessao.jogadores_espera)
                })
            else:
                await self.transmitir("jogador_saiu", {
                    "id_jogador": jogador.id,
                    "nome_jogador": jogador.nome,
                    "jogadores": [p.para_dict() for p in self.sessao.jogadores.values()],
                    "contagem": len([p for p in self.sessao.jogadores.values() if not p.em_espera])
                })
            
            logger.info(f"Jogador '{jogador.nome}' saiu")
            
            # Se não restam jogadores ativos durante a partida, volta ao lobby
            jogadores_ativos = [p for p in self.sessao.jogadores.values() if not p.em_espera]
            if len(jogadores_ativos) == 0 and self.sessao.estado != EstadoJogo.LOBBY:
                logger.warning("Todos os jogadores saíram - voltando ao lobby")
                await self.encerrar_jogo()
    
    async def iniciar_jogo(self):
        """Inicia o jogo (chamado pelo admin)."""
        async with self._lock_acao:
            if self.sessao.estado != EstadoJogo.LOBBY:
                logger.warning("Jogo já iniciado")
                return False
            
            jogadores_ativos = [p for p in self.sessao.jogadores.values() if not p.em_espera]
            if len(jogadores_ativos) < 1:
                logger.warning("Nenhum jogador conectado")
                return False
            
            self.sessao.indice_pergunta_atual = -1
            await self._proxima_pergunta()
            return True
    
    async def _proxima_pergunta(self):
        """Avança para a próxima pergunta."""
        if not self.sessao.tem_mais_perguntas():
            await self._exibir_podio()
            return
        
        self.sessao.resetar_jogadores_para_pergunta()
        self.sessao.indice_pergunta_atual += 1
        
        # Contagem 3-2-1
        self.sessao.estado = EstadoJogo.CONTAGEM
        await self.transmitir("contagem", {"segundos": 3})
        await asyncio.sleep(1)
        await self.transmitir("contagem", {"segundos": 2})
        await asyncio.sleep(1)
        await self.transmitir("contagem", {"segundos": 1})
        await asyncio.sleep(1)
        
        # Mostra pergunta
        self.sessao.estado = EstadoJogo.PERGUNTA
        pergunta = self.sessao.obter_pergunta_atual()
        self.sessao.inicio_pergunta_timestamp = time.time()
        
        await self.transmitir("pergunta", {
            "indice": self.sessao.indice_pergunta_atual,
            "total": len(self.sessao.perguntas),
            "pergunta": pergunta.para_dict(esconder_resposta=True)
        })
        
        self._iniciar_timer(pergunta.tempo_limite)
    
    def _iniciar_timer(self, segundos: int):
        """Inicia contagem do timer"""
        if self._tarefa_timer:
            self._tarefa_timer.cancel()
        self._tarefa_timer = asyncio.create_task(self._executar_timer(segundos))
    
    async def _executar_timer(self, segundos: int):
        """Executa o timer da pergunta."""
        try:
            for restante in range(segundos, 0, -1):
                await self.transmitir("temporizador", {"restante": restante})
                await asyncio.sleep(1)
            
            await self.transmitir("temporizador", {"restante": 0})
            await asyncio.sleep(0.5)
            await self._mostrar_resultados()
            
        except asyncio.CancelledError:
            logger.info("Timer cancelado")
    
    async def processar_resposta(self, sid: str, resposta: int, timestamp_cliente: float):
        """Processa resposta de um jogador."""
        async with self._lock_resposta:
            if self.sessao.estado != EstadoJogo.PERGUNTA:
                return
            
            jogador = self.sessao.obter_jogador_por_sid(sid)
            if not jogador or jogador.em_espera:
                return
            
            if jogador.resposta_atual is not None:
                return
            
            jogador.enviar_resposta(resposta)
            
            jogadores_ativos = [p for p in self.sessao.jogadores.values() if not p.em_espera]
            responderam = sum(1 for p in jogadores_ativos if p.resposta_atual is not None)
            
            await self.transmitir("jogador_respondeu", {
                "id_jogador": jogador.id,
                "contagem_respostas": responderam,
                "total_jogadores": len(jogadores_ativos)
            })
            
            logger.info(f"Jogador '{jogador.nome}' respondeu: {resposta}")
            
            if self.sessao.todos_jogadores_responderam():
                if self._tarefa_timer:
                    self._tarefa_timer.cancel()
                await asyncio.sleep(0.5)
                await self._mostrar_resultados()
    
    async def _mostrar_resultados(self):
        """Mostra resultados da pergunta atual."""
        self.sessao.estado = EstadoJogo.RESULTADOS
        pergunta = self.sessao.obter_pergunta_atual()
        
        resultados = []
        for jogador in self.sessao.jogadores.values():
            if jogador.em_espera:
                continue
                
            correta = False
            pontos = 0
            tempo_resposta_ms = 0
            
            if jogador.resposta_atual is not None:
                correta = pergunta.esta_correta(jogador.resposta_atual)
                if jogador.tempo_resposta and self.sessao.inicio_pergunta_timestamp:
                    tempo_resposta_ms = (jogador.tempo_resposta - self.sessao.inicio_pergunta_timestamp) * 1000
                    pontos = calcular_pontuacao(
                        esta_correta=correta,
                        tempo_resposta_ms=tempo_resposta_ms,
                        tempo_maximo_ms=pergunta.tempo_limite * 1000
                    )
            
            jogador.adicionar_pontuacao(pontos, correta)
            
            resultados.append({
                "id_jogador": jogador.id,
                "nome_jogador": jogador.nome,
                "resposta": jogador.resposta_atual,
                "correta": correta,
                "pontos_ganhos": pontos,
                "tempo_resposta_ms": int(tempo_resposta_ms),
                "pontuacao_total": jogador.pontuacao
            })
        
        resultados.sort(key=lambda x: x["pontuacao_total"], reverse=True)
        
        distribuicao_respostas = [0, 0, 0, 0]
        for jogador in self.sessao.jogadores.values():
            if not jogador.em_espera and jogador.resposta_atual is not None:
                distribuicao_respostas[jogador.resposta_atual] += 1
        
        await self.transmitir("resultados", {
            "resposta_correta": pergunta.correta,
            "resultados": resultados,
            "ranking": [{"posicao": i+1, "nome": r["nome_jogador"], "pontuacao": r["pontuacao_total"]} 
                       for i, r in enumerate(resultados)],
            "distribuicao": distribuicao_respostas,
            "tem_mais": self.sessao.tem_mais_perguntas()
        })
        
        logger.info(f"Resultados da pergunta {self.sessao.indice_pergunta_atual + 1} enviados")
    
    async def proxima_pergunta(self):
        """Avança para próxima pergunta (chamado pelo admin)"""
        async with self._lock_acao:
            if self.sessao.estado == EstadoJogo.RESULTADOS:
                await self._proxima_pergunta()
                return True
            return False
    
    async def _exibir_podio(self):
        """Exibe o pódio (TOP 3) e salva a partida."""
        self.sessao.estado = EstadoJogo.PODIO
        
        podio = self.sessao.obter_podio()
        await self.transmitir("podio", {
            "podio": podio
        })
        
        # Salvar partida no banco
        ranking_completo = self.sessao.obter_leaderboard()
        self.banco.salvar_partida(ranking_completo)

        logger.info("Pódio exibido e partida salva")
    
    async def mostrar_ranking(self):
        """Exibe ranking completo (chamado pelo admin)"""
        async with self._lock_acao:
            if self.sessao.estado == EstadoJogo.PODIO:
                self.sessao.estado = EstadoJogo.RANKING
                
                await self.transmitir("ranking", {
                    "ranking": self.sessao.obter_leaderboard()
                })
                
                logger.info("Ranking exibido")
                return True
            return False
    
    async def encerrar_jogo(self):
        """Encerra o jogo a qualquer momento e volta ao lobby."""
        async with self._lock_acao:
            if self._tarefa_timer:
                self._tarefa_timer.cancel()
                self._tarefa_timer = None
            
            # Move jogadores da fila de espera para o jogo
            quantidade_movida = self.sessao.mover_espera_para_jogo()
            if quantidade_movida > 0:
                logger.info(f"{quantidade_movida} jogadores movidos da espera para o jogo")
            
            # Reseta pontuações de todos os jogadores
            for jogador in self.sessao.jogadores.values():
                jogador.pontuacao = 0
                jogador.historico_respostas = []
                jogador.resetar_para_pergunta()
            
            self.sessao.estado = EstadoJogo.LOBBY
            self.sessao.indice_pergunta_atual = -1
            self.sessao.inicio_pergunta_timestamp = None
            
            await self.transmitir("jogo_encerrado", {
                "mensagem": "Jogo encerrado",
                "estado": self.sessao.para_dict()
            })
            
            logger.info("Jogo encerrado")
            return True
    
    def obter_estado_sessao(self) -> dict:
        """Retorna estado atual da sessão"""
        return self.sessao.para_dict()
    
    def obter_estatisticas_respostas(self) -> dict:
        """Retorna estatísticas de respostas (para admin)"""
        jogadores_ativos = [p for p in self.sessao.jogadores.values() if not p.em_espera]
        respondido = sum(1 for p in jogadores_ativos if p.resposta_atual is not None)
        return {
            "respondido": respondido,
            "total": len(jogadores_ativos),
            "esperando": len(jogadores_ativos) - respondido
        }
