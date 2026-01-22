import sqlite3
import json
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class BancoDados:
    def __init__(self, db_path: str = "trivion.db"):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Inicializa o banco de dados com as tabelas necessárias."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Tabela de Partidas
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS partidas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    vencedor TEXT
                )
                """)

                # Tabela de Resultados
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS resultados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    partida_id INTEGER,
                    jogador_nome TEXT,
                    pontuacao INTEGER,
                    posicao INTEGER,
                    FOREIGN KEY (partida_id) REFERENCES partidas (id)
                )
                """)

                # Tabela de Perguntas
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS perguntas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    texto TEXT UNIQUE,
                    opcoes TEXT,  -- JSON string
                    correta INTEGER,
                    tempo_limite INTEGER
                )
                """)

                conn.commit()
                logger.info("Banco de dados inicializado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao inicializar banco de dados: {e}")

    def salvar_partida(self, resultados: List[Dict[str, Any]]):
        """Salva o histórico da partida e resultados."""
        if not resultados:
            return

        try:
            # Assumindo que resultados está ordenado por posição (vencedor primeiro)
            # Adaptando chaves para o formato retornado por obter_leaderboard ('nome', 'pontuacao')
            primeiro = resultados[0]
            nome_vencedor = primeiro.get('nome') or primeiro.get('nome_jogador') or "N/A"

            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("INSERT INTO partidas (vencedor) VALUES (?)", (nome_vencedor,))
                partida_id = cursor.lastrowid

                for idx, res in enumerate(resultados):
                    nome = res.get('nome') or res.get('nome_jogador')
                    pontos = res.get('pontuacao') if 'pontuacao' in res else res.get('pontuacao_total')

                    cursor.execute("""
                    INSERT INTO resultados (partida_id, jogador_nome, pontuacao, posicao)
                    VALUES (?, ?, ?, ?)
                    """, (partida_id, nome, pontos, idx + 1))

                conn.commit()
                logger.info(f"Partida {partida_id} salva com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao salvar partida: {e}")

    def sincronizar_perguntas(self, perguntas: List[Dict[str, Any]]):
        """Sincroniza perguntas do JSON para o DB. Substitui todas as perguntas existentes."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Limpa tabela antes de inserir para garantir consistência total com JSON
                cursor.execute("DELETE FROM perguntas")

                for p in perguntas:
                    opcoes_json = json.dumps(p['options'])
                    cursor.execute("""
                    INSERT INTO perguntas (texto, opcoes, correta, tempo_limite)
                    VALUES (?, ?, ?, ?)
                    """, (p['text'], opcoes_json, p['correct'], p.get('time_limit', 20)))

                conn.commit()
                logger.info(f"Sincronizadas {len(perguntas)} perguntas no banco de dados.")
        except Exception as e:
            logger.error(f"Erro ao sincronizar perguntas: {e}")

    def obter_perguntas(self) -> List[Dict[str, Any]]:
        """Recupera perguntas do banco de dados."""
        perguntas = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT texto, opcoes, correta, tempo_limite FROM perguntas")
                rows = cursor.fetchall()

                for row in rows:
                    perguntas.append({
                        "text": row[0],
                        "options": json.loads(row[1]),
                        "correct": row[2],
                        "time_limit": row[3]
                    })
        except Exception as e:
            logger.error(f"Erro ao obter perguntas do banco: {e}")

        return perguntas
