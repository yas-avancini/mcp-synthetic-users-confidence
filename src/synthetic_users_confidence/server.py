"""Servidor MCP (stdio). Cada ferramenta devolve JSON estruturado."""

from __future__ import annotations

from typing import Annotated, Any, Literal

import mcp_types as types
from mcp import UrlElicitationRequiredError
from mcp.server.mcpserver import AcceptedElicitation, Context, Elicit, ElicitationResult, MCPServer, Resolve
from pydantic import Field, create_model

from . import base, pagina_credencial, render, tools

mcp = MCPServer("synthetic-users-confidence")


@mcp.tool()
def importar_dados(
    fonte: str, fracao_holdout: float = 0.3, semente: int = 42, dicionario: dict | str | None = None,
    consulta: str | None = None, aba: str | None = None,
) -> dict:
    """Importa as respostas humanas (uma linha por respondente) e separa o holdout.

    fonte: caminho de um arquivo (CSV, TSV, Excel, Parquet, JSON, JSONL, SQLite) ou um banco SQL:
    'env:SUC_DADOS_URL' lê a URL do SQLAlchemy dessa variável de ambiente. Nunca passe senha como argumento.
    consulta: SELECT só de leitura, obrigatório para bancos. aba: aba do Excel (padrão: a primeira).
    dicionario: objeto, JSON ou caminho de um .json que diz quais colunas são perguntas, a escala de 1 a 5
    de cada uma e os estratos do holdout. Sem ele, numa fonte que não é da Stack Overflow 2025, a ferramenta
    devolve status `precisa_dicionario` com as colunas, as opções comuns e um rascunho (`sugestao`):
    confirme a ordem das escalas com a pessoa e chame de novo com `dicionario`.
    """
    return tools.importar_dados(fonte, fracao_holdout, semente, dicionario, consulta, aba)


@mcp.tool()
def amostrar(pergunta: str, respostas: list) -> dict:
    """Resume as N respostas sintéticas já coletadas (contagens, média, variância)."""
    return tools.amostrar(pergunta, respostas)


@mcp.tool()
def pontuar_resposta(
    pergunta: str, respostas: list, segmento: dict[str, str] | None = None, incluir_texto: bool = False,
    formato: str = "markdown",
) -> str | dict:
    """Sinais de confiança das respostas sintéticas. formato: 'markdown' (tabela) ou 'json'.

    incluir_texto=True traz o texto dos trechos da base (por padrão, só id, estudo, data e score).
    """
    out = tools.pontuar_resposta(pergunta, respostas, segmento, incluir_texto)
    return out if formato == "json" else render.pontuar_resposta(out)


@mcp.tool()
def validar_usuario(
    pergunta: str, segmento: dict[str, str], respostas: list, incluir_texto: bool = False, formato: str = "markdown"
) -> str | dict:
    """Compara o usuário sintético com os humanos do holdout. formato: 'markdown' (tabela) ou 'json'."""
    out = tools.validar_usuario(pergunta, segmento, respostas, incluir_texto)
    return out if formato == "json" else render.validar_usuario(out)


# ---------- conexão com o RAG da equipe ----------

def _suporta(ctx: Context, modo: str) -> bool:
    cap = ctx.client_capabilities
    el = cap.elicitation if cap else None
    if el is None:
        return False
    if modo == "form":
        return el.form is not None or el.url is None  # `elicitation: {}` antigo vale como formulário
    return el.url is not None


def _opcoes(valores: list[str], sugestao: str | None, extra: str | None = None) -> tuple[Any, Any]:
    vals = list(dict.fromkeys(([extra] if extra else []) + valores)) or [base.SEM_CAMPO]
    padrao = sugestao if sugestao in vals else (extra or vals[0])
    return Literal[tuple(vals)], padrao  # type: ignore[valid-type]


