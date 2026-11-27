"""Lógica das ferramentas, separada do servidor MCP para poder ser testada direto."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

from . import base, confiabilidade, fontes, metrics, questionario, scales
from .data import STRATA, Dataset, split_holdout
from .scales import LABEL, PERGUNTA, SCALES

MIN_HUMANS = 30  # abaixo disso o segmento não sustenta comparação
STATE: dict = {}  # "ds": Dataset; "conexao": dict (configuração do RAG)


def _coerce(question: str, responses: list) -> np.ndarray:
    scale = SCALES[question]
    out = []
    for r in responses:
        v = scale.get(r) if isinstance(r, str) else int(r)
        if v is None or not 1 <= v <= 5:
            raise ValueError(f"resposta inválida para {question}: {r!r}")
        out.append(v)
    return np.asarray(out, dtype=int)


def _check_question(question: str) -> None:
    if question not in SCALES:
        raise ValueError(f"pergunta não suportada: {question}. Use uma de {sorted(SCALES)}")


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(x, nd)


def _ci(ci: tuple[float, float] | None) -> list[float] | None:
    return None if ci is None else [round(ci[0], 3), round(ci[1], 3)]


def _margens(v: np.ndarray) -> dict:
    return {
        "nivel_de_confianca": "95%",
        "media": _r(metrics.margin_of_error_mean(v)),
        "proporcao_pp": _r(metrics.margin_of_error_proportion(len(v)), 1),
        "variancia_intervalo_95": _ci(metrics.variance_ci(v)),
        "limite": "media em pontos da escala 1 a 5; proporcao em pontos percentuais, no pior caso (p = 50%); variancia por bootstrap",
    }


def _pt(x: float, nd: int = 2) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _dispersao(v: np.ndarray) -> dict:
    d = metrics.dispersion(v)
    leitura = "indefinida" if np.isnan(d) else ("consistente" if d < 0.25 else "moderada" if d < 0.4 else "dividida")
    return {
        "valor": None if np.isnan(d) else round(d, 3),
        "leitura": leitura,
        "limite": "mede consistência do modelo, não verdade; faixas de leitura provisórias",
    }


def _insight_pontuar(v: np.ndarray, margens: dict) -> str:
    texto = f"O usuário sintético respondeu, em média, {_pt(float(v.mean()))} numa escala de 1 a 5"
    if margens["media"] is not None:
        texto += f", e esse valor pode estar errado em até {_pt(margens['media'])} ponto(s) para mais ou para menos"
    texto += f" (baseado em {len(v)} respostas)."
    return texto + " Isto mostra o quanto ele é estável, não se ele acerta. Para saber se ele se parece com pessoas reais, compare com os dados reais."


def _insight_validar(synth, human, p_value, p_var, emd_value, piso) -> str:
    n, h = len(synth), len(human)
    partes = [f"Comparamos {n} respostas do usuário sintético com as de {h} pessoas reais deste grupo."]
    if p_value < 0.05:
        partes.append("As respostas dele são diferentes das das pessoas reais; não parece coincidência.")
        diff = float(synth.mean()) - float(human.mean())
        if abs(diff) >= 0.15:
            partes.append("Ele tende a responder de forma mais positiva." if diff > 0 else "Ele tende a responder de forma mais negativa.")
    else:
        partes.append("Não encontramos diferença entre as respostas dele e as das pessoas reais.")
        partes.append(f"Mas {n} respostas é pouco para ter certeza: isso não prova que ele representa bem o grupo.")
    if p_var < 0.05:
        mais_uniforme = float(synth.var(ddof=1)) < float(human.var(ddof=1))
        partes.append(
            "Ele responde de forma mais parecida entre si (menos variedade de opinião) do que as pessoas reais."
            if mais_uniforme
            else "Ele varia mais de opinião do que as pessoas reais."
        )
    else:
        partes.append("A variedade de opiniões dele é parecida com a das pessoas reais.")
    return " ".join(partes)


# ---------- conexão com a base da equipe ----------

def _instrucao_credencial(cfg: dict) -> str:
    var = cfg["autenticacao"]["variavel"]
    return (
        f"defina a variável de ambiente {var} ao instalar o servidor "
        f"(claude mcp add synthetic-users-confidence -e {var}=SUA_CHAVE -- ...) ou rode conectar_base num cliente "
        "que aceite elicitation por URL; nunca passe a chave como argumento"
    )


def _cfg_inicial(url, caminho_config, autenticacao, cabecalho) -> tuple[dict, Path]:
    caminho = Path(caminho_config).expanduser() if caminho_config else base.caminho_padrao()
    if caminho.exists():
        cfg = base.carregar(caminho)
    elif caminho_config:
        raise ValueError(f"arquivo de conexão não encontrado: {caminho}")
    else:
        cfg = {}
    if url:
        if cfg.get("url") and cfg["url"] != url:
            cfg.pop("calibracao", None)  # outra base, outra calibração
        cfg["url"] = url
    if autenticacao:
        cfg.setdefault("autenticacao", {})["tipo"] = autenticacao
    if cabecalho:
        cfg.setdefault("autenticacao", {})["cabecalho"] = cabecalho
    cfg = base.completar(cfg)
    base.validar(cfg)
    return cfg, caminho


def _aplicar_mapeamento(cfg: dict, m: dict) -> None:
    for k in ("lista", "texto", "score", "estudo", "data", "id", "fonte"):
        if k in m and m[k] is not None:
            if m[k] == base.SEM_CAMPO:
                cfg["resposta"].pop(k, None)
            else:
                cfg["resposta"][k] = "" if m[k] == base.RAIZ else m[k]
    if m.get("score_tipo"):
        if cfg["score"].get("tipo") != m["score_tipo"]:
            cfg.pop("calibracao", None)
        cfg["score"]["tipo"] = m["score_tipo"]
    if "estudos_holdout" in m and m["estudos_holdout"] is not None:
        v = m["estudos_holdout"]
        cfg["estudos_holdout"] = [x.strip() for x in v.split(",") if x.strip()] if isinstance(v, str) else list(v)


def _adaptador(cfg: dict) -> base.AdaptadorHTTP:
    return base.AdaptadorHTTP(cfg, base.credencial(cfg))


def diagnosticar_conexao(url: str | None = None, caminho_config: str | None = None, autenticacao: str | None = None,
                         cabecalho: str | None = None, mapeamento: dict | None = None) -> dict:
    """Passos sem efeito colateral: configuração, credencial, busca de teste e mapeamento. Não calibra nem salva."""
    try:
        cfg, caminho = _cfg_inicial(url, caminho_config, autenticacao, cabecalho)
        if mapeamento:
            _aplicar_mapeamento(cfg, mapeamento)
            base.validar(cfg)
    except base.ErroConfig as e:
        return {"status": "configuracao_invalida", "motivo": str(e)}
    out = {"arquivo": str(caminho), "nome": cfg["nome"]}
    if not cfg.get("url"):
        return {**out, "status": "precisa_configuracao", "faltando": ["url"],
                "motivo": "informe a url de busca do RAG da equipe"}
    if base.precisa_credencial(cfg) and not base.credencial(cfg):
        return {**out, "status": "precisa_credencial", "variavel": cfg["autenticacao"]["variavel"],
                "motivo": _instrucao_credencial(cfg), "_cfg": cfg}
    try:
        bruto = _adaptador(cfg).requisitar(base.CONSULTA_TESTE, int(cfg["top_k"]))
    except base.ErroConexao as e:
        return {**out, "status": "erro_conexao", "codigo": e.codigo, "motivo": e.motivo}
    det = base.detectar(bruto)
    falta = base.faltando(cfg)
    if falta:
        return {**out, "status": "precisa_configuracao", "faltando": falta, "campos_detectados": det,
                "sugestao": base.sugerir(det), "_cfg": cfg,
                "motivo": "mapeie os campos da resposta do RAG (só os nomes dos campos foram lidos)"}
    try:
        trechos = base.extrair(bruto, cfg)
    except base.ErroConexao as e:
        return {**out, "status": "precisa_configuracao", "faltando": [], "campos_detectados": det,
                "sugestao": base.sugerir(det), "_cfg": cfg, "motivo": e.motivo}
    return {**out, "status": "pronto", "trechos_no_teste": len(trechos), "_cfg": cfg}


def conectar_base(url: str | None = None, caminho_config: str | None = None, autenticacao: str | None = None,
                  cabecalho: str | None = None, mapeamento: dict | None = None, recalibrar: bool = False) -> dict:
    """Conecta ao RAG da equipe: valida, testa, calibra o corte com consultas placebo e grava a configuração."""
    d = diagnosticar_conexao(url, caminho_config, autenticacao, cabecalho, mapeamento)
    cfg = d.pop("_cfg", None)
    if d["status"] != "pronto":
        return d
    if recalibrar or not cfg.get("calibracao"):
        try:
            cfg["calibracao"] = base.calibrar(_adaptador(cfg), cfg)
        except base.ErroConexao as e:
            return {**d, "status": "erro_conexao", "codigo": e.codigo, "motivo": f"na calibração: {e.motivo}"}
    base.salvar(cfg, d["arquivo"])
    STATE["conexao"] = cfg
    avisos = []
    if not cfg["estudos_holdout"]:
        avisos.append("nenhum estudo marcado como holdout: não dá para checar vazamento")
    if cfg["calibracao"]["corte"] is None:
        avisos.append("nenhuma consulta placebo trouxe resultado: todo trecho devolvido conta como relevante")
    return {
        "status": "ok",
        "arquivo": d["arquivo"],
        "conexao": {"nome": cfg["nome"], "hash": base.hash_config(cfg)},
        "mapeamento": cfg["resposta"],
        "tipo_de_score": cfg["score"]["tipo"],
        "estudos_holdout": cfg["estudos_holdout"],
        "calibracao": cfg["calibracao"],
        "avisos": avisos,
        "limite": base.LIMITE,
    }


def _conexao() -> dict | None:
    if "conexao" not in STATE:
        caminho = base.caminho_padrao()
        if caminho.exists():
            try:
                STATE["conexao"] = base.carregar(caminho)
            except (base.ErroConfig, ValueError):
                return None
    return STATE.get("conexao")


def _suporte(pergunta: str, segmento: dict[str, str] | None, incluir_texto: bool) -> dict:
    cfg = _conexao()
    if cfg is None:
        return {"status": "nao_configurado", "motivo": "nenhuma base conectada; rode conectar_base com o RAG da equipe"}
    if base.faltando(cfg) or not cfg.get("calibracao"):
        return {"status": "nao_configurado", "motivo": "conexão incompleta ou sem calibração; rode conectar_base"}
    if base.precisa_credencial(cfg) and not base.credencial(cfg):
        return {"status": "nao_configurado", "motivo": f"falta a credencial: {_instrucao_credencial(cfg)}"}
    return base.sinal(cfg, _adaptador(cfg), PERGUNTA.get(pergunta, pergunta), segmento, incluir_texto)


def _e_stackoverflow(colunas: list[str]) -> bool:
    cols = set(colunas)
    return bool(cols & set(scales.PRESET_SO_2025["perguntas"])) and set(STRATA) <= cols


def importar_dados(fonte: str, fracao_holdout: float = 0.3, semente: int = 42,
                   dicionario: dict | str | None = None, consulta: str | None = None, aba: str | None = None) -> dict:
    """Importa as respostas humanas de um arquivo ou banco (veja `fontes.py`).

    `dicionario` (objeto, JSON ou caminho) diz quais colunas são perguntas e a escala. Sem dicionário: usa o da
    Stack Overflow 2025 se a fonte tiver as colunas dela; senão devolve `precisa_dicionario` com o resumo das
    colunas e um rascunho para completar.
    """
    if not 0 < fracao_holdout < 1:
        raise ValueError("fracao_holdout precisa estar entre 0 e 1")
    try:
        colunas, rows = fontes.ler(fonte, consulta, aba)
    except fontes.ErroFonte as e:
        return {"rotulo": LABEL, "status": "fonte_invalida", "erros": [str(e)]}
    if not rows:
        return {"rotulo": LABEL, "status": "fonte_invalida", "erros": ["a fonte não tem nenhuma linha"]}
    avisos: list[str] = []
    if dicionario is None:
        if not _e_stackoverflow(colunas):
            return {
                "rotulo": LABEL, "status": "precisa_dicionario",
                "motivo": "diga quais colunas são perguntas e a ordem das opções de cada escala: "
                          "chame importar_dados de novo com `dicionario`",
                "registros": len(rows),
                **questionario.detectar(colunas, rows),
                "formato": questionario.FORMATO,
            }
        d = {**scales.PRESET_SO_2025, "perguntas": {
            q: p for q, p in scales.PRESET_SO_2025["perguntas"].items() if q in colunas}}
        if d["id"] not in colunas:
            d.pop("id")
        avisos.append("sem dicionário: usando o da Stack Overflow Developer Survey 2025")
    else:
        try:
            d = questionario.carregar(dicionario)
        except (OSError, ValueError) as e:
            return {"rotulo": LABEL, "status": "dicionario_invalido", "erros": [f"não consegui ler o dicionário: {e}"]}
    erros = questionario.validar(d, colunas)
    if erros:
        return {"rotulo": LABEL, "status": "dicionario_invalido", "erros": erros}
    if d.get("id"):
        ids = Counter((r.get(d["id"]) or "").strip() for r in rows)
        repetidos = sum(1 for n in ids.values() if n > 1)
        if repetidos:
            return {"rotulo": LABEL, "status": "dados_invalidos",
                    "erros": [f"{repetidos} id(s) repetido(s) em {d['id']!r}: o CSV precisa ter uma linha por respondente"]}
    estratos = tuple(d.get("estratos", []))
    escalas = {q: dict(p["escala"]) for q, p in d["perguntas"].items()}
    ds = Dataset(rows=rows, holdout_idx=split_holdout(rows, fracao_holdout, semente, estratos),
                 escalas=escalas, separador=d.get("separador_multiplo", ";"))
    cob, avisos_cob = questionario.cobertura(rows, d)
    scales.ativar(d)
    STATE["ds"] = ds
    avisos.append("holdout sorteado por respondente, " + (
        f"estratificado por {', '.join(estratos)}" if estratos else "sem estratos (sorteio simples)"))
    return {
        "rotulo": LABEL,
        "status": "ok",
        "questionario": d.get("nome"),
        "registros": len(rows),
        "holdout": len(ds.holdout_idx),
        "perguntas_suportadas": sorted(escalas),
        "cobertura": cob,
        "dados_pessoais": {
            "status": "nao_verificado",
            "motivo": "a checagem de dados pessoais ainda não existe nesta versão; use apenas dados já anonimizados",
        },
        "avisos": avisos + avisos_cob,
    }


def amostrar(pergunta: str, respostas: list) -> dict:
    _check_question(pergunta)
    v = _coerce(pergunta, respostas)
    return {"rotulo": LABEL, "pergunta": pergunta, "amostras": len(v), "distribuicao": metrics.summary(v)}


def pontuar_resposta(pergunta: str, respostas: list, segmento: dict[str, str] | None = None,
                     incluir_texto: bool = False) -> dict:
    _check_question(pergunta)
    v = _coerce(pergunta, respostas)
    dispersao = _dispersao(v)
    margens = _margens(v)
    suporte = _suporte(pergunta, segmento, incluir_texto)
    avisos = ["terceiro sinal indisponível nesta versão", *suporte.pop("avisos", [])]
    if len(v) < 10:
        avisos.append("menos de 10 amostras: a dispersão é instável")
    return {
        "rotulo": LABEL,
        "pergunta": pergunta,
        "amostras": len(v),
        "distribuicao": metrics.summary(v),
        "margem_de_erro": margens,
        "insight": _insight_pontuar(v, margens),
        "confianca": {
            "dispersao": dispersao,
            "suporte_na_base": suporte,
            "acerto_historico": {"status": "nao_calculado", "motivo": "use validar_usuario para comparar com o holdout"},
        },
        "avisos": avisos,
    }


def validar_usuario(pergunta: str, segmento: dict[str, str], respostas: list, incluir_texto: bool = False) -> dict:
    _check_question(pergunta)
    ds = STATE.get("ds")
    if ds is None:
        raise ValueError("importe os dados antes com importar_dados")
    synth = _coerce(pergunta, respostas)
    human = ds.humans(pergunta, segmento, holdout=True)
    base = {"rotulo": LABEL, "pergunta": pergunta, "segmento": segmento, "amostras_sinteticas": len(synth)}
    if len(human) < MIN_HUMANS:
        return {**base, "status": "sem_holdout_suficiente", "humanos_no_holdout": len(human),
                "avisos": [f"menos de {MIN_HUMANS} humanos no segmento: nada foi calculado"]}
    ps, ph = metrics.pmf(synth), metrics.pmf(human)
    e = metrics.emd(ps, ph)
    lo, hi = metrics.bootstrap_emd_ci(synth, human)
    piso = metrics.human_noise_floor(human, len(synth))
    p_value = metrics.permutation_pvalue(synth, human)
    p_var = metrics.variance_ratio_pvalue(synth, human)
    var_s = float(synth.var(ddof=1)) if len(synth) > 1 else float("nan")
    var_h = float(human.var(ddof=1))
    razao = var_s / var_h if var_h else float("nan")
    avisos = []
    if not np.isnan(razao) and razao < 0.7:
        avisos.append("possível achatamento: o usuário varia bem menos que as pessoas")
    if len(synth) < 20:
        avisos.append("menos de 20 amostras sintéticas: intervalo largo")
    geral = ds.humans(pergunta, {}, holdout=False)
    melhor_geral = None
    if len(geral):
        sorteio = np.random.default_rng(0).choice(geral, size=len(synth))
        melhor_geral = bool(e < metrics.emd(metrics.pmf(sorteio), ps))
    dif = float(synth.mean()) - float(human.mean())
    razao_v = None if np.isnan(razao) else round(razao, 3)
    margem = max(metrics.margin_of_error_mean(synth) or 0.0, metrics.margin_of_error_mean(human) or 0.0)
    suporte = _suporte(pergunta, segmento, incluir_texto)
    avisos += suporte.pop("avisos", [])
    # acerto histórico ainda não existe: o nível não passa de média (a régua não baixa)
    faltam = 1 + (suporte["status"] != "ok")
    nivel = confiabilidade.nivel(dif, razao_v, bool(melhor_geral), sinais_completos=False)
    limitada = confiabilidade.limitada_por_sinais(dif, razao_v, bool(melhor_geral))
    return {
        **base,
        "status": "ok",
        "confiabilidade": {
            "nivel": nivel,
            "insight": confiabilidade.insight(dif, margem, razao_v, p_value, nivel, limitada, faltam),
            "limitada_por_sinais": limitada,
            "diferenca_de_media": round(dif, 3),
            "melhor_que_perguntar_a_qualquer_um": melhor_geral,
            "sinais": {
                "dispersao": _dispersao(synth),
                "suporte_na_base": suporte,
                "acerto_historico": {"status": "nao_calculado", "motivo": "faltam perguntas parecidas no holdout"},
            },
            "regra": confiabilidade.REGRA,
            "limite": confiabilidade.LIMITE,
        },
        "humanos_no_holdout": len(human),
        "distribuicao_sintetica": metrics.summary(synth),
        "distribuicao_humana": metrics.summary(human),
        "margem_de_erro": {"sintetico": _margens(synth), "humano": _margens(human)},
        "significancia": {
            "p_value": round(p_value, 4),
            "p_value_variancia": round(p_var, 4),
            "leitura_variancia": (
                "variância diferente da humana (p < 0,05)"
                if p_var < 0.05
                else "variância não distinguível da humana com esta amostra (p >= 0,05)"
            ),
            "teste": "permutação sobre a EMD e sobre o log da razão de variâncias (2000 sorteios cada)",
            "leitura": (
                "distinguível dos humanos (p < 0,05)"
                if p_value < 0.05
                else "não distinguível dos humanos com esta amostra (p >= 0,05)"
            ),
            "limite": "p alto com poucas amostras sintéticas significa falta de poder, não prova de fidelidade; olhe o intervalo e a margem de erro",
        },
        "insight": _insight_validar(synth, human, p_value, p_var, e, piso),
        "fidelidade": {
            "emd": round(e, 3),
            "intervalo_95": [round(lo, 3), round(hi, 3)],
            "piso_de_ruido_humano": round(piso, 3),
            "razao_de_variancia": None if np.isnan(razao) else round(razao, 3),
            "limite": "emd 0 = distribuição idêntica; compare com o piso, que é o melhor possível dado o tamanho da amostra",
        },
        "avisos": avisos,
    }
