import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "run_blind_experiment", Path(__file__).parent.parent / "experiments" / "run_blind_experiment.py"
)
exp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exp)

from synthetic_users_confidence import confiabilidade  # noqa: E402


def test_nivel_baixa_por_media_distante():
    assert confiabilidade.nivel(1.2, 0.9, True, True) == "baixa"


def test_nivel_baixa_por_achatamento():
    assert confiabilidade.nivel(0.05, 0.1, True, True) == "baixa"


def test_nivel_nao_passa_de_media_sem_os_tres_sinais():
    assert confiabilidade.nivel(0.03, 0.9, True, False) == "média"


def test_nivel_alta_so_com_tudo():
    assert confiabilidade.nivel(0.03, 0.9, True, True) == "alta"
    assert confiabilidade.nivel(0.03, 0.9, False, True) == "média"


def test_holm_nao_diminui_e_limita_em_1():
    ajustados = exp.holm([0.01, 0.04, 0.5])
    assert all(a >= p for a, p in zip(ajustados, [0.01, 0.04, 0.5]))
    assert max(ajustados) <= 1.0
