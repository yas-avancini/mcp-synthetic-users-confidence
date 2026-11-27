"""Conexão com o RAG da equipe, contra um RAG falso local (sem rede externa)."""

import asyncio
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from synthetic_users_confidence import base, pagina_credencial, render, tools

TOKEN = "segredo-123-nao-vazar"

# Estudos sobre confiança na precisão da IA (AIAcc). Nada sobre sentimento (AISent).
DOCS = [
    {"id": "t1", "study": "estudo-01", "date": "2026-03", "text": "people trust the accuracy of the output"},
    {"id": "t2", "study": "estudo-02", "date": "2026-05", "text": "accuracy of output, trust is low"},
    {"id": "t3", "study": "estudo-07", "date": "2026-06", "text": "trust accuracy output"},
    {"id": "t4", "study": "estudo-03", "date": "2026-01", "text": "onboarding checkout pricing page conversion"},
]


def _palavras(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ú]+", t.lower()) if len(w) > 4}


class RAGFalso:
    """Busca por sobreposição de palavras. Formato aninhado, com score de similaridade ou distância."""

    def __init__(self, distancia=False, metodo="POST", raiz=False, atraso=0.0, status=None, docs=DOCS):
        self.distancia, self.metodo, self.raiz, self.atraso, self.status, self.docs = (
            distancia, metodo, raiz, atraso, status, docs)
        self.consultas: list[str] = []
        rag = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _busca(self, consulta, top_k):
                rag.consultas.append(consulta)
                if rag.atraso:
                    time.sleep(rag.atraso)
                if rag.status or self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    self.send_error(rag.status or 401)
                    return
                q = _palavras(consulta)
                itens = []
                for d in rag.docs:
                    sim = len(q & _palavras(d["text"])) / max(len(q), 1)
                    s = {"distance": round(1 - sim, 4)} if rag.distancia else {"score": round(sim, 4)}
                    itens.append({"id": d["id"], "content": d["text"], **s,
                                  "metadata": {"study_id": d["study"], "date": d["date"]}})
                itens.sort(key=lambda x: x.get("distance", -x.get("score", 0)))
                itens = itens[: int(top_k)]
                corpo = json.dumps(itens if rag.raiz else {"data": {"results": itens}, "took": 3}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(corpo)

            def do_POST(self):
                b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self._busca(b["query"], b["top_k"])

            def do_GET(self):
                qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                self._busca(qs["query"][0], qs["top_k"][0])

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/search"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def rag():
    r = RAGFalso()
    yield r
    r.fechar()


def _campos(d: dict, **extra) -> dict:
    s = d["sugestao"]
    return {"lista": s["lista"], "texto": s["texto"], "score": s["score"], "estudo": s["estudo"],
            "data": s["data"], "id": s["id"], "score_tipo": s["score_tipo"], **extra}


def _conectar(rag, monkeypatch, **extra):
    monkeypatch.setenv("SUC_RAG_TOKEN", TOKEN)
    d = tools.conectar_base(url=rag.url)
    assert d["status"] == "precisa_configuracao"
    return tools.conectar_base(url=rag.url, mapeamento=_campos(d, **extra))


def test_sem_conexao_o_sinal_diz_por_que():
    s = tools.pontuar_resposta("AIAcc", [3, 4] * 10)["confianca"]["suporte_na_base"]
    assert s["status"] == "nao_configurado" and "conectar_base" in s["motivo"]
    assert "exige RAG" not in json.dumps(s)


def test_recusa_segredo_no_arquivo_e_na_url(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"url": "https://x/s", "autenticacao": {"tipo": "bearer", "valor": "abc"}}))
    out = tools.conectar_base(caminho_config=str(p))
    assert out["status"] == "configuracao_invalida" and "abc" not in json.dumps(out)
    assert tools.conectar_base(url="https://x/s?api_key=abc")["status"] == "configuracao_invalida"
    assert tools.conectar_base(url="ftp://x/s")["status"] == "configuracao_invalida"


