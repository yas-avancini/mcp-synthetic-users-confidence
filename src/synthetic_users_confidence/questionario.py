"""Dicionário do questionário: diz quais colunas do CSV são perguntas, a escala de cada uma e os estratos.

Formato (JSON):
    {
      "nome": "pesquisa-nps-2026",              # opcional
      "id": "respondente",                       # opcional: coluna com o id (uma linha por respondente)
      "estratos": ["faixa_etaria", "cargo"],     # opcional: colunas para estratificar o holdout
      "separador_multiplo": ";",                 # opcional: separa opções em colunas de múltipla escolha
      "perguntas": {
        "confia_ia": {                           # nome da coluna no CSV
          "texto": "Quanto você confia ...?",    # opcional: texto original (vai para a busca no RAG)
          "rotulo": "Confiança na IA",           # opcional: nome curto para tabelas
          "escala": {"Discordo totalmente": 1, "Discordo": 2, "Neutro": 3, "Concordo": 4, "Concordo totalmente": 5}
        }
      }
    }

A escala precisa ter os 5 pontos de 1 a 5: a régua de confiabilidade foi definida em pontos dessa escala.
Opções fora da escala (como "Não sei") são ignoradas e contadas em `cobertura`.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

PONTOS = {1, 2, 3, 4, 5}
CHAVES = {"nome", "descricao", "id", "estratos", "separador_multiplo", "perguntas"}
CHAVES_PERGUNTA = {"texto", "rotulo", "escala"}
MAX_OPCOES = 12  # acima disso a coluna não é lida como categórica
MIN_CONTAGEM = 5  # um valor só aparece na detecção se pelo menos 5 respondentes o deram
FORMATO = {
    "nome": "minha-pesquisa",
    "id": "coluna_do_id (opcional)",
    "estratos": ["coluna_de_segmento"],
    "separador_multiplo": ";",
    "perguntas": {
        "coluna_da_pergunta": {
            "texto": "texto original da pergunta (opcional)",
            "rotulo": "nome curto (opcional)",
            "escala": {"opção mais negativa": 1, "...": 2, "opção do meio": 3, "....": 4, "opção mais positiva": 5},
        }
    },
}


def carregar(dicionario: dict | str) -> dict:
    if isinstance(dicionario, dict):
        return dicionario
    if dicionario.lstrip().startswith("{"):
        return json.loads(dicionario)  # JSON passado como texto
    return json.loads(Path(dicionario).expanduser().read_text(encoding="utf-8"))


def validar(d, colunas: list[str]) -> list[str]:
    """Erros do dicionário diante das colunas do CSV (lista vazia: válido)."""
    if not isinstance(d, dict):
        return ["o dicionário precisa ser um objeto JSON"]
    erros = [f"chave desconhecida: {k!r}" for k in d if k not in CHAVES]
    cols = set(colunas)
    if d.get("id") is not None and d["id"] not in cols:
        erros.append(f"coluna de id {d['id']!r} não existe no CSV")
    estratos = d.get("estratos", [])
    if not isinstance(estratos, list) or not all(isinstance(e, str) for e in estratos):
        erros.append("estratos precisa ser uma lista de nomes de coluna")
        estratos = []
    erros += [f"estrato {e!r} não existe no CSV" for e in estratos if e not in cols]
    sep = d.get("separador_multiplo", ";")
    if not isinstance(sep, str) or not sep:
        erros.append("separador_multiplo precisa ser um texto não vazio")
    perguntas = d.get("perguntas")
    if not isinstance(perguntas, dict) or not perguntas:
        return erros + ["perguntas precisa ter ao menos uma pergunta"]
    for q, p in perguntas.items():
        if q not in cols:
            erros.append(f"pergunta {q!r}: coluna não existe no CSV")
        if q in estratos:
            erros.append(f"pergunta {q!r} também está nos estratos")
        if not isinstance(p, dict):
            erros.append(f"pergunta {q!r}: precisa ser um objeto com 'escala'")
            continue
        erros += [f"pergunta {q!r}: chave desconhecida {k!r}" for k in p if k not in CHAVES_PERGUNTA]
        erros += [f"pergunta {q!r}: {k} precisa ser texto" for k in ("texto", "rotulo")
                  if k in p and not isinstance(p[k], str)]
        esc = p.get("escala")
        if not isinstance(esc, dict) or not esc:
            erros.append(f"pergunta {q!r}: falta a escala (opção → ponto de 1 a 5)")
            continue
        pontos = list(esc.values())
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in pontos):
            erros.append(f"pergunta {q!r}: os pontos da escala precisam ser inteiros")
        elif set(pontos) != PONTOS:
            erros.append(f"pergunta {q!r}: a escala precisa usar os 5 pontos de 1 a 5 (recebi {sorted(set(pontos))})")
    return erros


def _valores(rows: list[dict[str, str]], col: str, sep: str | None) -> Counter:
    c: Counter = Counter()
    for r in rows:
        v = (r.get(col) or "").strip()
        if not v:
            continue
        c.update(x.strip() for x in v.split(sep) if x.strip()) if sep else c.update([v])
    return c


SEPARADORES = (";", "|")  # vírgula fica de fora: aparece em texto livre


def detectar(colunas: list[str], rows: list[dict[str, str]]) -> dict:
    """Resumo das colunas para montar o dicionário, sem expor valores raros.

    Só aparecem valores de colunas com até 12 opções, e só os que pelo menos 5 respondentes deram:
    texto livre, ids e valores raros (que podem identificar alguém) não são lidos.
    """
    out, perguntas, estratos, achados = [], [], [], Counter()
    for col in colunas:
        sep = next((s for s in SEPARADORES if any(s in (r.get(col) or "") for r in rows)), None)
        multipla = sep is not None
        c = _valores(rows, col, sep)
        if multipla and len(c) <= MAX_OPCOES:
            achados[sep] += 1
        item: dict = {"coluna": col, "opcoes_distintas": len(c), "respondentes": sum(1 for r in rows if (r.get(col) or "").strip())}
        if multipla:
            item["multipla_escolha"] = True
        if 0 < len(c) <= MAX_OPCOES:
            comuns = {v: n for v, n in c.most_common() if n >= MIN_CONTAGEM}
            item["valores"] = comuns
            if len(comuns) < len(c):
                item["valores_ocultos"] = len(c) - len(comuns)
            if not multipla and 3 <= len(c) <= 7:  # escalas com pontos sem resposta também entram
                perguntas.append(col)
            elif len(c) >= 2:
                estratos.append(col)
        else:
            item["valores"] = None
            item["motivo"] = "muitas opções (texto livre, id ou número): valores não lidos"
        out.append(item)
    return {
        "colunas": out,
        "candidatas_a_pergunta": perguntas,
        "candidatas_a_estrato": estratos,
        "sugestao": _sugestao(out, perguntas, estratos, achados.most_common(1)[0][0] if achados else ";"),
    }


def _sugestao(itens: list[dict], perguntas: list[str], estratos: list[str], sep: str) -> dict:
    """Rascunho do dicionário. Só preenche a escala quando a ordem é óbvia (valores 1 a 5)."""
    por_col = {i["coluna"]: i for i in itens}
    qs: dict = {}
    for q in perguntas:
        vals = set(por_col[q].get("valores") or {})
        if vals == {str(n) for n in PONTOS}:
            qs[q] = {"escala": {str(n): n for n in sorted(PONTOS)}}
        else:
            qs[q] = {"escala": None, "opcoes": sorted(vals)}
    ids = [i["coluna"] for i in itens if i["valores"] is None and i["respondentes"] == i["opcoes_distintas"] > 0]
    ids.sort(key=lambda c: not any(t in c.lower() for t in ("id", "respond")))  # nomes de id primeiro
    return {
        **({"id": ids[0]} if ids else {}),
        "estratos": estratos,
        "separador_multiplo": sep,
        "perguntas": qs,
        "falta": "ordene as opções de cada escala de 1 (mais negativo) a 5 (mais positivo) e confirme os estratos",
    }


def cobertura(rows: list[dict[str, str]], d: dict) -> tuple[dict, list[str]]:
    """Quantas respostas de cada pergunta caem na escala, e avisos de opções que não casam."""
    out, avisos = {}, []
    for q, p in d["perguntas"].items():
        c = _valores(rows, q, None)
        esc = p["escala"]
        validas = sum(n for v, n in c.items() if v in esc)
        fora = {v: n for v, n in c.most_common() if v not in esc}
        out[q] = {
            "validas": validas,
            "vazias": len(rows) - sum(c.values()),
            "fora_da_escala": sum(fora.values()),
            "opcoes_fora": {v: n for v, n in fora.items() if n >= MIN_CONTAGEM},
        }
        if validas == 0:
            avisos.append(f"{q}: nenhuma resposta casa com a escala; confira os nomes das opções")
        ausentes = [o for o in esc if o not in c]
        if ausentes and validas:
            avisos.append(f"{q}: opções da escala que não aparecem no CSV: {ausentes}")
    return out, avisos
