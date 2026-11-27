#!/usr/bin/env python3
"""Experimento às cegas: gera usuários sintéticos com `claude -p` e compara com o holdout humano.

Uso:
  python experiments/run_blind_experiment.py generate  --config experiments/stackoverflow-2025-blind.json --out runs/blind
  python experiments/run_blind_experiment.py analyze   --config experiments/stackoverflow-2025-blind.json --out runs/blind --csv data/stackoverflow-2025/results.csv
  python experiments/run_blind_experiment.py generate ... --limite 3   # teste rápido: 3 respostas por célula

O gerador (generate) NÃO lê os dados humanos. Só o analyze lê.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

OPCOES = {
    "AIAcc": ["Highly trust", "Somewhat trust", "Neither trust nor distrust", "Somewhat distrust", "Highly distrust"],
    "AISent": ["Very favorable", "Favorable", "Indifferent", "Unfavorable", "Very unfavorable"],
}
SISTEMA = (
    "You are simulating one respondent of the Stack Overflow Developer Survey. "
    "Answer exactly as that person would. Reply with only one of the listed options, copied exactly, and nothing else."
)


def hash_config(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def perfil(filtro: dict) -> str:
    return "; ".join(f"{k}: {v}" for k, v in filtro.items())


def montar_prompt(pergunta_id: str, texto: str, filtro: dict) -> str:
    opcoes = "\n".join(f"- {o}" for o in OPCOES[pergunta_id])
    return f"Respondent profile: {perfil(filtro)}.\n\nQuestion: {texto}\n\nOptions:\n{opcoes}\n\nYour answer:"


def chamar_claude(prompt: str, modelo: str) -> dict:
    with tempfile.TemporaryDirectory() as pasta_vazia:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", modelo, "--tools", "", "--setting-sources", "",
             "--disable-slash-commands", "--no-session-persistence", "--system-prompt", SISTEMA,
             "--output-format", "json"],
            cwd=pasta_vazia, capture_output=True, text=True, timeout=180,
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300] or "claude falhou")
    data = json.loads(proc.stdout)
    return {"texto": str(data.get("result", "")).strip(), "custo_usd": data.get("total_cost_usd", 0.0)}


def interpretar(pergunta_id: str, texto: str) -> str | None:
    limpo = texto.strip().strip("-*•. \"'").lower()
    for o in OPCOES[pergunta_id]:
        if limpo == o.lower():
            return o
    return None


def generate(cfg: dict, out: Path, limite: int | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    h = hash_config(cfg)
    arq = out / "respostas.jsonl"
    feitas: set[tuple] = set()
    if arq.exists():
        for linha in arq.read_text().splitlines():
            r = json.loads(linha)
            if r["config_hash"] != h:
                sys.exit("A configuração mudou desde a geração. Use outra pasta --out ou restaure a configuração.")
            feitas.add((r["segmento"], r["pergunta"], r["i"]))
    n = limite or cfg["n_por_celula"]
    tarefas = [
        (s, q, i) for s in cfg["segmentos"] for q in cfg["perguntas"] for i in range(n)
        if (s["nome"], q, i) not in feitas
    ]
    print(f"{len(tarefas)} chamadas a fazer ({len(feitas)} já feitas); modelo {cfg['modelo']}")
    trava = threading.Lock()
    contagem = {"ok": 0, "invalida": 0, "erro": 0, "custo": 0.0}

    def uma(t):
        s, q, i = t
        prompt = montar_prompt(q, cfg["perguntas"][q], s["filtro"])
        resp, r, tentativas = None, {"texto": "", "custo_usd": 0.0}, 0
        for tentativas in range(1, 4):  # mesma pergunta de novo se a resposta vier fora do formato
            try:
                r = chamar_claude(prompt, cfg["modelo"])
            except Exception as e:  # noqa: BLE001
                print(f"erro {s['nome']}/{q}/{i}: {e}", file=sys.stderr)
                r = None
                break
            resp = interpretar(q, r["texto"])
            if resp:
                break
        if r is None:
            with trava:
                contagem["erro"] += 1
            return
        reg = {
            "config_hash": h, "segmento": s["nome"], "pergunta": q, "i": i, "modelo": cfg["modelo"],
            "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12], "bruto": r["texto"],
            "resposta": resp, "tentativas": tentativas, "custo_usd": r["custo_usd"], "em": datetime.now(timezone.utc).isoformat(),
        }
        with trava:
            with arq.open("a") as fh:
                fh.write(json.dumps(reg, ensure_ascii=False) + "\n")
            contagem["ok" if resp else "invalida"] += 1
            contagem["custo"] += r["custo_usd"]
            feito = contagem["ok"] + contagem["invalida"] + contagem["erro"]
            if feito % 25 == 0:
                print(f"{feito}/{len(tarefas)}  custo US$ {contagem['custo']:.3f}")

    with ThreadPoolExecutor(cfg["paralelismo"]) as ex:
        list(ex.map(uma, tarefas))
    print(f"fim: {contagem}")


def holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    ordem = sorted(range(m), key=lambda i: pvals[i])
    ajust = [0.0] * m
    maior = 0.0
    for rank, i in enumerate(ordem):
        maior = max(maior, min(1.0, (m - rank) * pvals[i]))
        ajust[i] = maior
    return ajust


def analyze(cfg: dict, out: Path, csv_path: str) -> None:
    import numpy as np

    from synthetic_users_confidence import confiabilidade, metrics, render, tools
    from synthetic_users_confidence.scales import PERGUNTA, ROTULO, SCALES

    h = hash_config(cfg)
    por_celula: dict[tuple, list[int]] = {}
    invalidas = 0
    for linha in (out / "respostas.jsonl").read_text().splitlines():
        r = json.loads(linha)
        if r["config_hash"] != h:
            sys.exit("A configuração mudou depois da geração; a análise foi recusada.")
        if r["resposta"] is None:
            invalidas += 1
            continue
        por_celula.setdefault((r["segmento"], r["pergunta"]), []).append(SCALES[r["pergunta"]][r["resposta"]])

    tools.importar_dados(csv_path, cfg["fracao_holdout"], cfg["semente_holdout"])
    ds = tools.STATE["ds"]
    rng = np.random.default_rng(0)
    linhas, pvals, detalhes = [], [], []
    for s in cfg["segmentos"]:
        for q in cfg["perguntas"]:
            synth = np.asarray(por_celula.get((s["nome"], q), []), dtype=int)
            humanos = ds.humans(q, s["filtro"], holdout=True)
            if len(synth) < 30 or len(humanos) < 30:
                linhas.append({"segmento": s["nome"], "pergunta": q, "status": "dados_insuficientes",
                               "n_sintetico": int(len(synth)), "n_humano": int(len(humanos))})
                pvals.append(1.0)
                continue
            alvo = metrics.pmf(humanos)
            geral = ds.humans(q, {}, holdout=False)
            # Referência geral: respostas sorteadas de qualquer idade, mesmo tamanho do usuário sintético.
            ref_geral = metrics.emd(metrics.pmf(rng.choice(geral, size=len(synth))), alvo)
            # Segmento trocado: o mesmo usuário sintético, mas de outro grupo, comparado a este grupo.
            outros = [
                metrics.emd(metrics.pmf(np.asarray(por_celula[(o["nome"], q)], dtype=int)), alvo)
                for o in cfg["segmentos"] if o["nome"] != s["nome"] and (o["nome"], q) in por_celula
            ]
            seg_trocado = float(np.mean(outros)) if outros else float("nan")
            val = tools.validar_usuario(q, s["filtro"], synth.tolist())
            pont = tools.pontuar_resposta(q, synth.tolist())
            emd_s = val["fidelidade"]["emd"]
            p = val["significancia"]["p_value"]
            pvals.append(p)
            detalhes.append(val)
            dif = float(synth.mean()) - float(humanos.mean())
            razao = val["fidelidade"]["razao_de_variancia"]
            melhor_geral, melhor_trocado = emd_s < ref_geral, emd_s < seg_trocado
            nv = confiabilidade.nivel(dif, razao, melhor_geral, sinais_completos=False)
            linhas.append({
                "segmento": s["nome"], "pergunta": q, "status": "ok", "n_sintetico": int(len(synth)),
                "n_humano": int(len(humanos)), "emd_usuario": emd_s,
                "emd_referencia_geral": round(ref_geral, 4), "emd_segmento_trocado": round(seg_trocado, 4),
                "p_value": p, "media_sintetica": round(float(synth.mean()), 3), "media_humana": round(float(humanos.mean()), 3),
                "diferenca_de_media": round(dif, 3), "razao_de_variancia": razao,
                "melhor_que_referencia_geral": melhor_geral, "melhor_que_segmento_trocado": melhor_trocado,
                "margem_media_sintetica": val["margem_de_erro"]["sintetico"]["media"],
                "margem_media_humana": val["margem_de_erro"]["humano"]["media"],
                "variancia_sintetica": val["distribuicao_sintetica"]["variancia"],
                "variancia_humana": val["distribuicao_humana"]["variancia"],
                "p_value_variancia": val["significancia"]["p_value_variancia"],
                "sinais": {
                    "dispersao": pont["confianca"]["dispersao"],
                    "suporte_na_base": pont["confianca"]["suporte_na_base"],
                    "acerto_historico": {
                        "status": "sem_holdout_suficiente",
                        "motivo": "há só 2 perguntas por grupo (AIAcc e AISent); faltam perguntas parecidas no holdout",
                    },
                },
                "nivel_provisorio": nv,
                "margem_media": max(val["margem_de_erro"]["sintetico"]["media"] or 0, val["margem_de_erro"]["humano"]["media"] or 0),
            })
    for r, pa in zip(linhas, holm(pvals)):
        r["p_value_holm"] = round(pa, 4)
        if r["status"] == "ok":
            r["insight"] = confiabilidade.insight(r["diferenca_de_media"], r["margem_media"], r["razao_de_variancia"],
                                                  r["p_value_holm"], r["nivel_provisorio"])
    ok = [r for r in linhas if r["status"] == "ok"]
    aprovadas = [r for r in ok if r["melhor_que_referencia_geral"] and r["melhor_que_segmento_trocado"]]
    resumo = {
        "config_hash": h, "respostas_invalidas": invalidas, "celulas": len(linhas), "celulas_ok": len(ok),
        "celulas_aprovadas": len(aprovadas),
        "taxa_aprovacao": round(len(aprovadas) / len(ok), 3) if ok else None,
        "criterio": cfg["criterio_de_aprovacao"], "resultados": linhas, "validacoes": detalhes,
    }
    (out / "resultado.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1))

    corpo = [
        {"grupo": r["segmento"].replace("idade-", ""), "pergunta": r["pergunta"], "nivel": r["nivel_provisorio"],
         "media_s": r["media_sintetica"], "media_h": r["media_humana"], "var_s": r["variancia_sintetica"],
         "var_h": r["variancia_humana"], "p": r["p_value_holm"], "insight": r["insight"]}
        for r in ok
    ]
    n_baixa = sum(1 for r in ok if r["nivel_provisorio"] == "baixa")
    n_media = sum(1 for r in ok if r["nivel_provisorio"] == "média")
    perguntas = "\n".join(f"- **{ROTULO[q]}** (`{q}`): {PERGUNTA[q]}" for q in cfg["perguntas"])
    partes = [
        f"# Experimento às cegas · {cfg['nome']}\n",
        "> **SINTÉTICO.** Respostas simuladas. Não substituem pesquisa com pessoas.\n",
        f"**Confiabilidade (provisória): {n_baixa} baixa, {n_media} média, {len(ok) - n_baixa - n_media} alta.**",
        f"Critério pré-registrado do experimento: {len(aprovadas)} de {len(ok)} células aprovadas"
        + (f" ({str(round(100 * len(aprovadas) / len(ok))).replace('.', ',')}%), o mínimo era 70%" if ok else "")
        + f". Respostas inválidas: {invalidas}.\n",
        "## Usuário sintético vs pessoas reais\n",
        "```\n" + (render.tabela_confiabilidade(corpo, com_grupo=True) if corpo else "(sem dados suficientes)") + "\n```\n",
        "### Perguntas\n",
        perguntas + "\n",
        "### Como ler\n",
        "- **Pessoas reais** são o baseline: o holdout humano, que o usuário sintético nunca viu.",
        "- **Confiab.:** confiabilidade. **Signif.:** significância (p-value corrigido por Holm, 95% de confiança). Abaixo de 0,05, as respostas diferem das reais; acima, a diferença não foi provada, o que não prova que são iguais. O teste usa 2.000 sorteios, então abaixo de 0,01 mostra só \"p<0,01\".",
        "- **Média:** escala de 1 a 5. **Variação:** variância das respostas; muito menor que a humana significa todo mundo respondendo igual.",
        "",
        "### Não calculado (os três sinais do PRD)",
        "- **Dispersão entre amostras:** calculada (em `resultado.json`).",
        "- **Suporte na base de conhecimento:** não calculado. Este experimento não conecta uma base (veja `conectar_base`).",
        "- **Acerto histórico:** não calculado. Há só 2 perguntas por grupo; faltam perguntas parecidas no holdout.",
        "",
        f"_Regra provisória do nível: {confiabilidade.REGRA} {confiabilidade.LIMITE.capitalize()}. O critério de aprovação do experimento é o pré-registrado e não mudou._\n",
    ]
    for r in linhas:
        if r["status"] != "ok":
            partes.append(f"- {r['segmento']} / {r['pergunta']}: dados insuficientes ({r['n_sintetico']} sintéticas, {r['n_humano']} humanos).")
    texto = "\n".join(partes)
    (out / "resultado.md").write_text(texto)
    print(texto)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fase", choices=["generate", "analyze"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv")
    ap.add_argument("--limite", type=int, help="respostas por célula (teste rápido)")
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    if a.fase == "generate":
        generate(cfg, Path(a.out), a.limite)
    else:
        if not a.csv:
            sys.exit("--csv é obrigatório na análise")
        analyze(cfg, Path(a.out), a.csv)


if __name__ == "__main__":
    main()
