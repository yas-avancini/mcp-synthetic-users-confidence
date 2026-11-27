"""Página local, de uso único, para a pessoa colar a chave do RAG sem que ela passe pelo LLM.

Usada pela elicitation por URL do MCP: o servidor abre esta página em 127.0.0.1, numa porta
aleatória e com um token de uso único no caminho, e guarda a chave no cofre do sistema
(ou na memória da sessão, sem keyring). A página fecha depois do primeiro envio.
"""

from __future__ import annotations

import html
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

_ATIVAS: dict[str, "Pagina"] = {}
_FORM = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Chave do RAG · synthetic-users-confidence</title>
<style>body{{font:16px system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem}}
input{{width:100%;padding:.5rem;font:inherit}}button{{margin-top:1rem;padding:.5rem 1rem;font:inherit}}</style>
</head><body><h1>Chave do RAG</h1>
<p>Cole a chave de acesso de <b>{nome}</b>. Ela fica no cofre do seu sistema (ou só nesta sessão)
e não passa pelo LLM.</p>
<form method="post"><input type="password" name="chave" autocomplete="off" required autofocus>
<button type="submit">Salvar</button></form></body></html>"""
_OK = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Pronto</title></head>
<body style="font:16px system-ui;max-width:32rem;margin:4rem auto">
<h1>Pronto</h1><p>Chave guardada ({onde}). Volte para a IDE e rode <code>conectar_base</code> de novo.</p>
</body></html>"""


class Pagina:
    def __init__(self, nome: str, ao_receber: Callable[[str], str]):
        self.token = secrets.token_urlsafe(24)
        self.id = secrets.token_hex(8)
        self.recebida = threading.Event()
        pagina = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # nunca registra nada
                pass

            def _valida(self) -> bool:
                host_ok = self.headers.get("Host", "") == f"127.0.0.1:{pagina.porta}"  # contra DNS rebinding
                if not host_ok or self.path != f"/{pagina.token}" or pagina.recebida.is_set():
                    self.send_error(404)
                    return False
                return True

            def _responde(self, corpo: str) -> None:
                dados = corpo.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_GET(self):
                if self._valida():
                    self._responde(_FORM.format(nome=html.escape(nome)))

            def do_POST(self):
                if not self._valida():
                    return
                n = min(int(self.headers.get("Content-Length", 0) or 0), 16_384)
                campos = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
                chave = (campos.get("chave") or [""])[0].strip()
                if not chave:
                    self.send_error(400)
                    return
                onde = ao_receber(chave)
                pagina.recebida.set()
                self._responde(_OK.format(onde="no cofre do sistema" if onde == "cofre" else "só nesta sessão"))
                threading.Thread(target=pagina.fechar, daemon=True).start()

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.porta = self._srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.porta}/{self.token}"
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        _ATIVAS[self.id] = self

    def fechar(self) -> None:
        _ATIVAS.pop(self.id, None)
        self._srv.shutdown()
        self._srv.server_close()


def abrir(nome: str, ao_receber: Callable[[str], str]) -> Pagina:
    """Fecha páginas anteriores ainda abertas e abre uma nova."""
    for p in list(_ATIVAS.values()):
        p.fechar()
    return Pagina(nome, ao_receber)
