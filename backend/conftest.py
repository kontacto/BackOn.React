"""Configuração compartilhada do pytest.

Garante que /app/backend esteja no sys.path para que `import server`,
`from services...`, `from db...` funcionem em qualquer subpasta de testes
(tests/unit, tests/e2e), sem precisar de hacks de path em cada arquivo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
