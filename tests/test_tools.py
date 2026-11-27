import csv

import pytest

from synthetic_users_confidence import tools

LABELS = ["Highly distrust", "Somewhat distrust", "Neither trust nor distrust", "Somewhat trust", "Highly trust"]


@pytest.fixture
def dataset(tmp_path):
    path = tmp_path / "r.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ResponseId", "Age", "DevType", "Employment", "AIAcc"])
        w.writeheader()
        for i in range(400):
            w.writerow({"ResponseId": i, "Age": "25-34", "DevType": "Developer", "Employment": "Employed",
                        "AIAcc": LABELS[1 + i % 3]})  # humanos entre 2 e 4
    return str(path)


def test_importar_dados_separa_holdout(dataset):
    out = tools.importar_dados(dataset, 0.25)
    assert out["registros"] == 400 and out["holdout"] == 100
    assert out["rotulo"] == "sintético"


def test_pontuar_resposta_nao_zera_sinais_ausentes():
    out = tools.pontuar_resposta("AIAcc", [4, 4, 4, 4, 4, 4, 4, 4, 4, 4])
    assert out["confianca"]["dispersao"]["leitura"] == "consistente"
    assert out["confianca"]["acerto_historico"]["status"] == "nao_calculado"
    assert "limite" in out["confianca"]["dispersao"]


def test_usuario_achatada_e_detectada(dataset):
    tools.importar_dados(dataset)
    seg = {"Age": "25-34"}
    out = tools.validar_usuario("AIAcc", seg, [3] * 30)
    assert out["status"] == "ok"
    assert out["fidelidade"]["razao_de_variancia"] < 0.7
    assert any("achatamento" in a for a in out["avisos"])


def test_usuario_fiel_fica_perto_do_piso(dataset):
    tools.importar_dados(dataset)
    out = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [2, 3, 4] * 20)
    assert out["fidelidade"]["emd"] <= out["fidelidade"]["piso_de_ruido_humano"] + 0.05


def test_segmento_pequeno_nao_calcula(dataset):
    tools.importar_dados(dataset)
    out = tools.validar_usuario("AIAcc", {"Age": "999"}, [3] * 30)
    assert out["status"] == "sem_holdout_suficiente"


def test_pergunta_invalida():
    with pytest.raises(ValueError):
        tools.amostrar("Foo", [1])


def test_margem_de_erro_e_significancia(dataset):
    tools.importar_dados(dataset)
    ok = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [2, 3, 4] * 20)
    assert ok["margem_de_erro"]["sintetico"]["nivel_de_confianca"] == "95%"
    assert ok["margem_de_erro"]["sintetico"]["proporcao_pp"] > ok["margem_de_erro"]["humano"]["proporcao_pp"]
    assert ok["significancia"]["p_value"] >= 0.05
    flat = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [5] * 60)
    assert flat["significancia"]["p_value"] < 0.05
    assert "distinguível" in flat["significancia"]["leitura"]


def test_pontuar_resposta_traz_margem():
    out = tools.pontuar_resposta("AIAcc", [2, 3, 4, 4, 5, 3, 2, 4, 3, 3])
    assert out["margem_de_erro"]["proporcao_pp"] == pytest.approx(31.0, abs=0.1)


def test_variancia_tem_intervalo_e_teste(dataset):
    tools.importar_dados(dataset)
    out = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [3] * 5 + [2, 4] * 20)
    lo, hi = out["margem_de_erro"]["sintetico"]["variancia_intervalo_95"]
    assert lo <= out["distribuicao_sintetica"]["variancia"] <= hi
    flat = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [3, 3, 3, 3, 4] * 8)
    assert flat["significancia"]["p_value_variancia"] < 0.05


def test_insight_em_linguagem_simples(dataset):
    tools.importar_dados(dataset)
    out = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [2, 3, 4] * 20)
    assert "p-value" not in out["insight"] and "Comparamos 60 respostas" in out["insight"]
    flat = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [5] * 60)
    assert "são diferentes" in flat["insight"] and "mais positiva" in flat["insight"]
    assert "insight" in tools.pontuar_resposta("AIAcc", [2, 3, 4, 4, 5, 3, 2, 4, 3, 3])


def test_resumo_markdown_tem_tabela_com_insight(dataset):
    from synthetic_users_confidence import render

    tools.importar_dados(dataset)
    md = render.validar_usuario(tools.validar_usuario("AIAcc", {"Age": "25-34"}, [2, 3, 4] * 20))
    assert "┌" in md and "│ Pergunta" in md and "Insight" in md and "Confiab." in md and "Signif." in md
    assert md.startswith("> **SINTÉTICO.**") and "## Confiabilidade:" in md and "**Não calculado:**" in md
    assert "Acerto histórico" in md and max(len(l) for l in md.splitlines() if l[:1] in "┌│├└") <= 100
    vazio = render.validar_usuario(tools.validar_usuario("AIAcc", {"Age": "999"}, [3] * 30))
    assert "Não foi possível comparar" in vazio
    assert "│ Métrica" in render.pontuar_resposta(tools.pontuar_resposta("AIAcc", [2, 3, 4] * 5))


def test_confiabilidade_oficial_no_json(dataset):
    tools.importar_dados(dataset)
    c = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [5] * 60)["confiabilidade"]
    assert c["nivel"] == "baixa" and "Não usar" in c["insight"]
    assert c["sinais"]["acerto_historico"]["status"] == "nao_calculado" and c["limite"]
    # sem os três sinais calculados, nunca passa de média
    parecido = tools.validar_usuario("AIAcc", {"Age": "25-34"}, [2, 3, 4] * 20)["confiabilidade"]
    assert parecido["nivel"] in ("média", "baixa")
