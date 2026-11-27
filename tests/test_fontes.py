"""Mesmas respostas em qualquer fonte (arquivo ou banco) dão o mesmo resultado."""

import csv
import json
import sqlite3

import pytest

from synthetic_users_confidence import fontes, tools

OPCOES = ["Discordo totalmente", "Discordo", "Neutro", "Concordo", "Concordo totalmente"]
COLUNAS = ["respondente", "cargo", "canais", "confia_ia", "nota"]
SENHA = "segredo-do-banco-123"


def _linhas():
    return [
        {"respondente": f"r{i}", "cargo": "Gerente" if i % 2 else "Analista",
         "canais": "Meta;Google" if i % 4 == 0 else "Meta", "confia_ia": OPCOES[1 + i % 3], "nota": 1 + i % 5}
        for i in range(200)
    ]


DIC = {
    "id": "respondente", "estratos": ["cargo"], "separador_multiplo": ";",
    "perguntas": {
        "confia_ia": {"escala": {o: i + 1 for i, o in enumerate(OPCOES)}},
        "nota": {"escala": {str(n): n for n in range(1, 6)}},
    },
}


def _sqlite(tmp_path):
    p = tmp_path / "pesquisa.db"
    con = sqlite3.connect(p)
    con.execute("create table respostas (respondente text, cargo text, canais text, confia_ia text, nota integer)")
    con.executemany("insert into respostas values (?, ?, ?, ?, ?)", [tuple(r.values()) for r in _linhas()])
    con.commit()
    con.close()
    return p


def _arquivo(tmp_path, formato):
    linhas = _linhas()
    p = tmp_path / f"pesquisa.{formato}"
    if formato in ("csv", "tsv"):
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUNAS, delimiter="\t" if formato == "tsv" else ",")
            w.writeheader()
            w.writerows(linhas)
    elif formato == "csv-ponto-e-virgula":  # exportação do Excel em pt-BR
        p = tmp_path / "pesquisa_br.csv"
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUNAS, delimiter=";")
            w.writeheader()
            w.writerows(linhas)
    elif formato == "json":
        p.write_text(json.dumps({"respostas": linhas}, ensure_ascii=False))
    elif formato == "jsonl":
        p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in linhas))
    elif formato == "xlsx":
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(COLUNAS)
        for r in linhas:
            ws.append([r[c] if c != "nota" else float(r[c]) for c in COLUNAS])  # Excel guarda número como 5.0
        wb.save(p)
    elif formato == "parquet":
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.Table.from_pylist(linhas), p)
    return str(p)


def _resumo(out):
    assert out["status"] == "ok", out
    return out["registros"], out["holdout"], out["cobertura"]


@pytest.fixture
def referencia(tmp_path):
    return _resumo(tools.importar_dados(_arquivo(tmp_path, "csv"), dicionario=DIC))


@pytest.mark.parametrize("formato", ["tsv", "csv-ponto-e-virgula", "json", "jsonl", "xlsx", "parquet"])
def test_arquivos_dao_o_mesmo_resultado(tmp_path, referencia, formato):
    assert _resumo(tools.importar_dados(_arquivo(tmp_path, formato), dicionario=DIC)) == referencia


def test_csv_ponto_e_virgula_nao_confunde_com_multipla_escolha(tmp_path):
    p = tmp_path / "br.csv"
    p.write_text('respondente;canais\nr1;"Meta;Google"\nr2;Meta\n', encoding="utf-8")
    cols, rows = fontes.ler(str(p))
    assert cols == ["respondente", "canais"] and rows[0]["canais"] == "Meta;Google"


def test_sqlite_por_arquivo_e_por_url(tmp_path, referencia, monkeypatch):
    db = _sqlite(tmp_path)
    q = "select * from respostas"
    assert _resumo(tools.importar_dados(str(db), dicionario=DIC, consulta=q)) == referencia
    assert _resumo(tools.importar_dados(f"sqlite+pysqlite:///{db}", dicionario=DIC, consulta=q)) == referencia
    monkeypatch.setenv("SUC_DADOS_URL", f"sqlite:///{db}")
    assert _resumo(tools.importar_dados("env:SUC_DADOS_URL", dicionario=DIC, consulta=q)) == referencia


@pytest.mark.parametrize("consulta", [
    None,
    "delete from respostas",
    "select * from respostas; drop table respostas",
    "with x as (select 1) insert into respostas select * from respostas",
    "pragma table_info(respostas)",
])
def test_banco_so_leitura(tmp_path, consulta):
    db = _sqlite(tmp_path)
    out = tools.importar_dados(str(db), dicionario=DIC, consulta=consulta)
    assert out["status"] == "fonte_invalida"
    assert sqlite3.connect(db).execute("select count(*) from respostas").fetchone()[0] == 200


def test_sqlite_aberto_so_para_leitura(tmp_path, monkeypatch):
    """Segunda trava: mesmo se a checagem do texto falhar, o SQLite abre em modo só leitura."""
    db = _sqlite(tmp_path)
    monkeypatch.setattr(fontes, "_checar_consulta", lambda q: q)
    with pytest.raises(fontes.ErroFonte, match="readonly"):
        fontes.ler(str(db), "delete from respostas")
    assert sqlite3.connect(db).execute("select count(*) from respostas").fetchone()[0] == 200


def test_senha_nunca_como_argumento_nem_em_erro(tmp_path, monkeypatch):
    out = tools.importar_dados(f"postgresql://user:{SENHA}@127.0.0.1:1/db", dicionario=DIC, consulta="select 1")
    assert out["status"] == "fonte_invalida" and "env:SUC_DADOS_URL" in out["erros"][0]
    assert SENHA not in json.dumps(out)
    monkeypatch.setenv("SUC_DADOS_URL", f"postgresql://user:{SENHA}@127.0.0.1:1/db")
    out = tools.importar_dados("env:SUC_DADOS_URL", dicionario=DIC, consulta="select 1")
    assert out["status"] == "fonte_invalida" and SENHA not in json.dumps(out)


def test_variavel_ausente(monkeypatch):
    monkeypatch.delenv("SUC_DADOS_URL", raising=False)
    out = tools.importar_dados("env:SUC_DADOS_URL", consulta="select 1")
    assert out["status"] == "fonte_invalida" and "SUC_DADOS_URL" in out["erros"][0]


@pytest.mark.parametrize("conteudo, trecho", [
    ('[{"a": {"b": 1}}]', "aninhados"),
    ('{"x": 1}', "lista de objetos"),
    ("[1, 2]", "lista de objetos"),
    ("{", "JSON inválido"),
])
def test_json_invalido(tmp_path, conteudo, trecho):
    p = tmp_path / "x.json"
    p.write_text(conteudo)
    out = tools.importar_dados(str(p))
    assert out["status"] == "fonte_invalida" and trecho in out["erros"][0]


def test_formato_desconhecido_e_arquivo_ausente(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_text("x")
    assert "formato não suportado" in tools.importar_dados(str(p))["erros"][0]
    assert "não encontrado" in tools.importar_dados(str(tmp_path / "nao.csv"))["erros"][0]


def test_aba_do_excel(tmp_path):
    import openpyxl

    p = tmp_path / "x.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "capa"
    ws = wb.create_sheet("dados")
    ws.append(COLUNAS)
    for r in _linhas():
        ws.append([r[c] for c in COLUNAS])
    wb.save(p)
    assert tools.importar_dados(str(p), dicionario=DIC, aba="dados")["status"] == "ok"
    assert "não existe" in tools.importar_dados(str(p), dicionario=DIC, aba="nada")["erros"][0]
