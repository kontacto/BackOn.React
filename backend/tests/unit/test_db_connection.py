"""Testes unitários de db/connection.py — foco na tradução de mensagens de
erro de conexão pra linguagem não-técnica (`friendly_db_error`), aplicada
em `_open_conn` (o único ponto de abertura de conexão usado por todo o
resto do backend). Regra [GLOBAL] "mensagens do sistema devem usar
linguagem menos técnica pro usuário final", pedido explícito do usuário,
2026-07-18."""
import pytest

import db.connection as dbc


class TestFriendlyDbError:
    def test_login_failed(self):
        assert "senha" in dbc.friendly_db_error(Exception("Login failed for user 'sa'")).lower()

    def test_cannot_open_database(self):
        assert "banco de dados" in dbc.friendly_db_error(Exception("Cannot open database \"X\"")).lower()

    def test_timeout(self):
        msg = dbc.friendly_db_error(Exception("DB-Lib error: Connection timed out")).lower()
        assert "tempo" in msg or "timeout" in msg

    def test_host_nao_encontrado(self):
        msg = dbc.friendly_db_error(Exception("getaddrinfo failed")).lower()
        assert "servidor" in msg

    def test_adaptive_server_connection_failed(self):
        raw = "(20002, b'DB-Lib error message 20002, severity 9:\\nAdaptive Server connection failed (HOST)\\n')"
        msg = dbc.friendly_db_error(Exception(raw))
        assert "DB-Lib" not in msg
        assert "20002" not in msg

    def test_erro_desconhecido_cai_no_fallback_generico(self):
        msg = dbc.friendly_db_error(Exception("algo totalmente inesperado"))
        assert "Não foi possível conectar" in msg


class TestOpenConnTraduzErro:
    """`_open_conn` é o único ponto de conexão usado pelos ~70 services do
    backend — traduzir a mensagem aqui cobre o sistema inteiro sem precisar
    tocar em cada `except Exception as e: message=f"Falha conexão: {e}"`
    espalhado pelos services."""

    def test_falha_de_conexao_vira_mensagem_amigavel(self, monkeypatch):
        raw = "(20002, b'DB-Lib error message 20002, severity 9:\\nAdaptive Server connection failed (HOST)\\n')"

        def fake_connect(**kwargs):
            raise Exception(raw)

        monkeypatch.setattr(dbc.pymssql, "connect", fake_connect)
        with pytest.raises(ConnectionError) as exc_info:
            dbc._open_conn("algum-servidor", "algum-banco")
        msg = str(exc_info.value)
        assert "DB-Lib" not in msg
        assert "20002" not in msg
        assert msg == dbc.friendly_db_error(Exception(raw))

    def test_conexao_bem_sucedida_nao_e_afetada(self, monkeypatch):
        sentinel = object()
        monkeypatch.setattr(dbc.pymssql, "connect", lambda **kwargs: sentinel)
        assert dbc._open_conn("srv", "bd") is sentinel
