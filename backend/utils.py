"""Trivion - Utilidades

Funções auxiliares de validação e cálculo de pontuação.
"""

from typing import Tuple

def validar_nome(nome: str) -> Tuple[bool, str]:
    """Valida nome de jogador."""
    if nome is None:
        return False, "Nome é obrigatório"

    nome = nome.strip()

    if len(nome) < 1:
        return False, "Nome é obrigatório"

    if len(nome) > 15:
        return False, "Nome deve ter no máximo 15 caracteres"

    return True, ""


def calcular_pontuacao(correta: bool, tempo_ms: float, tempo_max_ms: float) -> int:
    """Calcula pontuação baseada na correção e velocidade."""
    if not correta:
        return 0
    
    tempo_ms = min(tempo_ms, tempo_max_ms)
    fator = 1 - (tempo_ms / tempo_max_ms) / 2
    pontos = int(1000 * fator)
    
    return max(pontos, 500)  # Mínimo 500 pontos se acertou
