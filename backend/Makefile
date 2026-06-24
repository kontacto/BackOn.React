# Back-On backend — atalhos de teste.
# Convenção (a partir de jun/2026):
#   tests/unit  → testes UNITÁRIOS puros, SEM banco (rápidos, rodar a cada commit)
#   tests/e2e   → testes ponta-a-ponta, exigem o SQL Server Azure (BASE_URL/EXPO_PUBLIC_BACKEND_URL)
.PHONY: test test-unit test-e2e

test-unit:
	python -m pytest tests/unit -q

test-e2e:
	python -m pytest tests/e2e -q

test:
	python -m pytest tests -q
