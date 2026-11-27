"""Resumo em markdown das saídas: tabela com uma coluna de insight por linha."""

from __future__ import annotations

import textwrap

from .confiabilidade import ROTULO_NIVEL
from .scales import PERGUNTA, ROTULO

FENCE = "```"


def _segmento(seg: dict) -> str:
    return ", ".join(f"{k}: {v}" for k, v in seg.items())


def table(headers: list[str], rows: list[list[str]], widths: list[int]) -> str:
    """Tabela com bordas; o texto longo quebra em várias linhas dentro da célula."""

    def line(l: str, m: str, r: str) -> str:
        return l + m.join("─" * (w + 2) for w in widths) + r

    def row(cells: list[str]) -> list[str]:
        wrapped = [textwrap.wrap(c, w) or [""] for c, w in zip(cells, widths)]
        height = max(len(c) for c in wrapped)
        return [
            "│ " + " │ ".join((c[i] if i < len(c) else "").ljust(w) for c, w in zip(wrapped, widths)) + " │"
            for i in range(height)
        ]

    out = [line("┌", "┬", "┐"), *row(headers), line("├", "┼", "┤")]
    for i, r in enumerate(rows):
        out.extend(row(r))
        out.append(line("├", "┼", "┤") if i < len(rows) - 1 else line("└", "┴", "┘"))
    return "\n".join(out)


def _n(x: float | None, nd: int = 2) -> str:
    return "-" if x is None else f"{x:.{nd}f}".replace(".", ",")


def _int(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def p_texto(p: float) -> str:
    """Abaixo de 0,01 o teste (2000 sorteios) não distingue valores; não mostra falsa precisão."""
    return "p<0,01" if p < 0.01 else f"p={_n(p)}"


def tabela_confiabilidade(linhas: list[dict], com_grupo: bool, largura_grupo: int = 5) -> str:
    """Tabela oficial: confiabilidade, média, variação e significância (sintético vs pessoas reais) e insight.

    Cada linha: grupo, pergunta, nivel, media_s, media_h, var_s, var_h, p, insight.
    Cabe em cerca de 100 colunas.
    """
    cab = ["Pergunta", "Confiab.", "Média sint. / real", "Variação sint. / real", "Signif.", "Insight"]
    larguras = [10, 8, 11, 11, 7, 30]
    if com_grupo:
        cab, larguras = ["Grupo", *cab], [largura_grupo, 10, 8, 11, 11, 7, 31 - largura_grupo]
    corpo = []
    for r in linhas:
        linha = [
            ROTULO.get(r["pergunta"], r["pergunta"]), ROTULO_NIVEL[r["nivel"]],
            f"{_n(r['media_s'])} / {_n(r['media_h'])}", f"{_n(r['var_s'])} / {_n(r['var_h'])}",
            p_texto(r["p"]), r["insight"],
        ]
        corpo.append([r["grupo"], *linha] if com_grupo else linha)
    return table(cab, corpo, larguras)


def _suporte(sup: dict) -> tuple[str, str]:
    """Valor curto e leitura do sinal suporte_na_base."""
    if sup.get("status") != "ok":
        return "não calculado", sup["motivo"].capitalize() + "."
    n = sup["estudos_distintos"]
    lista = f" ({', '.join(sup['estudos'])})" if sup["estudos"] else ""
    valor = f"{n} estudo{'s' if n != 1 else ''}"
    leitura = (f"{n} estudo{'s' if n != 1 else ''} da base trata{'m' if n != 1 else ''} do tema{lista}"
               if n else "A base da equipe não trata deste tema")
    return valor, leitura + ". Não diz se concordam com a resposta."


def validar_usuario(out: dict) -> str:
    head = f"> **{out['rotulo'].upper()}.** Resposta simulada. Não substitui pesquisa com pessoas.\n\n"
    if out["status"] != "ok":
        avisos = "\n".join(f"- {a}" for a in out["avisos"])
        return head + f"## Não foi possível comparar\n\n{avisos}\n"
    s, h = out["distribuicao_sintetica"], out["distribuicao_humana"]
    c = out["confiabilidade"]
    tabela = tabela_confiabilidade(
        [{
            "grupo": "", "pergunta": out["pergunta"], "nivel": c["nivel"],
            "media_s": s["media"], "media_h": h["media"], "var_s": s["variancia"], "var_h": h["variancia"],
            "p": out["significancia"]["p_value"], "insight": c["insight"],
        }],
        com_grupo=False,
    )
    nomes = {"suporte_na_base": "Suporte na base de conhecimento", "acerto_historico": "Acerto histórico"}
    nao_calc = "".join(
        f"\n- **{nomes[k]}:** {v['motivo']}." for k, v in c["sinais"].items() if v.get("status") not in (None, "ok")
    )
    sup = c["sinais"]["suporte_na_base"]
    linha_sup = f"\n**Suporte na base:** {_suporte(sup)[1]}\n" if sup.get("status") == "ok" else ""
    avisos = "".join(f"\n- {a}" for a in out["avisos"])
    return (
        head
        + f"## Confiabilidade: {c['nivel'].upper()}\n\n"
        + f"{ROTULO.get(out['pergunta'], out['pergunta'])} · {_segmento(out['segmento'])}\n\n"
        + f"{FENCE}\n{tabela}\n{FENCE}\n"
        + f"\n_Pergunta original: {PERGUNTA.get(out['pergunta'], out['pergunta'])}_\n"
        + "\n**Como ler.** Pessoas reais são o baseline (holdout que o usuário sintético não viu). "
        + "Média na escala de 1 a 5. Variação é a variância das respostas. "
        + "Signif. é o p-value, com 95% de confiança: abaixo de 0,05 as respostas diferem das reais; acima, a diferença não foi provada, o que não prova que são iguais.\n"
        + linha_sup
        + f"\n**Não calculado:**{nao_calc}\n"
        + f"\n_Regra provisória do nível: {c['regra']} {c['limite'].capitalize()}._\n"
        + (f"\n### Avisos{avisos}\n" if avisos else "")
    )


def pontuar_resposta(out: dict) -> str:
    d = out["distribuicao"]
    m = out["margem_de_erro"]
    c = out["confianca"]["dispersao"]
    tabela = table(
        ["Métrica", "Valor", "Insight"],
        [
            ["Respostas", _int(out["amostras"]), "Poucas respostas: resultado instável." if out["amostras"] < 10 else "Quantidade razoável."],
            ["Média (escala 1 a 5)", f"{_n(d['media'])} ±{_n(m['media'])}", f"A média pode errar até {_n(m['media'])} ponto para mais ou menos."],
            ["Variância", _n(d["variancia"]), "Quanto maior, mais dividido o usuário sintético está entre as respostas."],
            ["Dispersão", _n(c["valor"], 2), c["limite"].capitalize() + "."],
            ["Suporte na base", *_suporte(out["confianca"]["suporte_na_base"])],
        ],
        [20, 14, 50],
    )
    return (
        f"> **{out['rotulo'].upper()}.** Resposta simulada. Não substitui pesquisa com pessoas.\n\n"
        f"## Pergunta {out['pergunta']}\n\n" + f"{FENCE}\n{tabela}\n{FENCE}\n" + f"\n**Em resumo:** {out['insight']}\n"
    )
