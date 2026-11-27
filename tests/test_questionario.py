"""Importação de qualquer questionário: dicionário, detecção de colunas e validação."""

import csv
import json

import pytest

from synthetic_users_confidence import render, tools

OPCOES = ["Discordo totalmente", "Discordo", "Neutro", "Concordo", "Concordo totalmente"]
ESCALA = {o: i + 1 for i, o in enumerate(OPCOES)}


def _csv(tmp_path, linhas, nome="pesquisa.csv"):
    path = tmp_path / nome
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    return str(path)


@pytest.fixture
def pesquisa(tmp_path):
    linhas = []
    for i in range(400):
        linhas.append({
            "respondente": f"r{i}",
            "nome": f"Pessoa {i}",  # dado pessoal: nunca pode aparecer na detecção
            "cargo": "Gerente" if i % 2 else "Analista",
            "canais": "Meta|Google" if i % 4 == 0 else "Meta",
            "confia_ia": "Não sei" if i % 20 == 0 else OPCOES[1 + i % 3],
            "nota": str(1 + i % 5),
            "cidade": "Itu" if i < 2 else "São Paulo",  # valor raro: some da detecção
        })
    return _csv(tmp_path, linhas)


DICIONARIO = {
    "nome": "pesquisa-teste",
    "id": "respondente",
    "estratos": ["cargo"],
    "separador_multiplo": "|",
    "perguntas": {
        "confia_ia": {"texto": "Quanto você confia na IA?", "rotulo": "Confiança na IA", "escala": ESCALA},
    },
}


def test_sem_dicionario_pede_e_sugere_sem_expor_dados(pesquisa):
    out = tools.importar_dados(pesquisa)
    assert out["status"] == "precisa_dicionario" and "ds" not in tools.STATE
    cols = {c["coluna"]: c for c in out["colunas"]}
    assert cols["nome"]["valores"] is None  # texto livre: não lido
    assert "Pessoa 1" not in json.dumps(out, ensure_ascii=False)
    assert "Itu" not in json.dumps(out, ensure_ascii=False) and cols["cidade"]["valores_ocultos"] == 1
    assert cols["canais"]["multipla_escolha"] is True and out["sugestao"]["separador_multiplo"] == "|"
    assert set(cols["canais"]["valores"]) == {"Meta", "Google"}
    assert {"confia_ia", "nota"} <= set(out["candidatas_a_pergunta"])
    sug = out["sugestao"]
    assert sug["id"] == "respondente"
    assert sug["perguntas"]["nota"]["escala"] == {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}
    assert sug["perguntas"]["confia_ia"]["escala"] is None  # ordem não é óbvia: o agente pergunta
    assert "perguntas" in out["formato"]


def test_com_dicionario_valida_usuario(pesquisa):
    out = tools.importar_dados(pesquisa, dicionario=DICIONARIO)
    assert out["status"] == "ok" and out["perguntas_suportadas"] == ["confia_ia"]
    assert out["holdout"] == 120
    assert out["cobertura"]["confia_ia"]["fora_da_escala"] == 20
    assert out["cobertura"]["confia_ia"]["opcoes_fora"] == {"Não sei": 20}
    assert any("estratificado por cargo" in a for a in out["avisos"])
    v = tools.validar_usuario("confia_ia", {"cargo": "Gerente"}, ["Neutro", "Concordo", "Discordo"] * 10)
    assert v["status"] == "ok"
    md = render.validar_usuario(v)
    assert "Confiança na IA" in md and "Quanto você confia na IA?" in md
    with pytest.raises(ValueError, match="não suportada"):
        tools.pontuar_resposta("AIAcc", [3] * 10)


def test_segmento_multipla_escolha_usa_o_separador(pesquisa):
    tools.importar_dados(pesquisa, dicionario=DICIONARIO)
    google = tools.STATE["ds"].humans("confia_ia", {"canais": "Google"}, holdout=False)
    assert 0 < len(google) < 100


def test_holdout_estratificado(pesquisa):
    tools.importar_dados(pesquisa, 0.25, dicionario=DICIONARIO)
    ds = tools.STATE["ds"]
    gerentes = [i for i in ds.holdout_idx if ds.rows[i]["cargo"] == "Gerente"]
    assert len(gerentes) == 50 and len(ds.holdout_idx) == 100


def test_dicionario_por_caminho_e_por_texto(pesquisa, tmp_path):
    p = tmp_path / "dic.json"
    p.write_text(json.dumps(DICIONARIO, ensure_ascii=False), encoding="utf-8")
    assert tools.importar_dados(pesquisa, dicionario=str(p))["status"] == "ok"
    assert tools.importar_dados(pesquisa, dicionario=json.dumps(DICIONARIO))["status"] == "ok"
    out = tools.importar_dados(pesquisa, dicionario=str(tmp_path / "nao-existe.json"))
    assert out["status"] == "dicionario_invalido"


@pytest.mark.parametrize("mudanca, trecho", [
    ({"perguntas": {"confia_ia": {"escala": {"a": 1, "b": 2, "c": 3, "d": 4}}}}, "5 pontos"),
    ({"perguntas": {"sumiu": {"escala": ESCALA}}}, "não existe"),
    ({"estratos": ["confia_ia"]}, "também está nos estratos"),
    ({"extra": 1}, "chave desconhecida"),
    ({"id": "nao_tem"}, "id"),
    ({"perguntas": {}}, "ao menos uma"),
])
def test_dicionario_invalido(pesquisa, mudanca, trecho):
    out = tools.importar_dados(pesquisa, dicionario={**DICIONARIO, **mudanca})
    assert out["status"] == "dicionario_invalido"
    assert any(trecho in e for e in out["erros"]), out["erros"]
    assert "ds" not in tools.STATE


def test_id_repetido(tmp_path):
    linhas = [{"respondente": "r1", "cargo": "A", "confia_ia": "Neutro"}] * 2
    out = tools.importar_dados(_csv(tmp_path, linhas), dicionario=DICIONARIO | {"estratos": ["cargo"]})
    assert out["status"] == "dados_invalidos"


def test_opcao_digitada_errada_gera_aviso(pesquisa):
    esc = {**{o: v for o, v in ESCALA.items() if o != "Neutro"}, "neutro": 3}
    dic = {**DICIONARIO, "perguntas": {"confia_ia": {"escala": esc}}}
    out = tools.importar_dados(pesquisa, dicionario=dic)
    assert out["status"] == "ok"
    assert any("neutro" in a for a in out["avisos"])
    assert out["cobertura"]["confia_ia"]["opcoes_fora"]["Neutro"] > 0


def test_stackoverflow_continua_sem_dicionario(tmp_path):
    linhas = [{"ResponseId": i, "Age": "25-34", "DevType": "Dev", "Employment": "E", "AIAcc": "Somewhat trust"}
              for i in range(50)]
    out = tools.importar_dados(_csv(tmp_path, linhas))
    assert out["status"] == "ok" and out["perguntas_suportadas"] == ["AIAcc"]
    assert any("Stack Overflow" in a for a in out["avisos"])


def test_servidor_aceita_dicionario_como_objeto(pesquisa):
    from test_base import _chamar, _json

    out = _json(_chamar("importar_dados", {"caminho_csv": pesquisa, "dicionario": DICIONARIO}))
    assert out["status"] == "ok" and out["perguntas_suportadas"] == ["confia_ia"]
