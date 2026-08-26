"""Testes unitários de imagem_storage — driver de armazenamento plugável
(disco local / Blob Storage compatível) usado por produto_imagem_service.
Ver PENDENCIAS.md > "Fotos de Produto" pro documento de arquitetura."""
import pytest

import services.imagem_storage as mod


# ---------------------------------------------------------------------------
# Detecção de URL de Blob (mesma regex do Gestor de Documentos)
# ---------------------------------------------------------------------------

class TestIsBlobTarget:
    def test_url_azure_blob_eh_detectada(self):
        assert mod._is_blob_target("https://minhaconta.blob.core.windows.net/produtos-imagens")

    def test_path_local_nao_eh_blob(self):
        assert not mod._is_blob_target(r"C:\fotos_produtos")
        assert not mod._is_blob_target("")
        assert not mod._is_blob_target(None)


class TestParseBlobUrl:
    def test_extrai_container_e_prefixo(self):
        container, prefixo = mod._parse_blob_url("https://conta.blob.core.windows.net/produtos-imagens/algum/prefixo")
        assert container == "produtos-imagens"
        assert prefixo == "algum/prefixo"

    def test_url_so_container_prefixo_vazio(self):
        container, prefixo = mod._parse_blob_url("https://conta.blob.core.windows.net/produtos-imagens")
        assert container == "produtos-imagens"
        assert prefixo == ""


# ---------------------------------------------------------------------------
# LocalDiskDriver
# ---------------------------------------------------------------------------

class TestLocalDiskDriver:
    def test_salvar_ler_excluir(self, tmp_path):
        driver = mod.LocalDiskDriver(str(tmp_path))
        driver.salvar("empresa/123/abc/original.jpg", b"conteudo-fake", "image/jpeg")
        assert (tmp_path / "empresa" / "123" / "abc" / "original.jpg").is_file()
        assert driver.ler("empresa/123/abc/original.jpg") == b"conteudo-fake"
        driver.excluir("empresa/123/abc/original.jpg")
        assert not (tmp_path / "empresa" / "123" / "abc" / "original.jpg").is_file()

    def test_excluir_arquivo_inexistente_nao_levanta(self, tmp_path):
        driver = mod.LocalDiskDriver(str(tmp_path))
        driver.excluir("nao/existe.jpg")  # não deve levantar


# ---------------------------------------------------------------------------
# BlobStorageDriver — SDK do Azure mockado
# ---------------------------------------------------------------------------

class FakeBlobClient:
    def __init__(self, store: dict, key: str):
        self._store = store
        self._key = key

    def upload_blob(self, conteudo, overwrite=True):
        self._store[self._key] = conteudo

    def download_blob(self):
        store = self._store

        class _Downloaded:
            def readall(self_inner):
                return store[self._key]

        return _Downloaded()

    def delete_blob(self):
        self._store.pop(self._key, None)


class FakeBlobService:
    _store: dict = {}

    def __init__(self, *a, **k):
        pass

    def get_blob_client(self, container, blob):
        return FakeBlobClient(self._store, f"{container}/{blob}")

    @classmethod
    def from_connection_string(cls, conn_str):
        return cls()


class TestBlobStorageDriver:
    def test_salvar_ler_excluir(self, monkeypatch):
        FakeBlobService._store = {}
        monkeypatch.setattr(mod, "BlobServiceClient", FakeBlobService)
        driver = mod.BlobStorageDriver("fake-conn-str", "produtos-imagens", "prefixo")
        driver.salvar("123/abc/original.jpg", b"bytes-da-foto", "image/jpeg")
        assert driver.ler("123/abc/original.jpg") == b"bytes-da-foto"
        driver.excluir("123/abc/original.jpg")
        assert FakeBlobService._store == {}

    def test_excluir_erro_azure_nao_levanta(self, monkeypatch):
        class ServiceQueBlefa:
            def __init__(self, *a, **k):
                pass

            def get_blob_client(self, container, blob):
                raise mod.AzureError("falhou")

            @classmethod
            def from_connection_string(cls, conn_str):
                return cls()

        monkeypatch.setattr(mod, "BlobServiceClient", ServiceQueBlefa)
        driver = mod.BlobStorageDriver("fake-conn-str", "produtos-imagens")
        driver.excluir("qualquer.jpg")  # não deve levantar


# ---------------------------------------------------------------------------
# resolver_driver_sync — decide LocalDiskDriver vs BlobStorageDriver a
# partir de controle_aux.path_produto_imagem
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, q, p=None):
        pass

    def fetchone(self):
        return self._row

    def close(self):
        pass


class FakeConn:
    def __init__(self, row):
        self._row = row

    def cursor(self, as_dict=False):
        return FakeCursor(self._row)

    def close(self):
        pass


class TestResolverDriverSync:
    def test_sem_configuracao_levanta_value_error(self, monkeypatch):
        monkeypatch.setattr(mod, "_open_conn", lambda *a, **k: FakeConn({}))
        with pytest.raises(ValueError, match="não configurado"):
            mod.resolver_driver_sync("srv", "bd")

    def test_path_local_devolve_local_disk_driver(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_open_conn",
            lambda *a, **k: FakeConn({"path_produto_imagem": r"C:\fotos_produtos", "Azure_ConnectionString": None}),
        )
        driver = mod.resolver_driver_sync("srv", "bd")
        assert isinstance(driver, mod.LocalDiskDriver)

    def test_blob_sem_connection_string_levanta_value_error(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_open_conn",
            lambda *a, **k: FakeConn({
                "path_produto_imagem": "https://conta.blob.core.windows.net/produtos-imagens", "Azure_ConnectionString": None,
            }),
        )
        with pytest.raises(ValueError, match="Azure_ConnectionString"):
            mod.resolver_driver_sync("srv", "bd")

    def test_blob_com_connection_string_devolve_blob_storage_driver(self, monkeypatch):
        monkeypatch.setattr(
            mod, "_open_conn",
            lambda *a, **k: FakeConn({
                "path_produto_imagem": "https://conta.blob.core.windows.net/produtos-imagens",
                "Azure_ConnectionString": "conn-str-fake",
            }),
        )
        driver = mod.resolver_driver_sync("srv", "bd")
        assert isinstance(driver, mod.BlobStorageDriver)


# ---------------------------------------------------------------------------
# Migração idempotente da coluna nova
# ---------------------------------------------------------------------------

class TestEnsurePathProdutoImagemCol:
    def test_ddl_idempotente(self):
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        mod._ensure_path_produto_imagem_col(Cur())
        assert len(queries) == 1
        assert "path_produto_imagem" in queries[0]
        assert "IF NOT EXISTS" in queries[0]
        assert "controle_aux" in queries[0]
