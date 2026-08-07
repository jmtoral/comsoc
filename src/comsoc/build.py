"""Pipeline completo: Excel crudos -> dataset canónico.

    python -m comsoc.build
    python -m comsoc.build --base 2025 --sin-deflactor
"""

from __future__ import annotations

import argparse

import pandas as pd

from . import clean, deflate, entities, ids, ingest, validate
from .config import FACTURAS_PARQUET, POLIZAS_PARQUET, asegurar_directorios


def construir(base: int = 2020, deflactar: bool = True) -> pd.DataFrame:
    asegurar_directorios()

    print("\n########## 1. Ingesta")
    crudo = ingest.ingerir_todo(incluir_preliminares=True)
    print(f"\n  total crudo: {len(crudo):,} filas")

    print("\n########## 2. Limpieza")
    df = clean.limpiar(crudo)
    df = entities.agregar_canonicos(df)

    print("\n########## 3. Identificadores")
    df = ids.agregar_ids(df)
    for k, v in ids.verificar_ids(df).items():
        print(f"  {k:<28} {v:,}" if isinstance(v, int) else f"  {k:<28} {v}")

    print("\n########## 4. Validación")
    validate.reporte(df)

    print("\n########## 5. Separación por nivel de registro")
    facturas = df[df["nivel_registro"] == "factura"]
    polizas = df[df["nivel_registro"] == "renglon"].copy()
    print(f"  renglón (canónico): {len(polizas):,}")
    print(f"  factura (reconciliación): {len(facturas):,}")
    facturas.to_parquet(FACTURAS_PARQUET, index=False)

    if deflactar:
        print("\n########## 6. Deflactación")
        polizas = deflate.deflactar(polizas, base=base, estricto=False)

        print("\n########## 7. Contraste con fuente externa (ARTICLE 19, 2018-2024)")
        a19 = validate.contraste_a19(polizas)
        fallos = int((~a19["ok"]).sum())
        print(f"  {'OK' if fallos == 0 else f'{fallos} FALLO(S)'}")
        print(a19.to_string(index=False))

    polizas.to_parquet(POLIZAS_PARQUET, index=False)
    print(f"\n>> {POLIZAS_PARQUET}  ({len(polizas):,} filas, {len(polizas.columns)} columnas)")

    definitivo = polizas[polizas["vintage"] == "definitiva"]
    print("\n  Gasto nominal por año (MDP, sólo ediciones definitivas):")
    resumen = definitivo.groupby(["anio_fuente", "partida_grupo"])["monto_total"].sum() / 1e6
    print(resumen.round(1).to_string())

    return polizas


def main() -> None:
    p = argparse.ArgumentParser(description="Construye el dataset COMSOC de pólizas")
    p.add_argument("--base", type=int, default=2020, help="año base del deflactor")
    p.add_argument("--sin-deflactor", action="store_true", help="omite la deflactación")
    args = p.parse_args()
    construir(base=args.base, deflactar=not args.sin_deflactor)


if __name__ == "__main__":
    main()
