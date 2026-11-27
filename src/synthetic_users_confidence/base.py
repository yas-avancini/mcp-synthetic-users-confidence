"""Conexão com o RAG da equipe (adaptador http) e o sinal suporte_na_base.

O projeto não indexa documentos: chama o RAG que a equipe já tem. Spec:
docs/specs/2026-11-27-conexao-base-spec.md
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import numpy as np

SERVICO = "synthetic-users-confidence"
TOP_K = 10
TIMEOUT_S = 10.0
PERCENTIL = 95
CONSULTA_TESTE = "teste de conexão"
# Só a pergunta: palavras como "Público: gestores de marketing" casam com quase todo trecho de uma base de
# pesquisa de produto e inflam o sinal. Quem quiser o segmento na consulta usa {segmento} no consulta_modelo.
CONSULTA_MODELO = "{texto_da_pergunta}"
REQUISICAO_PADRAO = {"query": "{consulta}", "top_k": "{top_k}"}
AUTENTICACAO_PADRAO = {"tipo": "bearer", "variavel": "SUC_RAG_TOKEN"}
TIPOS_AUTENTICACAO = ("bearer", "cabecalho", "nenhuma")
OBRIGATORIOS = ("lista", "texto", "score", "estudo")
SEM_CAMPO = "(nenhum)"  # opção do formulário para campo opcional ausente
RAIZ = "(raiz)"  # opção do formulário quando a resposta já é a lista
SEGREDOS = {"valor", "token", "senha", "password", "secret", "api_key", "apikey", "chave", "key"}
LIMITE = (
    "mede se a base trata do tema, não se concorda com a resposta; score não comparável entre ferramentas; "
    "corte calibrado com consultas placebo nesta base"
)

# Temas que nenhuma pesquisa de produto trata: o melhor score delas mostra o "ruído" da busca nesta base.
# Versionadas aqui; mudar a lista muda a calibração (o hash da conexão registra o corte resultante).
PLACEBO = (
    "receita de bolo de cenoura com cobertura de chocolate",
    "regras oficiais do críquete",
    "como trocar o óleo de um motor a diesel",
    "migração anual das baleias jubarte",
    "técnicas de poda de bonsai",
    "história da dinastia Ming",
    "como afinar um violino",
    "ciclo de vida das borboletas monarca",
    "receita de pão de fermentação natural",
    "regras do xadrez para o roque",
    "composição química da água do mar",
    "como montar um aquário de água salgada",
    "órbita de Plutão e seus satélites",
    "técnica de pintura a óleo do Renascimento",
    "como fazer queijo minas curado",
    "treino de maratona para iniciantes",
    "erupção do Vesúvio no ano 79",
    "cultivo de orquídeas em apartamento",
    "regras do vôlei de praia",
    "como funciona a fotossíntese",
    "receita de feijoada tradicional",
    "manutenção de bicicleta de estrada",
    "formação de estalactites em cavernas",
    "história do samba no Rio de Janeiro",
    "como tricotar um cachecol",
    "alimentação de cavalos de corrida",
    "arquitetura das pirâmides do Egito",
    "previsão de marés em portos",
    "como preparar café coado",
    "reprodução de tartarugas marinhas",
)


class ErroConfig(ValueError):
    """Configuração inválida ou insegura (sem conteúdo do segredo na mensagem)."""


class ErroConexao(Exception):
    def __init__(self, codigo: str, motivo: str):
        super().__init__(f"{codigo}: {motivo}")
        self.codigo, self.motivo = codigo, motivo


@dataclass
class Trecho:
    id: str
    estudo: str | None
    data: str | None
    fonte: str | None
    score: float
    texto: str


class Adaptador(Protocol):
    def buscar(self, consulta: str, top_k: int) -> list[Trecho]: ...


# ---------- configuração ----------

def caminho_padrao() -> Path:
    return Path(os.environ.get("SUC_CONEXAO", "~/.config/synthetic-users-confidence/conexao.json")).expanduser()


def _procura_segredo(obj: Any, onde: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in SEGREDOS:
                raise ErroConfig(
                    f"o campo {onde}{k} parece um segredo: segredo nunca vai no arquivo; "
                    "use autenticacao.variavel (nome da variável de ambiente)"
                )
            _procura_segredo(v, f"{onde}{k}.")
    elif isinstance(obj, list):
        for v in obj:
            _procura_segredo(v, onde)


def validar(cfg: dict) -> None:
    """Recusa configuração insegura. Não verifica se está completa (isso é `faltando`)."""
    _procura_segredo(cfg)
    url = cfg.get("url") or ""
    if url:
        partes = urllib.parse.urlsplit(url)
        if partes.scheme not in ("http", "https"):
            raise ErroConfig("a url precisa começar com http:// ou https://")
        if partes.password or any(k.lower() in SEGREDOS for k, _ in urllib.parse.parse_qsl(partes.query)):
            raise ErroConfig("a url não pode levar senha nem chave; use autenticacao.variavel")
    tipo = cfg.get("autenticacao", {}).get("tipo", "bearer")
    if tipo not in TIPOS_AUTENTICACAO:
        raise ErroConfig(f"autenticacao.tipo deve ser um de {TIPOS_AUTENTICACAO}")
    if cfg.get("score", {}).get("tipo", "similaridade") not in ("similaridade", "distancia"):
        raise ErroConfig("score.tipo deve ser 'similaridade' ou 'distancia'")


def faltando(cfg: dict) -> list[str]:
    out = [] if cfg.get("url") else ["url"]
    resposta = cfg.get("resposta", {})
    out += [f"resposta.{k}" for k in OBRIGATORIOS if k not in resposta]
    if cfg.get("score", {}).get("tipo") is None:
        out.append("score.tipo")
    aut = cfg.get("autenticacao", {})
    if aut.get("tipo") == "cabecalho" and not aut.get("cabecalho"):
        out.append("autenticacao.cabecalho")
    return out


def completar(cfg: dict) -> dict:
    """Preenche os padrões sem sobrescrever o que já veio."""
    cfg = copy.deepcopy(cfg)
    cfg.setdefault("nome", "base-da-equipe")
    cfg.setdefault("adaptador", "http")
    cfg.setdefault("metodo", "POST")
    cfg.setdefault("autenticacao", dict(AUTENTICACAO_PADRAO))
    cfg["autenticacao"].setdefault("variavel", AUTENTICACAO_PADRAO["variavel"])
    cfg.setdefault("requisicao", dict(REQUISICAO_PADRAO))
    cfg.setdefault("resposta", {})
    cfg.setdefault("score", {})
    cfg.setdefault("consulta_modelo", CONSULTA_MODELO)
    cfg.setdefault("top_k", TOP_K)
    cfg.setdefault("estudos_holdout", [])
    return cfg


def hash_config(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def carregar(caminho: str | Path) -> dict:
    with open(caminho, encoding="utf-8") as fh:
        cfg = json.load(fh)
    validar(cfg)
    return cfg


def salvar(cfg: dict, caminho: str | Path) -> None:
    validar(cfg)
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- credencial ----------

_MEMORIA: dict[str, str] = {}


def precisa_credencial(cfg: dict) -> bool:
    return cfg.get("autenticacao", {}).get("tipo", "bearer") != "nenhuma"


def credencial(cfg: dict) -> str | None:
    """Variável de ambiente, depois o cofre do sistema (keyring, se instalado), depois a memória da sessão."""
    var = cfg.get("autenticacao", {}).get("variavel", AUTENTICACAO_PADRAO["variavel"])
    if os.environ.get(var):
        return os.environ[var]
    try:
        import keyring  # opcional: pip install "synthetic-users-confidence[cofre]"

        valor = keyring.get_password(SERVICO, var)
        if valor:
            return valor
    except Exception:  # sem keyring ou sem cofre disponível
        pass
    return _MEMORIA.get(var)


def guardar_credencial(variavel: str, valor: str) -> str:
    """Guarda no cofre do sistema; sem keyring, só na memória desta sessão. Devolve onde guardou."""
    try:
        import keyring

        keyring.set_password(SERVICO, variavel, valor)
        return "cofre"
    except Exception:
        _MEMORIA[variavel] = valor
        return "memoria"


# ---------- adaptador http ----------

def pegar(obj: Any, caminho: str) -> Any:
    """Caminho com ponto (metadata.study_id); vazio é a raiz."""
    if not caminho:
        return obj
    for parte in caminho.split("."):
        if isinstance(obj, dict) and parte in obj:
            obj = obj[parte]
        elif isinstance(obj, list) and parte.isdigit() and int(parte) < len(obj):
            obj = obj[int(parte)]
        else:
            return None
    return obj


def _preencher(modelo: Any, valores: dict[str, Any]) -> Any:
    if isinstance(modelo, dict):
        return {k: _preencher(v, valores) for k, v in modelo.items()}
    if isinstance(modelo, list):
        return [_preencher(v, valores) for v in modelo]
    if isinstance(modelo, str):
        for k, v in valores.items():
            if modelo == "{" + k + "}":
                return v  # mantém o tipo (top_k continua inteiro)
        for k, v in valores.items():
            modelo = modelo.replace("{" + k + "}", str(v))
        return modelo
    return modelo


class AdaptadorHTTP:
    def __init__(self, cfg: dict, token: str | None):
        self.cfg, self._token = cfg, token

    def _cabecalhos(self) -> dict[str, str]:
        h = {"Accept": "application/json", "User-Agent": SERVICO}
        aut = self.cfg.get("autenticacao", {})
        if aut.get("tipo", "bearer") == "nenhuma":
            return h
        if not self._token:
            raise ErroConexao("sem_credencial", f"defina a variável {aut.get('variavel')} ou rode conectar_base")
        if aut.get("tipo", "bearer") == "bearer":
            h["Authorization"] = f"Bearer {self._token}"
        else:
            h[aut["cabecalho"]] = self._token
        return h

    def requisitar(self, consulta: str, top_k: int) -> Any:
        corpo = _preencher(self.cfg.get("requisicao", REQUISICAO_PADRAO), {"consulta": consulta, "top_k": top_k})
        url, dados = self.cfg["url"], None
        h = self._cabecalhos()
        if self.cfg.get("metodo", "POST").upper() == "GET":
            sep = "&" if "?" in url else "?"
            url = url + sep + urllib.parse.urlencode(corpo, doseq=True)
        else:
            dados = json.dumps(corpo).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=dados, headers=h, method=self.cfg.get("metodo", "POST").upper())
        try:
            with urllib.request.urlopen(req, timeout=float(self.cfg.get("timeout_s", TIMEOUT_S))) as r:
                bruto = r.read(20_000_000)
        except urllib.error.HTTPError as e:
            dica = " (confira a credencial e o tipo de autenticação)" if e.code in (401, 403) else ""
            raise ErroConexao(f"http_{e.code}", f"o RAG respondeu {e.code}{dica}") from None
        except (TimeoutError, socket.timeout):
            raise ErroConexao("timeout", "o RAG não respondeu a tempo") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (TimeoutError, socket.timeout)):
                raise ErroConexao("timeout", "o RAG não respondeu a tempo") from None
            raise ErroConexao("sem_conexao", f"não foi possível conectar: {type(e.reason).__name__}") from None
        try:
            return json.loads(bruto)
        except ValueError:
            raise ErroConexao("resposta_invalida", "o RAG não devolveu JSON") from None

    def buscar(self, consulta: str, top_k: int) -> list[Trecho]:
        return extrair(self.requisitar(consulta, top_k), self.cfg)


def extrair(bruto: Any, cfg: dict) -> list[Trecho]:
    m = cfg["resposta"]
    lista = pegar(bruto, m["lista"])
    if not isinstance(lista, list):
        raise ErroConexao("resposta_invalida", f"resposta.lista ({m['lista'] or 'raiz'}) não é uma lista")
    out = []
    for i, item in enumerate(lista):
        score = pegar(item, m["score"])
        try:
            score = float(score)
        except (TypeError, ValueError):
            raise ErroConexao("resposta_invalida", f"resposta.score ({m['score']}) não é número") from None
        txt = lambda k: None if not m.get(k) or pegar(item, m[k]) is None else str(pegar(item, m[k]))
        out.append(Trecho(id=txt("id") or str(i), estudo=txt("estudo"), data=txt("data"), fonte=txt("fonte"),
                          score=score, texto=txt("texto") or ""))
    return out


# ---------- detecção do mapeamento ----------

def _folhas(obj: Any, prefixo: str = "", nivel: int = 0) -> list[str]:
    out = []
    if isinstance(obj, dict) and nivel < 3:
        for k, v in obj.items():
            out += _folhas(v, f"{prefixo}{k}.", nivel + 1)
    elif not isinstance(obj, (dict, list)):
        out.append(prefixo[:-1])
    return out


def detectar(bruto: Any) -> dict:
    """Só os NOMES dos campos da resposta de teste, nunca o conteúdo."""
    listas = []
    if isinstance(bruto, list) and bruto and isinstance(bruto[0], dict):
        listas.append("")
    for caminho in _caminhos_dict(bruto):
        v = pegar(bruto, caminho)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            listas.append(caminho)
    campos = sorted(set(_folhas(pegar(bruto, listas[0])[0]))) if listas else []
    return {"listas": listas, "campos": campos}


def _caminhos_dict(obj: Any, prefixo: str = "", nivel: int = 0) -> list[str]:
    if not isinstance(obj, dict) or nivel >= 3:
        return []
    out = []
    for k, v in obj.items():
        out.append(prefixo + k)
        out += _caminhos_dict(v, f"{prefixo}{k}.", nivel + 1)
    return out


_PISTAS = {
    "texto": ("page_content", "content", "text", "texto", "conteudo", "chunk", "document", "body"),
    "score": ("score", "similarity", "relevance", "distance", "distancia", "similaridade"),
    "estudo": ("study", "estudo", "document_id", "doc_id", "source_id", "file", "source", "fonte"),
    "data": ("date", "data", "created", "timestamp"),
    "id": ("chunk_id", "_id", "id"),
    "fonte": ("source", "fonte", "url", "file", "title"),
}


def sugerir(det: dict) -> dict:
    campos = det["campos"]
    sug: dict[str, str | None] = {"lista": det["listas"][0] if det["listas"] else None}
    for alvo, pistas in _PISTAS.items():
        sug[alvo] = next((c for p in pistas for c in campos if c.split(".")[-1].lower() == p), None) or next(
            (c for p in pistas for c in campos if p in c.lower()), None
        )
    sug["score_tipo"] = "distancia" if sug["score"] and "dist" in sug["score"].lower() else "similaridade"
    return sug


# ---------- calibração e sinal ----------

def proximidade(score: float, tipo: str) -> float:
    """Maior é mais perto, nos dois sentidos de score."""
    return -score if tipo == "distancia" else score


def calibrar(adaptador: Adaptador, cfg: dict) -> dict:
    tipo, k = cfg["score"]["tipo"], int(cfg.get("top_k", TOP_K))
    melhores = []
    for q in PLACEBO:
        trechos = adaptador.buscar(q, k)
        if trechos:
            melhores.append(max(proximidade(t.score, tipo) for t in trechos))
    corte = None
    if melhores:
        p = float(np.percentile(melhores, PERCENTIL))
        corte = round(proximidade(p, tipo), 6)  # volta para a unidade do RAG
    return {
        "corte": corte,
        "consultas_placebo": len(PLACEBO),
        "com_resultado": len(melhores),
        "percentil": PERCENTIL,
        "feita_em": date.today().isoformat(),
    }


def relevante(t: Trecho, cfg: dict) -> bool:
    corte = cfg["calibracao"]["corte"]
    if corte is None:  # nenhuma consulta placebo trouxe resultado: o próprio RAG já filtra
        return True
    tipo = cfg["score"]["tipo"]
    return proximidade(t.score, tipo) > proximidade(corte, tipo)


def consulta(cfg: dict, texto_da_pergunta: str, segmento: dict[str, str] | None) -> str:
    seg = ", ".join(segmento.values()) if segmento else "todos"
    modelo = cfg.get("consulta_modelo", CONSULTA_MODELO)
    return modelo.replace("{texto_da_pergunta}", texto_da_pergunta).replace("{segmento}", seg)


def sinal(cfg: dict, adaptador: Adaptador, texto_da_pergunta: str, segmento: dict[str, str] | None,
          incluir_texto: bool = False) -> dict:
    """O sinal suporte_na_base, com status ok ou erro_conexao. Quem chama trata o nao_configurado."""
    q = consulta(cfg, texto_da_pergunta, segmento)
    conexao = {"nome": cfg.get("nome"), "hash": hash_config(cfg)}
    try:
        trechos = adaptador.buscar(q, int(cfg.get("top_k", TOP_K)))
    except ErroConexao as e:
        return {"status": "erro_conexao", "codigo": e.codigo, "motivo": e.motivo, "consulta": q, "conexao": conexao}
    holdout = set(cfg.get("estudos_holdout", []))
    relevantes = [t for t in trechos if relevante(t, cfg)]
    vazados = sorted({t.estudo for t in relevantes if t.estudo in holdout})
    validos = [t for t in relevantes if t.estudo not in holdout]
    estudos = sorted({t.estudo for t in validos if t.estudo})
    avisos = []
    if vazados:
        avisos.append(
            f"a base contém estudos do holdout ({', '.join(vazados)}): se o usuário sintético consulta esta base, "
            "a validação pode estar inflada; eles não entram na contagem"
        )
    if not holdout:
        avisos.append("não dá para checar vazamento: nenhum estudo marcado como holdout na conexão")
    sem_estudo = sum(1 for t in validos if not t.estudo)
    if sem_estudo:
        avisos.append(f"{sem_estudo} trecho(s) relevante(s) sem estudo identificado: não entram na contagem de estudos")
    tipo = cfg["score"]["tipo"]
    melhor = max((t.score for t in validos), key=lambda s: proximidade(s, tipo), default=None)
    campos = ("id", "estudo", "data", "fonte", "score") + (("texto",) if incluir_texto else ())
    return {
        "status": "ok",
        "estudos_distintos": len(estudos),
        "estudos": estudos,
        "trechos_relevantes": len(validos),
        "trechos_recuperados": len(trechos),
        "score_mais_proximo": melhor,
        "corte": cfg["calibracao"]["corte"],
        "tipo_de_score": tipo,
        "consulta": q,
        "estudos_holdout_recuperados": vazados,
        "conexao": conexao,
        "trechos": [{k: v for k, v in asdict(t).items() if k in campos} for t in validos],
        "avisos": avisos,
        "limite": LIMITE,
    }