def _formulario(d: dict):
    det, sug = d["campos_detectados"], d["sugestao"]
    campos, listas = det["campos"], [base.RAIZ if x == "" else x for x in det["listas"]]
    sug_lista = base.RAIZ if sug.get("lista") == "" else sug.get("lista")
    defs: dict[str, Any] = {}
    if len(listas) != 1:
        t, p = _opcoes(listas, sug_lista)
        defs["lista"] = (t, Field(p, description="Onde está a lista de resultados na resposta"))
    for nome, desc in (("texto", "Campo com o texto do trecho"), ("score", "Campo com o score"),
                       ("estudo", "Campo que identifica o estudo (pesquisa) de origem")):
        t, p = _opcoes(campos, sug.get(nome))
        defs[nome] = (t, Field(p, description=desc))
    for nome, desc in (("data", "Campo com a data (opcional)"), ("id", "Campo com o id do trecho (opcional)")):
        t, p = _opcoes(campos, sug.get(nome), base.SEM_CAMPO)
        defs[nome] = (t, Field(p, description=desc))
    defs["score_tipo"] = (Literal["similaridade", "distancia"],
                          Field(sug.get("score_tipo", "similaridade"),
                                description="similaridade: maior é mais perto; distancia: menor é mais perto"))
    defs["estudos_holdout"] = (str, Field("", description="Ids dos estudos do holdout, separados por vírgula"))
    return create_model("MapeamentoRAG", **defs)


def _pedir_mapeamento(
    ctx: Context, url: str | None = None, caminho_config: str | None = None, autenticacao: str | None = None,
    cabecalho: str | None = None,
):
    """Resolver: só pergunta quando falta o mapeamento e o cliente aceita formulário."""
    if not _suporta(ctx, "form"):
        return None
    d = tools.diagnosticar_conexao(url, caminho_config, autenticacao, cabecalho)
    if d["status"] != "precisa_configuracao" or "campos_detectados" not in d or not d["campos_detectados"]["listas"]:
        return None
    modelo = _formulario(d)
    return Elicit(
        "Conectar a base da equipe: diga onde estão os campos na resposta do RAG. "
        "Só os nomes dos campos foram lidos, não o conteúdo.",
        modelo,
    )


@mcp.tool()
def conectar_base(
    ctx: Context,
    url: str | None = None,
    caminho_config: str | None = None,
    autenticacao: Literal["bearer", "cabecalho", "nenhuma"] | None = None,
    cabecalho: str | None = None,
    campos: dict[str, str] | None = None,
    recalibrar: bool = False,
    mapeamento: Annotated[ElicitationResult[Any], Resolve(_pedir_mapeamento)] = None,
) -> dict:
    """Conecta o RAG da equipe para calcular o sinal suporte_na_base.

    url: endpoint de busca do RAG. caminho_config: um conexao.json já preenchido (sem segredos).
    autenticacao: bearer (padrão), cabecalho (informe o nome em `cabecalho`) ou nenhuma.
    campos: mapeamento dos campos da resposta (lista, texto, score, estudo, data, id, score_tipo,
    estudos_holdout), para clientes sem formulário: use `campos_detectados` e `sugestao` da chamada anterior.
    A chave NUNCA vai como argumento: ela vem da variável de ambiente indicada ou de uma página local.
    """
    m = dict(campos) if campos else None
    if isinstance(mapeamento, AcceptedElicitation) and mapeamento.data is not None:
        m = {**(m or {}), **mapeamento.data.model_dump()}
        d = tools.diagnosticar_conexao(url, caminho_config, autenticacao, cabecalho)
        if "campos_detectados" in d and len(d["campos_detectados"]["listas"]) == 1 and "lista" not in m:
            m["lista"] = d["campos_detectados"]["listas"][0]
    out = tools.conectar_base(url, caminho_config, autenticacao, cabecalho, m, recalibrar)
    if out["status"] == "precisa_credencial" and _suporta(ctx, "url"):
        cfg, _ = tools._cfg_inicial(url, caminho_config, autenticacao, cabecalho)
        var = cfg["autenticacao"]["variavel"]
        pag = pagina_credencial.abrir(cfg["nome"], lambda chave: base.guardar_credencial(var, chave))
        raise UrlElicitationRequiredError(
            [types.ElicitRequestURLParams(
                message=f"Abra {pag.url} para colar a chave do RAG; depois rode conectar_base de novo.",
                url=pag.url, elicitation_id=pag.id,
            )],
            message=f"Falta a chave do RAG. Abra {pag.url} (página local, de uso único) e rode conectar_base de novo.",
        )
    if out["status"] == "precisa_configuracao" and mapeamento is not None and not isinstance(mapeamento, AcceptedElicitation):
        out["motivo"] += "; o formulário foi recusado: passe caminho_config com um conexao.json preenchido"
    return out


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
