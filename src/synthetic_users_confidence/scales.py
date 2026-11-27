"""Escalas ordinais das perguntas ativas.

O padrão são as perguntas da Stack Overflow Developer Survey 2025. Ao receber um dicionário,
`importar_dados` troca as perguntas ativas pelas do questionário importado (veja `questionario.py`).
"""

from __future__ import annotations

import copy

LABEL = "sintético"

# Dicionário da Stack Overflow Developer Survey 2025, no mesmo formato que o usuário passa a importar_dados.
PRESET_SO_2025: dict = {
    "nome": "stackoverflow-2025",
    "id": "ResponseId",
    "estratos": ["Age", "DevType", "Employment"],
    "separador_multiplo": ";",
    "perguntas": {
        "AIAcc": {
            "rotulo": "Acurácia da IA",
            "texto": "How much do you trust the accuracy of the output from AI tools as part of your development workflow?",
            "escala": {
                "Highly distrust": 1,
                "Somewhat distrust": 2,
                "Neither trust nor distrust": 3,
                "Somewhat trust": 4,
                "Highly trust": 5,
            },
        },
        "AISent": {
            "rotulo": "Opinião sobre IA",
            "texto": "How favorable is your stance on using AI tools as part of your development workflow?",
            "escala": {
                "Very unfavorable": 1,
                "Unfavorable": 2,
                "Indifferent": 3,
                "Favorable": 4,
                "Very favorable": 5,
            },
        },
    },
}

# Perguntas ativas. São dicionários mutáveis de propósito: todo módulo que importou `SCALES` passa a ver a troca.
SCALES: dict[str, dict[str, int]] = {}
ROTULO: dict[str, str] = {}  # nome curto, para tabelas
PERGUNTA: dict[str, str] = {}  # texto original da pergunta


def ativar(dicionario: dict) -> None:
    """Troca as perguntas ativas pelas do dicionário (já validado)."""
    perguntas = copy.deepcopy(dicionario["perguntas"])
    for d in (SCALES, ROTULO, PERGUNTA):
        d.clear()
    for q, p in perguntas.items():
        SCALES[q] = dict(p["escala"])
        ROTULO[q] = p.get("rotulo") or q
        PERGUNTA[q] = p.get("texto") or q


def restaurar() -> None:
    ativar(PRESET_SO_2025)


restaurar()
