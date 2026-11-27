"""Isola cada teste: nenhuma conexão real do usuário (~/.config) nem estado entre testes."""

import pytest

from synthetic_users_confidence import base, tools


@pytest.fixture(autouse=True)
def _isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("SUC_CONEXAO", str(tmp_path / "conexao.json"))
    monkeypatch.delenv("SUC_RAG_TOKEN", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "keyring", None)  # cofre do sistema fora dos testes
    tools.STATE.clear()
    base._MEMORIA.clear()
    yield
    tools.STATE.clear()
    base._MEMORIA.clear()
