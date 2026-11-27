"""Escalas ordinais das perguntas suportadas (Stack Overflow Developer Survey 2025)."""

SCALES: dict[str, dict[str, int]] = {
    "AIAcc": {
        "Highly distrust": 1,
        "Somewhat distrust": 2,
        "Neither trust nor distrust": 3,
        "Somewhat trust": 4,
        "Highly trust": 5,
    },
    "AISent": {
        "Very unfavorable": 1,
        "Unfavorable": 2,
        "Indifferent": 3,
        "Favorable": 4,
        "Very favorable": 5,
    },
}

LABEL = "sintético"

# Nome curto (para tabelas) e texto original da pergunta na Stack Overflow Developer Survey 2025.
ROTULO: dict[str, str] = {"AIAcc": "Acurácia da IA", "AISent": "Opinião sobre IA"}
PERGUNTA: dict[str, str] = {
    "AIAcc": "How much do you trust the accuracy of the output from AI tools as part of your development workflow?",
    "AISent": "How favorable is your stance on using AI tools as part of your development workflow?",
}
