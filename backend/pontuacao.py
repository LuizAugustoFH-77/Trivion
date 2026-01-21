"""Trivion - Sistema de Pontuação"""


def calcular_pontuacao(
    esta_correta: bool,
    tempo_resposta_ms: float,
    tempo_maximo_ms: float,
    pontos_base: int = 1000
) -> int:
    """Calcula pontuação baseada na correção e velocidade da resposta."""
    if not esta_correta:
        return 0
    
    tempo_resposta_ms = min(tempo_resposta_ms, tempo_maximo_ms)
    fator_velocidade = 1 - (tempo_resposta_ms / tempo_maximo_ms) / 2
    pontuacao = int(pontos_base * fator_velocidade)
    
    return max(pontuacao, pontos_base // 2)


def calcular_porcentagem_bonus_tempo(tempo_resposta_ms: float, tempo_maximo_ms: float) -> int:
    """Calcula a porcentagem de bônus por velocidade."""
    if tempo_resposta_ms >= tempo_maximo_ms:
        return 0
    
    porcentagem = int((1 - tempo_resposta_ms / tempo_maximo_ms) * 100)
    return max(0, min(100, porcentagem))


def formatar_tempo(segundos: float) -> str:
    """Formata tempo em segundos para exibição."""
    return f"{segundos:.1f}s"
