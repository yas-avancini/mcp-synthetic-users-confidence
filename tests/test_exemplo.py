"""O exemplo do README continua dando o resultado descrito."""

import importlib.util
import json
from pathlib import Path

import pytest

from synthetic_users_confidence import render, tools

EXEMPLO = Path(__file__).parent.parent / "exemplo"


def test_arquivos_batem_com_o_gerador(tmp_path):
    spec = importlib.util.spec_from_file_location("gerar", EXEMPLO / "gerar.py")
    gerar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gerar)
    gerar.main(tmp_path)
    for nome in ("respostas.csv", "dicionario.json", "sinteticas.json"):
        assert (tmp_path / nome).read_bytes() == (EXEMPLO / nome).read_bytes(), f"rode python exemplo/gerar.py ({nome})"


@pytest.fixture
def importado():
    out = tools.importar_dados(str(EXEMPLO / "respostas.csv"), dicionario=str(EXEMPLO / "dicionario.json"))
    assert out["status"] == "ok"
    return out, json.loads((EXEMPLO / "sinteticas.json").read_text(encoding="utf-8"))


def test_importacao(importado):
    out, _ = importado
    assert out["registros"] == 600 and out["perguntas_suportadas"] == ["confia_ia", "recomendaria"]
    assert out["cobertura"]["confia_ia"]["opcoes_fora"] == {"Não sei": 22}


@pytest.mark.parametrize("usuario, nivel", [("parecido", "média"), ("otimista", "baixa")])
def test_niveis_do_readme(importado, usuario, nivel):
    _, s = importado
    v = tools.validar_usuario(s["pergunta"], s["segmento"], s["usuarios"][usuario]["respostas"])
    assert v["status"] == "ok" and v["confiabilidade"]["nivel"] == nivel
    assert "Confiança na IA" in render.validar_usuario(v)