def test_sem_credencial_pede_a_variavel(rag):
    out = tools.conectar_base(url=rag.url)
    assert out["status"] == "precisa_credencial" and out["variavel"] == "SUC_RAG_TOKEN"
    assert "_cfg" not in out and rag.consultas == []  # nem chega a chamar o RAG


def test_detecta_so_nomes_dos_campos(rag, monkeypatch):
    monkeypatch.setenv("SUC_RAG_TOKEN", TOKEN)
    d = tools.conectar_base(url=rag.url)
    assert d["campos_detectados"]["listas"] == ["data.results"]
    assert "metadata.study_id" in d["campos_detectados"]["campos"]
    s = d["sugestao"]
    assert (s["texto"], s["score"], s["estudo"], s["data"], s["score_tipo"]) == (
        "content", "score", "metadata.study_id", "metadata.date", "similaridade")
    assert "people trust" not in json.dumps(d)  # conteúdo dos trechos não sai


def test_fluxo_completo_calibra_grava_e_calcula(rag, monkeypatch, tmp_path):
    out = _conectar(rag, monkeypatch, estudos_holdout="estudo-99")
    assert out["status"] == "ok" and out["calibracao"]["consultas_placebo"] == len(base.PLACEBO)
    salvo = json.loads((tmp_path / "conexao.json").read_text())
    assert salvo["calibracao"]["corte"] == out["calibracao"]["corte"]
    assert TOKEN not in json.dumps(salvo)

    tools.STATE.clear()  # nova sessão: relê o arquivo
    p = tools.pontuar_resposta("AIAcc", [3, 4] * 10)
    s = p["confianca"]["suporte_na_base"]
    assert s["status"] == "ok" and s["estudos"] == ["estudo-01", "estudo-02", "estudo-07"]
    assert s["conexao"]["hash"] == out["conexao"]["hash"] and s["consulta"] == tools.PERGUNTA["AIAcc"]
    assert "texto" not in s["trechos"][0]
    com_texto = tools.pontuar_resposta("AIAcc", [3, 4] * 10, incluir_texto=True)
    assert "texto" in com_texto["confianca"]["suporte_na_base"]["trechos"][0]
    assert "3 estudos" in render.pontuar_resposta(p)

    nada = tools.pontuar_resposta("AISent", [3, 4] * 10)["confianca"]["suporte_na_base"]
    assert nada["status"] == "ok" and nada["estudos_distintos"] == 0
    assert "não trata deste tema" in render.pontuar_resposta(tools.pontuar_resposta("AISent", [3, 4] * 10))


def test_score_de_distancia_e_get_com_lista_na_raiz(monkeypatch):
    r = RAGFalso(distancia=True, metodo="GET", raiz=True)
    try:
        monkeypatch.setenv("SUC_RAG_TOKEN", TOKEN)
        cfg = base.completar({"url": r.url, "metodo": "GET"})
        caminho = base.caminho_padrao()
        base.salvar(cfg, caminho)
        d = tools.conectar_base()
        assert d["campos_detectados"]["listas"] == [""] and d["sugestao"]["score_tipo"] == "distancia"
        out = tools.conectar_base(mapeamento=_campos(d))
        assert out["status"] == "ok" and out["tipo_de_score"] == "distancia"
        assert tools.pontuar_resposta("AIAcc", [3] * 10)["confianca"]["suporte_na_base"]["estudos_distintos"] == 3
        assert tools.pontuar_resposta("AISent", [3] * 10)["confianca"]["suporte_na_base"]["estudos_distintos"] == 0
    finally:
        r.fechar()


