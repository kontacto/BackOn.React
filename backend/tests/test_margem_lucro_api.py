"""Testa o endpoint POST /api/relatorios/margem-lucro contra o servidor real
(sql.juansouza.com.br) e valida que o consolidado expõe o campo 'desconto'
e que cada empresa expõe 'total_desconto' (mudança incremental da iter40)."""
import os
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://order-crud-discounts.preview.emergentagent.com").rstrip("/")
TIMEOUT = 60


def _payload(banco: str = "BD_ESTELA") -> dict:
    return {
        "conexoes": [{"empresa": banco.replace("BD_", ""), "servidor": "sql.juansouza.com.br", "banco": banco}],
        "data_ini": "2025-12-01",
        "data_fim": "2026-06-30",
        "incluir_pedidos": True, "incluir_os": True, "incluir_comandas": True,
        "retorna_produtos": True, "retorna_servicos": True,
        "davs_abertos": True, "davs_fechados": True, "davs_faturados": True,
    }


def test_margem_lucro_status_200():
    r = requests.post(f"{BASE_URL}/api/relatorios/margem-lucro", json=_payload(), timeout=TIMEOUT)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"


def test_consolidado_tem_campo_desconto():
    r = requests.post(f"{BASE_URL}/api/relatorios/margem-lucro", json=_payload(), timeout=TIMEOUT)
    body = r.json()
    assert body.get("success") is True, body
    cons = body.get("consolidado") or {}
    assert "desconto" in cons, f"consolidado nao tem 'desconto': {cons}"
    assert isinstance(cons["desconto"], (int, float)), type(cons["desconto"])
    assert cons["desconto"] >= 0, cons["desconto"]
    # Sanidade dos demais campos
    for k in ("total_venda", "total_custo", "lucro", "margem_pct", "qtd_davs", "qtd_empresas"):
        assert k in cons, f"falta {k} no consolidado: {cons}"
    print(f"CONSOLIDADO: venda={cons['total_venda']} custo={cons['total_custo']} desconto={cons['desconto']} lucro={cons['lucro']}")


def test_empresa_tem_total_desconto():
    r = requests.post(f"{BASE_URL}/api/relatorios/margem-lucro", json=_payload(), timeout=TIMEOUT)
    body = r.json()
    empresas = body.get("empresas") or []
    assert len(empresas) >= 1, "Nenhuma empresa no payload"
    for emp in empresas:
        if not emp.get("success"):
            print(f"AVISO: empresa {emp.get('banco')} falhou: {emp.get('message')}")
            continue
        assert "total_desconto" in emp, f"empresa {emp.get('banco')} nao tem 'total_desconto': {list(emp.keys())}"
        assert isinstance(emp["total_desconto"], (int, float))
        assert emp["total_desconto"] >= 0
        # cada DAV deve ter total_desconto
        for d in (emp.get("davs") or [])[:3]:
            assert "total_desconto" in d, f"DAV nao tem total_desconto: {d.keys()}"


def test_multiempresa_consolida_desconto():
    payload = _payload()
    payload["conexoes"] = [
        {"empresa": "ESTELA", "servidor": "sql.juansouza.com.br", "banco": "BD_ESTELA"},
        {"empresa": "PAJE", "servidor": "sql.juansouza.com.br", "banco": "BD_PAJE"},
        {"empresa": "KONTACTO", "servidor": "sql.juansouza.com.br", "banco": "BD_KONTACTO"},
    ]
    r = requests.post(f"{BASE_URL}/api/relatorios/margem-lucro", json=payload, timeout=TIMEOUT * 2)
    assert r.status_code == 200
    body = r.json()
    cons = body["consolidado"]
    soma_emp = sum(e.get("total_desconto", 0) for e in body["empresas"] if e.get("success"))
    # consolidado.desconto deve ser ~ soma dos total_desconto das empresas (tolerancia 0.05)
    assert abs(cons["desconto"] - round(soma_emp, 2)) <= 0.05, f"cons.desc={cons['desconto']} soma={soma_emp}"
    print(f"MULTI: desconto consolidado={cons['desconto']} soma_empresas={round(soma_emp, 2)}")
