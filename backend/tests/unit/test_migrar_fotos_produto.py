"""Testes unitários do script de migração (Fase 4, ver PENDENCIAS.md >
"Fotos de Produto") — copia fotos do Gestor de Documentos (grupo Produtos)
pra `produto_imagem`. Nunca apaga nada do sistema antigo; idempotente por
hash em reexecução."""
import hashlib

import scripts.migrar_fotos_produto as mod


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, rows):
        self._c = FakeCursor(rows)

    def cursor(self, as_dict=False):
        return self._c

    def close(self):
        pass


def _patch_open_conn(monkeypatch, resultados_em_ordem):
    """`_open_conn` é chamado 2x por `migrar()` — 1ª pros documentos do
    Gestor de Documentos, 2ª pros hashes já migrados. `resultados_em_ordem`
    é uma lista com o `fetchall()` de cada chamada, na ordem."""
    estado = {"i": -1}

    def _fake(*a, **k):
        estado["i"] += 1
        return FakeConn(resultados_em_ordem[estado["i"]])

    monkeypatch.setattr(mod, "_open_conn", _fake)


class TestBaixarArquivoLocalOuBlob:
    def test_arquivo_local_existente(self, tmp_path):
        p = tmp_path / "foto.jpg"
        p.write_bytes(b"conteudo-real")
        assert mod._baixar_arquivo_local_ou_blob("srv", "bd", str(p)) == b"conteudo-real"

    def test_arquivo_local_inexistente_devolve_none(self, tmp_path):
        assert mod._baixar_arquivo_local_ou_blob("srv", "bd", str(tmp_path / "nao-existe.jpg")) is None

    def test_path_vazio_devolve_none(self):
        assert mod._baixar_arquivo_local_ou_blob("srv", "bd", "") is None

    def test_blob_sem_connection_string_devolve_none(self, monkeypatch):
        monkeypatch.setattr(mod, "_get_storage_config_sync", lambda *a, **k: (None, None))
        r = mod._baixar_arquivo_local_ou_blob("srv", "bd", "https://conta.blob.core.windows.net/container/arquivo.jpg")
        assert r is None


class TestMigrar:
    def test_dry_run_nao_chama_upload(self, monkeypatch, tmp_path):
        foto = tmp_path / "foto.jpg"
        foto.write_bytes(b"bytes-da-foto")
        _patch_open_conn(monkeypatch, [
            [{"codigo": 1, "codigo_int": "123", "path": str(foto), "path_origem": "foto.jpg", "cor": None}],
            [],  # nenhum hash já migrado
        ])
        chamado = {"n": 0}
        monkeypatch.setattr(mod, "_upload_imagem_sync", lambda *a, **k: chamado.update(n=chamado["n"] + 1))

        r = mod.migrar("srv", "bd", dry_run=True)
        assert r["migrados"] == 1
        assert chamado["n"] == 0

    def test_pula_documento_sem_codigo_int(self, monkeypatch):
        _patch_open_conn(monkeypatch, [
            [{"codigo": 1, "codigo_int": "", "path": "x.jpg", "path_origem": "x.jpg", "cor": None}],
            [],
        ])
        r = mod.migrar("srv", "bd", dry_run=False)
        assert r["pulados"] == 1
        assert r["migrados"] == 0

    def test_pula_arquivo_nao_encontrado(self, monkeypatch):
        _patch_open_conn(monkeypatch, [
            [{"codigo": 1, "codigo_int": "123", "path": "/nao/existe/foto.jpg", "path_origem": "foto.jpg", "cor": None}],
            [],
        ])
        r = mod.migrar("srv", "bd", dry_run=False)
        assert r["pulados"] == 1

    def test_pula_hash_ja_migrado_idempotente(self, monkeypatch, tmp_path):
        foto = tmp_path / "foto.jpg"
        conteudo = b"bytes-ja-migrados"
        foto.write_bytes(conteudo)
        hash_existente = hashlib.sha256(conteudo).hexdigest()
        _patch_open_conn(monkeypatch, [
            [{"codigo": 1, "codigo_int": "123", "path": str(foto), "path_origem": "foto.jpg", "cor": None}],
            [{"hash_conteudo": hash_existente}],
        ])
        chamado = {"n": 0}
        monkeypatch.setattr(mod, "_upload_imagem_sync", lambda *a, **k: chamado.update(n=chamado["n"] + 1) or {"success": True})

        r = mod.migrar("srv", "bd", dry_run=False)
        assert r["pulados"] == 1
        assert r["migrados"] == 0
        assert chamado["n"] == 0

    def test_migra_com_sucesso_chamando_upload(self, monkeypatch, tmp_path):
        foto = tmp_path / "foto.jpg"
        foto.write_bytes(b"bytes-novos")
        _patch_open_conn(monkeypatch, [
            [{"codigo": 1, "codigo_int": "123", "path": str(foto), "path_origem": "foto.jpg", "cor": 5}],
            [],
        ])
        capturado = {}

        def _fake_upload(servidor, banco, *, codigo_int, conteudo, nome_original, cor=None):
            capturado.update(codigo_int=codigo_int, conteudo=conteudo, nome_original=nome_original, cor=cor)
            return {"success": True, "codigo": 1}

        monkeypatch.setattr(mod, "_upload_imagem_sync", _fake_upload)
        r = mod.migrar("srv", "bd", dry_run=False)
        assert r["migrados"] == 1
        assert r["erros"] == 0
        assert capturado["codigo_int"] == "123"
        assert capturado["cor"] == 5

    def test_conta_erro_quando_upload_falha(self, monkeypatch, tmp_path):
        foto = tmp_path / "foto.jpg"
        foto.write_bytes(b"bytes-com-erro")
        _patch_open_conn(monkeypatch, [
            [{"codigo": 1, "codigo_int": "123", "path": str(foto), "path_origem": "foto.jpg", "cor": None}],
            [],
        ])
        monkeypatch.setattr(mod, "_upload_imagem_sync", lambda *a, **k: {"success": False, "message": "falhou"})
        r = mod.migrar("srv", "bd", dry_run=False)
        assert r["erros"] == 1
        assert r["migrados"] == 0
