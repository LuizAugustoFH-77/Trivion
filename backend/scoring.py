"""
Trivion - Sistema de Pontuação
===============================

Este módulo implementa o cálculo de pontuação estilo Kahoot.

CONCEITO DE SISTEMAS DISTRIBUÍDOS: Ordenação de Eventos
---------------------------------------------------------
Em sistemas distribuídos, a ordem dos eventos importa. Aqui usamos
timestamps para determinar quem respondeu mais rápido. O servidor
é a autoridade final sobre o tempo, evitando que clientes manipulem
seus próprios timestamps (segurança).
"""


def calculate_score(
    is_correct: bool,
    response_time_ms: float,
    max_time_ms: float,
    base_points: int = 1000
) -> int:
    """
    Calcula pontuação baseada na correção e velocidade da resposta.
    
    Fórmula inspirada no Kahoot:
    - Resposta errada: 0 pontos
    - Resposta correta: base_points * fator_velocidade
    - Fator velocidade: 1 - (tempo_resposta / tempo_maximo) / 2
    - Isso resulta em 50% a 100% dos pontos base
    
    Args:
        is_correct: Se a resposta está correta
        response_time_ms: Tempo de resposta em milissegundos
        max_time_ms: Tempo máximo permitido em milissegundos
        base_points: Pontuação base para resposta correta
        
    Returns:
        Pontuação calculada (0 a base_points)
        
    CONCEITO: Justiça em Sistemas Distribuídos
    O cálculo considera a latência implicitamente - jogadores com
    conexões mais lentas podem ser prejudicados. Em um sistema mais
    robusto, compensaríamos a latência de rede, mas para fins
    didáticos mantemos a simplicidade.
    """
    if not is_correct:
        return 0
    
    # Garante que o tempo não exceda o máximo
    response_time_ms = min(response_time_ms, max_time_ms)
    
    # Fator de velocidade: quanto mais rápido, maior (0.5 a 1.0)
    speed_factor = 1 - (response_time_ms / max_time_ms) / 2
    
    # Calcula pontuação final
    score = int(base_points * speed_factor)
    
    # Garante mínimo de 50% dos pontos para resposta correta
    return max(score, base_points // 2)


def calculate_time_bonus_percentage(response_time_ms: float, max_time_ms: float) -> int:
    """
    Calcula a porcentagem de bônus por velocidade (para exibição).
    
    Returns:
        Porcentagem de 0 a 100
    """
    if response_time_ms >= max_time_ms:
        return 0
    
    percentage = int((1 - response_time_ms / max_time_ms) * 100)
    return max(0, min(100, percentage))


def format_time(seconds: float) -> str:
    """Formata tempo em segundos para exibição (ex: '2.5s')"""
    return f"{seconds:.1f}s"


def get_streak_multiplier(consecutive_correct: int) -> float:
    """
    Multiplicador de sequência de acertos (feature opcional).
    
    Em uma implementação mais completa, jogadores que acertam
    várias perguntas seguidas poderiam ganhar bônus.
    
    Args:
        consecutive_correct: Número de acertos consecutivos
        
    Returns:
        Multiplicador (1.0 a 2.0)
    """
    if consecutive_correct < 2:
        return 1.0
    elif consecutive_correct < 4:
        return 1.25
    elif consecutive_correct < 6:
        return 1.5
    else:
        return 2.0
