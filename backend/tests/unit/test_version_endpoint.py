"""Testes unitários do endpoint GET /api/version — usado pelo Atualizador
automático (updater/) pra troubleshooting remoto (confirmar o que está
rodando numa instalação de cliente). Ver PENDENCIAS.md > "Atualizador
automático de instalações de cliente".

Chama a função da rota diretamente (mesmo padrão do resto deste projeto —
sem `starlette.testclient.TestClient`, que nesta venv exige um pacote
`httpx2` que não está pinado em requirements.txt)."""
import asyncio
import json

import routes.misc as misc_module


class TestVersionEndpoint:
    def test_sem_arquivo_version_devolve_null(self, monkeypatch, tmp_path):
        monkeypatch.setattr(misc_module, "_VERSION_FILE", tmp_path / "nao-existe" / "VERSION")
        r = asyncio.run(misc_module.version())
        assert r == {"commit": None, "published_at": None}

    def test_com_arquivo_version_devolve_commit_e_data(self, monkeypatch, tmp_path):
        version_file = tmp_path / "VERSION"
        version_file.write_text(
            json.dumps({"commit": "cef4dcc", "published_at": "2026-08-26T12:00:00"}), encoding="utf-8"
        )
        monkeypatch.setattr(misc_module, "_VERSION_FILE", version_file)
        r = asyncio.run(misc_module.version())
        assert r == {"commit": "cef4dcc", "published_at": "2026-08-26T12:00:00"}

    def test_arquivo_version_corrompido_nao_derruba_endpoint(self, monkeypatch, tmp_path):
        version_file = tmp_path / "VERSION"
        version_file.write_text("isso não é json válido {{{", encoding="utf-8")
        monkeypatch.setattr(misc_module, "_VERSION_FILE", version_file)
        r = asyncio.run(misc_module.version())
        assert r == {"commit": None, "published_at": None}
