"""Rutas del proyecto.

En local se deducen de la ubicación de este archivo. En Colab, exporta
COMSOC_ROOT apuntando a la carpeta del proyecto en Drive:

    import os
    os.environ["COMSOC_ROOT"] = "/content/drive/MyDrive/publicidad_oficial"
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("COMSOC_ROOT", Path(__file__).resolve().parents[2]))

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = ROOT / "reports"
LEGACY_DIR = ROOT / "legacy"
DOCS_DIR = ROOT / "docs"  # sitio estático — GitHub Pages sirve desde aquí

# Salidas principales
POLIZAS_PARQUET = PROCESSED_DIR / "comsoc_polizas.parquet"
FACTURAS_PARQUET = INTERIM_DIR / "reconciliacion_facturas.parquet"
EJERCIDO_PARQUET = PROCESSED_DIR / "comsoc_ejercido.parquet"


def asegurar_directorios() -> None:
    for d in (INTERIM_DIR, PROCESSED_DIR, REPORTS_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)
