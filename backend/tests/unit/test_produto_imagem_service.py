"""Testes unitários de produto_imagem_service — sistema NOVO e isolado do
Gestor de Documentos, pra foto de produto (upload com geração de 3
variantes WebP, listagem, download, soft-delete, marcar principal). Ver
PENDENCIAS.md > "Fotos de Produto" pro documento de arquitetura aprovado."""
import hashlib
import io

from PIL import Image

import services.produto_imagem_service as svc


def _png_bytes(w=40, h=30, color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


class FakeCursor:
    def __init__(self, one=None, many=None, rowcount=1):
        self._one = list(one or [])
        self._many = list(many or [])
        self.rowcount = rowcount
        self.queries = []

    def execute(self, q, p=None):
        self.queries.append((q, p))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []

    def close(self):
        pass


class FakeConn:
    def __init__(self, cursor):
        self._c = cursor
        self.committed = False
        self.rolled = False

    def cursor(self, as_dict=False):
        return self._c

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        pass


def _patch_conn(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(svc, "_open_conn", lambda *a, **k: conn)
    return conn


class FakeDriver:
    def __init__(self):
        self.salvos: dict[str, tuple[bytes, str]] = {}

    def salvar(self, caminho, conteudo, content_type):
        self.salvos[caminho] = (conteudo, content_type)

    def ler(self, caminho):
        return self.salvos[caminho][0]

    def excluir(self, caminho):
        self.salvos.pop(caminho, None)


def _patch_driver(monkeypatch, driver=None):
    driver = driver or FakeDriver()
    monkeypatch.setattr(svc, "resolver_driver_sync", lambda *a, **k: driver)
    return driver


# ---------------------------------------------------------------------------
# Migração idempotente da tabela
# ---------------------------------------------------------------------------

class TestEnsureTable:
    def test_cria_tabela_e_indice_filtrado(self):
        queries = []

        class Cur:
            def execute(self, q, p=None):
                queries.append(q)

        svc._ensure_produto_imagem_table(Cur())
        assert len(queries) == 2
        assert "CREATE TABLE produto_imagem" in queries[0]
        assert "IF NOT EXISTS (SELECT 1 FROM sys.tables" in queries[0]
        assert "UX_produto_imagem_principal" in queries[1]
        assert "WHERE principal = 1 AND situacao = 'A'" in queries[1]


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUploadImagem:
    def test_rejeita_sem_codigo_int(self):
        r = svc._upload_imagem_sync("srv", "bd", codigo_int="", conteudo=b"x", nome_original="a.png")
        assert r["success"] is False
        assert "Código do produto" in r["message"]

    def test_rejeita_sem_conteudo(self):
        r = svc._upload_imagem_sync("srv", "bd", codigo_int="123", conteudo=b"", nome_original="a.png")
        assert r["success"] is False
        assert "Selecione uma imagem" in r["message"]

    def test_rejeita_arquivo_maior_que_limite(self, monkeypatch):
        monkeypatch.setattr(svc, "TAMANHO_MAX_BYTES", 5)
        r = svc._upload_imagem_sync("srv", "bd", codigo_int="123", conteudo=b"123456", nome_original="a.png")
        assert r["success"] is False
        assert "10MB" in r["message"] or "limite" in r["message"]

    def test_rejeita_arquivo_que_nao_e_imagem(self):
        r = svc._upload_imagem_sync("srv", "bd", codigo_int="123", conteudo=b"nao e uma imagem de verdade", nome_original="a.png")
        assert r["success"] is False
        assert "não é uma imagem válida" in r["message"]

    def test_erro_de_configuracao_de_storage_vira_mensagem_amigavel(self, monkeypatch):
        def _raise(*a, **k):
            raise ValueError("Armazenamento de fotos de produto não configurado — ...")
        monkeypatch.setattr(svc, "resolver_driver_sync", _raise)
        r = svc._upload_imagem_sync("srv", "bd", codigo_int="123", conteudo=_png_bytes(), nome_original="a.png")
        assert r["success"] is False
        assert "não configurado" in r["message"]

    def test_upload_valido_gera_3_variantes_e_grava_registro(self, monkeypatch):
        driver = _patch_driver(monkeypatch)
        cur = FakeCursor(one=[{"prox": 0}, {"codigo": 42}])
        _patch_conn(monkeypatch, cur)

        conteudo = _png_bytes()
        r = svc._upload_imagem_sync(
            "srv", "bd", codigo_int="123", conteudo=conteudo, nome_original="foto.png",
            cor=5, principal=False, usuario_inclusao=7,
        )

        assert r["success"] is True
        assert r["codigo"] == 42

        # original + 3 variantes (thumb/medium/web) foram gravados no driver
        caminhos = list(driver.salvos.keys())
        assert any(c.endswith("/original.png") for c in caminhos)
        for variante in ("thumb", "medium", "web"):
            assert any(c.endswith(f"/{variante}.webp") for c in caminhos)
        assert len(caminhos) == 4

        # variantes foram de fato reduzidas de tamanho (WebP comprimido)
        thumb_bytes = next(v for k, v in driver.salvos.items() if k.endswith("/thumb.webp"))[0]
        thumb_img = Image.open(io.BytesIO(thumb_bytes))
        assert max(thumb_img.size) <= 150

        insert_query, insert_params = cur.queries[-2]  # último é @@IDENTITY
        assert "INSERT INTO produto_imagem" in insert_query
        hash_esperado = hashlib.sha256(conteudo).hexdigest()
        assert hash_esperado in insert_params

    def test_upload_com_principal_zera_o_anterior_antes_de_inserir(self, monkeypatch):
        _patch_driver(monkeypatch)
        cur = FakeCursor(one=[{"prox": 1}, {"codigo": 43}])
        _patch_conn(monkeypatch, cur)

        r = svc._upload_imagem_sync(
            "srv", "bd", codigo_int="123", conteudo=_png_bytes(), nome_original="foto.png", principal=True,
        )
        assert r["success"] is True
        # 1ª query deve ser o UPDATE que zera o principal anterior
        primeira_query = cur.queries[0][0]
        assert "UPDATE produto_imagem SET principal=0" in primeira_query

    def test_falha_ao_gravar_no_driver_nao_grava_registro(self, monkeypatch):
        class DriverQueFalha(FakeDriver):
            def salvar(self, caminho, conteudo, content_type):
                raise RuntimeError("disco cheio")
        driver = DriverQueFalha()
        _patch_driver(monkeypatch, driver)
        cur = FakeCursor()
        conn = _patch_conn(monkeypatch, cur)

        r = svc._upload_imagem_sync("srv", "bd", codigo_int="123", conteudo=_png_bytes(), nome_original="foto.png")
        assert r["success"] is False
        assert "Falha ao gravar a imagem" in r["message"]
        assert not cur.queries  # nunca chegou a tentar INSERT


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------

class TestListImagens:
    def test_lista_so_ativas_formatadas(self, monkeypatch):
        cur = FakeCursor(many=[[
            {
                "codigo": 1, "storage_key": "uuid-1", "nome_original": "a.png", "content_type": "image/png",
                "largura": 100, "altura": 80, "tamanho_bytes": 1234, "cor": None, "principal": True, "ordem": 0,
                "data_inclusao": None,
            },
        ]])
        _patch_conn(monkeypatch, cur)
        r = svc._list_imagens_sync("srv", "bd", "123")
        assert r["success"] is True
        assert len(r["items"]) == 1
        assert r["items"][0]["principal"] is True
        query = cur.queries[0][0]
        assert "situacao='A'" in query
        assert "ORDER BY principal DESC, ordem ASC" in query


# ---------------------------------------------------------------------------
# Download (variantes)
# ---------------------------------------------------------------------------

class TestArquivo:
    def test_variante_invalida_rejeitada(self, monkeypatch):
        r = svc._arquivo_sync("srv", "bd", 1, "gigante")
        assert r["success"] is False
        assert "inválida" in r["message"]

    def test_foto_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch_conn(monkeypatch, cur)
        r = svc._arquivo_sync("srv", "bd", 999, "thumb")
        assert r["success"] is False
        assert "não encontrada" in r["message"]

    def test_le_variante_thumb_do_driver(self, monkeypatch):
        cur = FakeCursor(one=[{
            "codigo_int": "123", "storage_key": "uuid-1", "content_type": "image/png", "nome_original": "foto.png",
        }])
        _patch_conn(monkeypatch, cur)
        driver = FakeDriver()
        driver.salvos["srv/bd/123/uuid-1/thumb.webp"] = (b"bytes-thumb", "image/webp")
        _patch_driver(monkeypatch, driver)

        r = svc._arquivo_sync("srv", "bd", 1, "thumb")
        assert r["success"] is True
        assert r["conteudo"] == b"bytes-thumb"
        assert r["content_type"] == "image/webp"

    def test_le_original_pelo_content_type_gravado(self, monkeypatch):
        cur = FakeCursor(one=[{
            "codigo_int": "123", "storage_key": "uuid-1", "content_type": "image/png", "nome_original": "foto.png",
        }])
        _patch_conn(monkeypatch, cur)
        driver = FakeDriver()
        driver.salvos["srv/bd/123/uuid-1/original.png"] = (b"bytes-original", "image/png")
        _patch_driver(monkeypatch, driver)

        r = svc._arquivo_sync("srv", "bd", 1, "original")
        assert r["success"] is True
        assert r["conteudo"] == b"bytes-original"
        assert r["content_type"] == "image/png"


# ---------------------------------------------------------------------------
# Exclusão (soft-delete) e marcar principal
# ---------------------------------------------------------------------------

class TestExcluirImagem:
    def test_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch_conn(monkeypatch, cur)
        r = svc._excluir_imagem_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_soft_delete_nunca_remove_fisicamente(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo": 1}])
        conn = _patch_conn(monkeypatch, cur)
        r = svc._excluir_imagem_sync("srv", "bd", 1)
        assert r["success"] is True
        assert conn.committed is True
        update_query = cur.queries[-1][0]
        assert "SET situacao='C', principal=0" in update_query


class TestMarcarPrincipal:
    def test_foto_nao_encontrada(self, monkeypatch):
        cur = FakeCursor(one=[None])
        _patch_conn(monkeypatch, cur)
        r = svc._marcar_principal_sync("srv", "bd", 999)
        assert r["success"] is False

    def test_troca_principal_com_2_updates(self, monkeypatch):
        cur = FakeCursor(one=[{"codigo_int": "123"}])
        conn = _patch_conn(monkeypatch, cur)
        r = svc._marcar_principal_sync("srv", "bd", 5)
        assert r["success"] is True
        assert conn.committed is True
        updates = [q for q, _ in cur.queries if q.startswith("UPDATE")]
        assert len(updates) == 2
        assert "SET principal=0 WHERE codigo_int=%s" in updates[0]
        assert "SET principal=1 WHERE codigo=%s" in updates[1]
