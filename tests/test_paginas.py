"""Carga las páginas en un navegador real y verifica que nada se rompa.

Existe porque un error de JavaScript no falla ruidosamente: la página se sirve con
HTTP 200, el HTML está completo, y aun así todo lo que va después del error deja de
ejecutarse. Pasó con `Cannot access 'T' before initialization`, que mató seis
secciones —barras, treemaps, ganadores, concentración, buscador y diccionario—
mientras las tres de arriba se veían bien.

Verificar el HTML con expresiones regulares NO lo detecta: el marcado estaba ahí.
Hay que ejecutar el guion.

    conda run -n base python -m pytest tests/test_paginas.py -v

Playwright vive en el env `base`, no en `pnt_analysis`. Si falta el navegador:
    python -m playwright install chromium
"""

from __future__ import annotations

from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api", reason="playwright no instalado")
from playwright.sync_api import sync_playwright  # noqa: E402

DOCS = Path(__file__).resolve().parents[1] / "docs"

# (archivo, [(selector, qué es, mínimo de elementos esperados)])
PAGINAS = {
    "index.html": [
        ("#bars rect.bar", "barras de la serie", 14),
        ("#cCiclo rect.barra-ciclo", "ciclo electoral", 12),
        ("#mLineas polyline.linea", "líneas de medios", 9),
        ("#mapInst g.cell", "treemap de instituciones", 20),
        ("#mapBen g.cell", "treemap de empresas", 20),
        ("#mapCamp g.cell", "treemap de campañas", 50),
        ("#gLista .gp-fila", "ganadores y perdedores", 50),
        ("#cLista .conc-fila", "concentración", 100),
        ("#tblBusca tbody tr", "buscador", 50),
        ("#tblDicc tbody tr", "diccionario", 40),
    ],
    "quien-paga-a-quien.html": [("#mapa g.cel", "treemap de instituciones", 20)],
    "medios.html": [("#mapa g.cel", "treemap de medios", 20)],
}


@pytest.fixture(scope="module")
def navegador():
    with sync_playwright() as p:
        try:
            nav = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"sin navegador de Playwright: {e}")
        yield nav
        nav.close()


@pytest.mark.parametrize("archivo", list(PAGINAS))
def test_pagina_sin_errores(navegador, archivo):
    ruta = DOCS / archivo
    if not ruta.exists():
        pytest.skip(f"falta {archivo}; genéralo con comsoc.reporte o comsoc.zoom")

    errores: list[str] = []
    pg = navegador.new_page(viewport={"width": 1400, "height": 1000})
    pg.on("pageerror", lambda e: errores.append(str(e)))
    pg.on("console", lambda m: errores.append(f"console.{m.type}: {m.text}")
          if m.type == "error" else None)
    pg.goto(ruta.as_uri())
    pg.wait_for_timeout(2000)

    vacias = []
    for sel, etq, minimo in PAGINAS[archivo]:
        n = pg.locator(sel).count()
        if n < minimo:
            vacias.append(f"{etq}: {n} elementos, se esperaban ≥{minimo}")
    pg.close()

    assert not errores, f"{archivo} lanzó errores:\n  " + "\n  ".join(errores)
    assert not vacias, f"{archivo} tiene secciones vacías:\n  " + "\n  ".join(vacias)