def test_vazamento_do_holdout_avisa_e_nao_conta(rag, monkeypatch):
    _conectar(rag, monkeypatch, estudos_holdout="estudo-07, estudo-99")
    p = tools.pontuar_resposta("AIAcc", [3, 4] * 10)
    s = p["confianca"]["suporte_na_base"]
    assert s["estudos_holdout_recuperados"] == ["estudo-07"] and "estudo-07" not in s["estudos"]
    assert any("holdout" in a and "inflada" in a for a in p["avisos"])


def test_sem_holdout_marcado_avisa(rag, monkeypatch):
    out = _conectar(rag, monkeypatch)
    assert any("vazamento" in a for a in out["avisos"])
    assert any("vazamento" in a for a in tools.pontuar_resposta("AIAcc", [3] * 10)["avisos"])


def test_timeout_vira_erro_conexao(rag, monkeypatch, tmp_path):
    _conectar(rag, monkeypatch)
    cfg = json.loads((tmp_path / "conexao.json").read_text())
    cfg["timeout_s"] = 0.3
    (tmp_path / "conexao.json").write_text(json.dumps(cfg))
    tools.STATE.clear()
    rag.atraso = 1.0
    s = tools.pontuar_resposta("AIAcc", [3] * 10)["confianca"]["suporte_na_base"]
    assert s["status"] == "erro_conexao" and s["codigo"] == "timeout"


def test_401_e_500_nao_vazam_o_token(rag, monkeypatch):
    monkeypatch.setenv("SUC_RAG_TOKEN", "chave-errada-xyz")
    out = tools.conectar_base(url=rag.url)
    assert out["status"] == "erro_conexao" and out["codigo"] == "http_401" and "credencial" in out["motivo"]
    assert "chave-errada-xyz" not in json.dumps(out)
    _conectar(rag, monkeypatch)
    rag.status = 500
    p = tools.pontuar_resposta("AIAcc", [3] * 10)
    assert p["confianca"]["suporte_na_base"]["codigo"] == "http_500"
    assert TOKEN not in json.dumps(p) and TOKEN not in render.pontuar_resposta(p)


def test_validar_usuario_traz_o_sinal_e_ajusta_o_insight(rag, monkeypatch, tmp_path):
    import csv

    labels = ["Highly distrust", "Somewhat distrust", "Neither trust nor distrust", "Somewhat trust", "Highly trust"]
    path = tmp_path / "r.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ResponseId", "Age", "DevType", "Employment", "AIAcc"])
        w.writeheader()
        for i in range(400):
            w.writerow({"ResponseId": i, "Age": "25-34", "DevType": "Dev", "Employment": "E", "AIAcc": labels[1 + i % 3]})
    tools.importar_dados(str(path))
    _conectar(rag, monkeypatch, estudos_holdout="estudo-99")
    out = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [2, 3, 4] * 20)
    s = out["confiabilidade"]["sinais"]["suporte_na_base"]
    assert s["status"] == "ok" and s["consulta"] == tools.PERGUNTA["AIAcc"]  # segmento fora da consulta padrão
    assert out["confiabilidade"]["nivel"] != "alta"  # acerto histórico ainda não existe
    md = render.validar_usuario(out)
    assert "**Suporte na base:**" in md and "Suporte na base de conhecimento:" not in md


def test_consulta_modelo_com_segmento_e_opcional():
    cfg = base.completar({})
    assert base.consulta(cfg, "Pergunta?", {"Age": "25-34"}) == "Pergunta?"
    cfg["consulta_modelo"] = "{texto_da_pergunta} Público: {segmento}"
    assert base.consulta(cfg, "Pergunta?", {"Age": "25-34"}) == "Pergunta? Público: 25-34"
    assert base.consulta(cfg, "Pergunta?", None) == "Pergunta? Público: todos"


