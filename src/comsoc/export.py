"""Exportación del dataset a formatos compartibles.

Todo corre en local: el parquet ya queda en `data/processed/`. Este módulo sirve
para generar copias en otros formatos y subconjuntos ligeros, no para transportar
archivos entre máquinas.

- `parquet` conserva tipos y pesa poco: es el formato de trabajo.
- `csv` (comprimido `.csv.gz`) es para compartir con quien no use Python.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import PROCESSED_DIR, asegurar_directorios


def exportar(
    df: pd.DataFrame,
    nombre: str = "comsoc_polizas",
    formatos: tuple[str, ...] = ("parquet",),
) -> dict[str, Path]:
    """Escribe el dataset en los formatos pedidos y devuelve las rutas."""
    asegurar_directorios()
    rutas: dict[str, Path] = {}

    if "parquet" in formatos:
        ruta = PROCESSED_DIR / f"{nombre}.parquet"
        df.to_parquet(ruta, index=False, compression="snappy")
        rutas["parquet"] = ruta

    if "csv" in formatos:
        ruta = PROCESSED_DIR / f"{nombre}.csv.gz"
        df.to_csv(ruta, index=False, compression="gzip", encoding="utf-8")
        rutas["csv"] = ruta

    for formato, ruta in rutas.items():
        print(f"  {formato:<8} {ruta}  ({ruta.stat().st_size / 1e6:.1f} MB)")
    return rutas


def muestra(df: pd.DataFrame, n: int = 5000, nombre: str = "comsoc_muestra") -> Path:
    """Subconjunto ligero para inspeccionar o compartir sin mover el dataset completo."""
    sub = df.sample(min(n, len(df)), random_state=1)
    ruta = PROCESSED_DIR / f"{nombre}.parquet"
    sub.to_parquet(ruta, index=False)
    print(f"  muestra de {len(sub):,} filas -> {ruta} ({ruta.stat().st_size / 1e6:.2f} MB)")
    return ruta


def por_anio(df: pd.DataFrame, carpeta: str = "por_anio") -> list[Path]:
    """Un parquet por año. Útil para revisar un ejercicio sin cargar toda la serie."""
    destino = PROCESSED_DIR / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for anio, grupo in df.groupby("anio_fuente"):
        ruta = destino / f"comsoc_{int(anio)}.parquet"
        grupo.to_parquet(ruta, index=False)
        rutas.append(ruta)
    print(f"  {len(rutas)} archivos en {destino}")
    return rutas
