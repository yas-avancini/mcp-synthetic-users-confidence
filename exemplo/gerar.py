"""Gera o exemplo: respostas humanas FICTÍCIAS e dois usuários sintéticos prontos.

Nenhum dado é real. Semente fixa: rodar de novo produz os mesmos arquivos.

    python exemplo/gerar.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

AQUI = Path(__file__).parent
SEMENTE = 2026
PESSOAS = 600

CARGOS = {"Analista": 0.45, "Gerente": 0.35, "Diretoria": 0.20}
PORTES = {"Pequena": 0.4, "Média": 0.35, "Grande": 0.25}

CONFIA = ["Desconfio muito", "Desconfio um pouco", "Nem confio nem desconfio", "Confio um pouco", "Confio muito"]
RECOMENDA = ["Muito improvável", "Improvável", "Talvez", "Provável", "Muito provável"]

# Distribuição das respostas (pontos 1 a 5) por cargo: quem decide é mais cético com a IA.
P_CONFIA = {
    "Analista": [0.05, 0.15, 0.25, 0.40, 0.15],
    "Gerente": [0.10, 0.25, 0.30, 0.28, 0.07],
    "Diretoria": [0.20, 0.30, 0.25, 0.20, 0.05],
}
P_RECOMENDA = {
    "Analista": [0.05, 0.10, 0.25, 0.40, 0.20],
    "Gerente": [0.08, 0.17, 0.30, 0.33, 0.12],
    "Diretoria": [0.15, 0.25, 0.30, 0.22, 0.08],
}
NAO_SEI = 0.04  # parte das pessoas responde "Não sei": fica fora da escala e aparece em `cobertura`

DICIONARIO = {
    "nome": "exemplo-ficticio-ia-no-trabalho",
    "descricao": "Pesquisa fictícia sobre uso de IA no trabalho, gerada por exemplo/gerar.py",
    "id": "respondente",
    "estratos": ["cargo", "porte"],
    "perguntas": {
        "confia_ia": {
            "texto": "Quanto você confia nas respostas de ferramentas de IA no seu trabalho?",
            "rotulo": "Confiança na IA",
            "escala": {o: i + 1 for i, o in enumerate(CONFIA)},
        },
        "recomendaria": {
            "texto": "Qual a chance de você recomendar uma ferramenta de IA a um colega?",
            "rotulo": "Recomendaria IA",
            "escala": {o: i + 1 for i, o in enumerate(RECOMENDA)},
        },
    },
}


def _escolher(rng, opcoes, p):
    return opcoes[int(rng.choice(len(opcoes), p=p))]


def humanos(rng) -> list[dict]:
    linhas = []
    for i in range(PESSOAS):
        cargo = _escolher(rng, list(CARGOS), list(CARGOS.values()))
        porte = _escolher(rng, list(PORTES), list(PORTES.values()))
        confia = "Não sei" if rng.random() < NAO_SEI else _escolher(rng, CONFIA, P_CONFIA[cargo])
        recomenda = _escolher(rng, RECOMENDA, P_RECOMENDA[cargo])
        linhas.append({"respondente": f"p{i + 1:03d}", "cargo": cargo, "porte": porte,
                       "confia_ia": confia, "recomendaria": recomenda})
    return linhas


def sinteticos(rng, n: int = 50) -> dict:
    """Dois usuários sintéticos para Gerente: um parecido com as pessoas, outro otimista demais."""
    otimista = [0.00, 0.02, 0.08, 0.40, 0.50]
    return {
        "pergunta": "confia_ia",
        "segmento": {"cargo": "Gerente"},
        "usuarios": {
            "parecido": {
                "descricao": "Responde como os gerentes reais: espera-se confiabilidade média "
                             "(alta exige os três sinais, que esta versão ainda não calcula).",
                "respostas": [_escolher(rng, CONFIA, P_CONFIA["Gerente"]) for _ in range(n)],
            },
            "otimista": {
                "descricao": "Confia na IA bem mais que os gerentes reais: espera-se confiabilidade baixa.",
                "respostas": [_escolher(rng, CONFIA, otimista) for _ in range(n)],
            },
        },
    }


def main(destino: Path = AQUI) -> None:
    rng = np.random.default_rng(SEMENTE)
    linhas = humanos(rng)
    with open(destino / "respostas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)
    (destino / "dicionario.json").write_text(json.dumps(DICIONARIO, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destino / "sinteticas.json").write_text(json.dumps(sinteticos(rng), ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")


if __name__ == "__main__":
    main()
