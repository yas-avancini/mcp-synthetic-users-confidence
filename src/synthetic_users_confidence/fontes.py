"""Leitura das respostas humanas de qualquer fonte: arquivo ou banco SQL.

Tudo vira o mesmo formato, colunas + linhas como dicionários de texto, e segue o mesmo caminho
(dicionário do questionário, holdout, comparação).

Fontes:
- arquivo: .csv / .tsv / .txt (separador detectado), .xlsx / .xlsm (extra `excel`),
  .parquet (extra `parquet`), .json (lista de objetos) / .jsonl / .ndjson, .sqlite / .db (com `consulta`).
- banco SQL: `env:NOME_DA_VARIAVEL`, com a URL do SQLAlchemy nessa variável (extra `sql` + o driver do banco),
  ou a própria URL, desde que sem senha. Exige `consulta`, só de leitura (SELECT ou WITH).

A senha do banco nunca vai como argumento: os argumentos passam pelo LLM.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

csv.field_size_limit(sys.maxsize)

PADRAO_VARIAVEL = "SUC_DADOS_URL"
SEPARADORES_CSV = (",", ";", "\t", "|")
SQL_LEITURA = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
SQL_PROIBIDO = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|attach|detach|pragma|copy|call|exec|execute)\b",
    re.IGNORECASE,
)


class ErroFonte(ValueError):
    """Erro de leitura com mensagem segura (sem senha nem URL completa)."""


Tabela = tuple[list[str], list[dict[str, str]]]


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v != v:  # NaN
            return ""
        if v.is_integer():
            return str(int(v))  # 5.0 de Excel/Parquet casa com a opção "5"
    return str(v).strip()


def _tabela(colunas: list, linhas) -> Tabela:
    cols = [str(c) for c in colunas]
    if len(set(cols)) != len(cols):
        raise ErroFonte("há colunas com o mesmo nome; renomeie antes de importar")
    return cols, [{c: _texto(v) for c, v in zip(cols, linha)} for linha in linhas]


def ler(fonte: str, consulta: str | None = None, aba: str | None = None) -> Tabela:
    if not isinstance(fonte, str) or not fonte.strip():
        raise ErroFonte("informe a fonte: o caminho de um arquivo ou env:VARIAVEL com a URL do banco")
    fonte = fonte.strip()
    if fonte.startswith("env:"):
        return _sql(_url_da_variavel(fonte[4:] or PADRAO_VARIAVEL), consulta)
    if "://" in fonte:
        if urlsplit(fonte).password:
            raise ErroFonte(
                f"a URL do banco não pode ir como argumento com senha; coloque-a na variável {PADRAO_VARIAVEL} "
                f"e use fonte='env:{PADRAO_VARIAVEL}'"
            )
        return _sql(fonte, consulta)
    p = Path(fonte).expanduser()
    if not p.is_file():
        raise ErroFonte(f"arquivo não encontrado: {p.name}")
    ext = p.suffix.lower()
    if ext in (".sqlite", ".sqlite3", ".db"):
        return _sqlite(p, consulta)
    if consulta:
        raise ErroFonte("consulta só vale para bancos de dados")
    if ext in (".xlsx", ".xlsm"):
        return _excel(p, aba)
    if ext == ".parquet":
        return _parquet(p)
    if ext in (".json", ".jsonl", ".ndjson"):
        return _json(p)
    if ext in (".csv", ".tsv", ".txt", ""):
        return _csv(p, "\t" if ext == ".tsv" else None)
    raise ErroFonte(f"formato não suportado: {ext}. Use CSV, TSV, Excel, Parquet, JSON, SQLite ou um banco SQL")


# ---------- arquivos ----------

def _separador(cabecalho: str) -> str:
    return max(SEPARADORES_CSV, key=cabecalho.count) if any(s in cabecalho for s in SEPARADORES_CSV) else ","


def _csv(p: Path, sep: str | None) -> Tabela:
    with open(p, encoding="utf-8-sig", newline="") as fh:
        primeira = fh.readline()
        fh.seek(0)
        reader = csv.reader(fh, delimiter=sep or _separador(primeira))
        cab = next(reader, None)
        if not cab:
            raise ErroFonte("o arquivo está vazio")
        return _tabela(cab, (linha + [""] * (len(cab) - len(linha)) for linha in reader if any(linha)))


def _json(p: Path) -> Tabela:
    texto = p.read_text(encoding="utf-8-sig")
    try:
        if p.suffix.lower() == ".json":
            dados = json.loads(texto)
            if isinstance(dados, dict):  # {"respostas": [...]} ou {"data": [...]}
                listas = [v for v in dados.values() if isinstance(v, list)]
                dados = listas[0] if len(listas) == 1 else dados
        else:
            dados = [json.loads(linha) for linha in texto.splitlines() if linha.strip()]
    except json.JSONDecodeError as e:
        raise ErroFonte(f"JSON inválido na linha {e.lineno}") from None
    if not isinstance(dados, list) or not all(isinstance(r, dict) for r in dados):
        raise ErroFonte("o JSON precisa ser uma lista de objetos, um por respondente")
    colunas = list(dict.fromkeys(k for r in dados for k in r))
    aninhado = [c for c in colunas if any(isinstance(r.get(c), (dict, list)) for r in dados)]
    if aninhado:
        raise ErroFonte(f"campos aninhados não são suportados ({', '.join(aninhado[:3])}); achate o JSON antes")
    return _tabela(colunas, ([r.get(c) for c in colunas] for r in dados))


def _excel(p: Path, aba: str | None) -> Tabela:
    try:
        import openpyxl
    except ImportError:
        raise ErroFonte('para ler Excel, instale o extra: pip install "synthetic-users-confidence[excel]"') from None
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    try:
        if aba is not None and aba not in wb.sheetnames:
            raise ErroFonte(f"aba {aba!r} não existe; abas: {wb.sheetnames}")
        ws = wb[aba] if aba else wb.worksheets[0]
        linhas = ws.iter_rows(values_only=True)
        cab = next(linhas, None)
        if not cab or all(c is None for c in cab):
            raise ErroFonte("a primeira linha da aba precisa ter os nomes das colunas")
        n = max(i for i, c in enumerate(cab) if c is not None) + 1
        cab = [c if c is not None else f"coluna_{i + 1}" for i, c in enumerate(cab[:n])]
        return _tabela(cab, (list(r[:n]) for r in linhas if any(v is not None for v in r[:n])))
    finally:
        wb.close()


def _parquet(p: Path) -> Tabela:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ErroFonte('para ler Parquet, instale o extra: pip install "synthetic-users-confidence[parquet]"') from None
    t = pq.read_table(p)
    cols = t.column_names
    dados = t.to_pydict()
    return _tabela(cols, zip(*(dados[c] for c in cols)))


# ---------- bancos ----------

def _checar_consulta(consulta: str | None) -> str:
    if not consulta or not consulta.strip():
        raise ErroFonte("para ler de um banco, passe `consulta` com um SELECT que traga uma linha por respondente")
    q = consulta.strip().rstrip(";").strip()
    if ";" in q:
        raise ErroFonte("a consulta precisa ser um único comando")
    if not SQL_LEITURA.match(q) or SQL_PROIBIDO.search(q):
        raise ErroFonte("a consulta precisa ser só de leitura (SELECT ou WITH)")
    return q


def _sqlite(p: Path, consulta: str | None) -> Tabela:
    q = _checar_consulta(consulta)
    con = sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True)  # só leitura no próprio SQLite
    try:
        cur = con.execute(q)
        return _tabela([d[0] for d in cur.description], cur.fetchall())
    except sqlite3.Error as e:
        raise ErroFonte(f"erro na consulta: {e}") from None
    finally:
        con.close()


def _url_da_variavel(var: str) -> str:
    url = os.environ.get(var)
    if not url:
        raise ErroFonte(f"a variável {var} não está definida; coloque nela a URL do banco (formato do SQLAlchemy)")
    return url


def _sem_segredo(msg: str, url: str) -> str:
    partes = urlsplit(url)
    for s in (url, partes.password):
        if s:
            msg = msg.replace(s, "***")
    return msg


def _sql(url: str, consulta: str | None) -> Tabela:
    q = _checar_consulta(consulta)
    if url.startswith("sqlite:///"):
        return _sqlite(Path(url[len("sqlite:///"):]), q)
    try:
        import sqlalchemy as sa
    except ImportError:
        raise ErroFonte('para ler de um banco, instale o extra: pip install "synthetic-users-confidence[sql]" '
                        "e o driver do seu banco (psycopg, pymysql, sqlalchemy-bigquery...)") from None
    try:
        engine = sa.create_engine(url)
    except Exception as e:  # dialeto/driver ausente ou URL inválida
        raise ErroFonte(_sem_segredo(f"não consegui abrir o banco: {type(e).__name__}: {e}", url)) from None
    try:
        with engine.connect() as con:
            if engine.dialect.name == "postgresql":
                con.exec_driver_sql("SET TRANSACTION READ ONLY")
            try:
                res = con.execute(sa.text(q))
                return _tabela(list(res.keys()), res.fetchall())
            finally:
                con.rollback()  # nada que a consulta tenha feito fica gravado
    except ErroFonte:
        raise
    except Exception as e:
        raise ErroFonte(_sem_segredo(f"erro no banco: {type(e).__name__}: {e}", url)) from None
    finally:
        engine.dispose()