def test_pagina_de_credencial_uso_unico():
    guardado = {}
    pag = pagina_credencial.abrir("pesquisas", lambda c: guardado.setdefault("c", c) and "memoria")
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(pag.url.rsplit("/", 1)[0] + "/errado")
    assert "Chave do RAG" in urllib.request.urlopen(pag.url).read().decode()
    urllib.request.urlopen(pag.url, data=b"chave=abc%2B1")
    assert guardado["c"] == "abc+1" and pag.recebida.is_set()
    time.sleep(0.2)
    with pytest.raises(OSError):
        urllib.request.urlopen(pag.url, timeout=1)


def test_credencial_sem_keyring_fica_na_memoria(monkeypatch):
    assert base.guardar_credencial("SUC_RAG_TOKEN", "x1") == "memoria"
    assert base.credencial(base.completar({})) == "x1"


# ---------- servidor MCP: elicitation de formulário, de URL e plano B ----------

def _chamar(nome, args, callback=None):
    from mcp.client.client import Client

    from synthetic_users_confidence.server import mcp

    async def go():
        async with Client(mcp, elicitation_callback=callback) as c:
            try:
                return await c.call_tool(nome, args)
            except Exception as e:  # sai do `async with` sem virar ExceptionGroup
                return e

    r = asyncio.run(go())
    if isinstance(r, Exception):
        raise r
    return r


def _json(r):
    return json.loads(r.content[0].text)


def test_servidor_pede_mapeamento_por_formulario(rag, monkeypatch):
    import mcp_types as types

    monkeypatch.setenv("SUC_RAG_TOKEN", TOKEN)
    pedidos = []

    async def aceita_sugestao(ctx, params):
        pedidos.append(params)
        props = params.requested_schema["properties"]
        conteudo = {k: v["default"] for k, v in props.items()}
        conteudo["estudos_holdout"] = "estudo-07"
        return types.ElicitResult(action="accept", content=conteudo)

    out = _json(_chamar("conectar_base", {"url": rag.url}, aceita_sugestao))
    assert out["status"] == "ok" and out["estudos_holdout"] == ["estudo-07"]
    assert out["mapeamento"]["lista"] == "data.results" and out["mapeamento"]["estudo"] == "metadata.study_id"
    assert pedidos and "lista" not in pedidos[0].requested_schema["properties"]  # uma lista só: não pergunta


def test_servidor_sem_elicitation_usa_plano_b(rag, monkeypatch):
    monkeypatch.setenv("SUC_RAG_TOKEN", TOKEN)
    out = _json(_chamar("conectar_base", {"url": rag.url}))
    assert out["status"] == "precisa_configuracao" and out["sugestao"]["estudo"] == "metadata.study_id"
    campos = _campos(out)
    ok = _json(_chamar("conectar_base", {"url": rag.url, "campos": campos}))
    assert ok["status"] == "ok"


def test_servidor_recusa_formulario_explica_o_caminho(rag, monkeypatch):
    import mcp_types as types

    monkeypatch.setenv("SUC_RAG_TOKEN", TOKEN)

    async def recusa(ctx, params):
        return types.ElicitResult(action="decline")

    out = _json(_chamar("conectar_base", {"url": rag.url}, recusa))
    assert out["status"] == "precisa_configuracao" and "recusado" in out["motivo"]


def test_servidor_pede_a_chave_por_url_local(rag):
    import mcp_types as types
    from mcp import UrlElicitationRequiredError

    async def aceita(ctx, params):
        props = params.requested_schema["properties"]
        return types.ElicitResult(action="accept", content={k: v["default"] for k, v in props.items()})

    with pytest.raises(UrlElicitationRequiredError) as e:
        _chamar("conectar_base", {"url": rag.url}, aceita)
    url = e.value.elicitations[0].url
    assert url.startswith("http://127.0.0.1:") and TOKEN not in str(e.value)
    urllib.request.urlopen(url, data=urllib.parse.urlencode({"chave": TOKEN}).encode())
    out = _json(_chamar("conectar_base", {"url": rag.url}, aceita))
    assert out["status"] == "ok" and TOKEN not in json.dumps(out)
