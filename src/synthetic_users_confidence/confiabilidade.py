"""Confiabilidade do usuário sintético: nível provisório (baixa, média, alta) e frase curta.

Os cortes são PROVISÓRIOS: foram definidos depois de ver a primeira rodada e não foram calibrados.
O PRD pede uma regra simples sobre os três sinais (dispersão, suporte na base, acerto histórico),
a calibrar na etapa 2; esta é só uma leitura exploratória e não substitui os sinais.
"""

from __future__ import annotations

DIF_MEDIA_BAIXA = 0.5   # diferença de média acima disso: baixa
VARIEDADE_BAIXA = 0.30  # variância sintética / humana abaixo disso: baixa
DIF_MEDIA_ALTA = 0.1    # diferença de média abaixo disso (com o resto): alta
VARIEDADE_ALTA = 0.70

REGRA = (
    f"Baixa: média a mais de {str(DIF_MEDIA_BAIXA).replace('.', ',')} ponto da real, ou variação abaixo de {VARIEDADE_BAIXA:.0%} da humana. "
    f"Alta: média a menos de {str(DIF_MEDIA_ALTA).replace('.', ',')} ponto, variação de pelo menos {VARIEDADE_ALTA:.0%}, melhor que perguntar "
    "a qualquer um e os três sinais calculados. Média: o resto. Sem os três sinais, não passa de média."
)
LIMITE = "cortes provisórios, definidos depois de ver a primeira rodada e sem calibração; não substitui os três sinais"

ROTULO_NIVEL = {"baixa": "Baixa", "média": "Média", "alta": "Alta"}


def nivel(dif_media: float, razao_variancia: float | None, melhor_que_geral: bool, sinais_completos: bool) -> str:
    """Nível provisório. Sem os três sinais calculados, nunca passa de média: ausência de sinal não é sinal bom."""
    v = razao_variancia if razao_variancia is not None else 0.0
    if abs(dif_media) > DIF_MEDIA_BAIXA or v < VARIEDADE_BAIXA:
        return "baixa"
    if abs(dif_media) < DIF_MEDIA_ALTA and v >= VARIEDADE_ALTA and melhor_que_geral and sinais_completos:
        return "alta"
    return "média"


def limitada_por_sinais(dif_media: float, razao_variancia: float | None, melhor_que_geral: bool) -> bool:
    """True quando os números já seriam de nível alto e só faltam os outros sinais para chegar lá."""
    v = razao_variancia if razao_variancia is not None else 0.0
    return abs(dif_media) < DIF_MEDIA_ALTA and v >= VARIEDADE_ALTA and melhor_que_geral


def _n(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def insight(dif_media: float, margem: float, razao_variancia: float | None, p_value: float, nivel_: str,
            limitada: bool = False, faltam: int = 2) -> str:
    """Frase curta sobre o porquê do nível (cabe numa célula estreita)."""
    if abs(dif_media) <= margem:
        media = "Média parecida."
    else:
        media = f"Mais {'positivo' if dif_media > 0 else 'negativo'} ({'+' if dif_media > 0 else '-'}{_n(abs(dif_media))})."
    v = razao_variancia or 0.0
    var = "Quase sem variação." if v < VARIEDADE_BAIXA else "Menos variação." if v < 0.7 else "Variação parecida."
    sig = "Diferença real." if p_value < 0.05 else "Diferença não provada."
    fecho = {"baixa": "Não usar para este grupo.", "média": "Só ponto de partida.", "alta": "Confiável para este uso."}[nivel_]
    if nivel_ == "média" and limitada:
        fecho = f"Números bons; falta{'m' if faltam > 1 else ''} {faltam} dos 3 sinais para ser Alta."
    return f"{media} {var} {sig} {fecho}"
