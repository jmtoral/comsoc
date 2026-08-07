"""Lectura de los Excel crudos al esquema canónico.

Un lector para las tres generaciones. Todo lo específico de cada año vive en
config/layouts.yaml y config/columnas.yaml; aquí no hay un solo `if anio == ...`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import INTERIM_DIR, asegurar_directorios
from .layouts import Hoja, detectar_header_row, hojas_de_polizas, resolver_nombre_hoja
from .schema import (
    COLUMNAS_CANONICAS,
    COLUMNAS_LINAJE,
    COLUMNAS_NUMERICAS,
    aplicar_mapeo,
)


def leer_hoja(hoja: Hoja, verificar_header: bool = True) -> pd.DataFrame:
    """Lee una hoja y la devuelve con nombres canónicos y columnas de linaje."""
    nombre = resolver_nombre_hoja(hoja.ruta, hoja)
    fila = detectar_header_row(hoja.ruta, nombre)

    if verificar_header and fila != hoja.header_row:
        print(
            f"  [aviso] {hoja.archivo} / {nombre}: encabezado detectado en la fila {fila}, "
            f"layouts.yaml dice {hoja.header_row}. Uso el detectado; actualiza el YAML."
        )

    df = pd.read_excel(
        hoja.ruta,
        sheet_name=nombre,
        skiprows=fila - 1,
        dtype=object,
        engine="openpyxl",
    )

    renombres, sin_mapear = aplicar_mapeo(list(df.columns), hoja.generacion)
    if sin_mapear:
        print(f"  [sin mapear] {hoja.archivo} / {nombre}: {sin_mapear}")

    df = df.rename(columns=renombres)
    df = df[[c for c in df.columns if c in COLUMNAS_CANONICAS]]
    df = df.loc[:, ~df.columns.duplicated()]

    df = _quitar_filas_basura(df)
    df = _a_numerico(df)
    df = _a_texto(df)
    df = _marcar_nivel_registro(df)

    df["archivo"] = hoja.archivo
    df["hoja"] = nombre
    df["generacion"] = hoja.generacion
    df["anio_fuente"] = hoja.anio
    df["partida_grupo"] = hoja.partida_grupo
    df["vintage"] = hoja.vintage

    # Las columnas ausentes se crean con dtype explícito: si se dejaran como
    # `object` todo-NA, el concat final las descartaría al inferir tipos.
    for c in [c for c in COLUMNAS_CANONICAS if c not in df.columns]:
        if c in COLUMNAS_NUMERICAS:
            df[c] = pd.Series(np.nan, index=df.index, dtype="float64")
        else:
            df[c] = pd.Series(pd.NA, index=df.index, dtype="string")

    return df[COLUMNAS_CANONICAS + COLUMNAS_LINAJE]


def _quitar_filas_basura(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina filas de relleno, subtotales, encabezados repetidos y notas al pie.

    NO usa `!is.na(cantidad)` como el pipeline en R: ese filtro descartaba
    silenciosamente las filas de factura. Aquí las filas de factura se conservan
    y se separan después por `nivel_registro`.
    """
    if "fecha_gasto" not in df.columns:
        return df

    df = df[df["fecha_gasto"].notna()].copy()

    # Encabezados repetidos a media hoja
    for col, valor in (("mes", "mes"), ("sector", "sector"), ("poliza", "poliza")):
        if col in df.columns:
            df = df[df[col].astype(str).str.strip().str.lower() != valor]

    # Notas al pie: filas larguísimas de texto legal en la primera columna
    if "sector" in df.columns:
        df = df[df["sector"].astype(str).str.len() < 60]

    return df


def _a_numerico(df: pd.DataFrame) -> pd.DataFrame:
    for col in COLUMNAS_NUMERICAS:
        if col in df.columns:
            serie = df[col].astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
            df[col] = pd.to_numeric(serie.replace({"": None, "-": None}), errors="coerce")
    return df


def _a_texto(df: pd.DataFrame) -> pd.DataFrame:
    """Todo lo no numérico pasa a dtype `string`.

    Sin esto, las columnas quedan `object` con tipos mezclados —`fecha_gasto` trae
    seriales de Excel (numéricos) en G1 y texto dd/mm/aaaa en G2/G3— y pyarrow no
    puede inferir un tipo al escribir el parquet intermedio.

    Es seguro: `clean.parsear_fechas` es un parser dual que opera sobre texto y
    reconoce ambas formas.
    """
    for col in df.columns:
        if col in COLUMNAS_NUMERICAS:
            continue
        serie = df[col]
        if pd.api.types.is_datetime64_any_dtype(serie):
            serie = serie.dt.strftime("%d/%m/%Y")
        elif serie.dtype == object:
            # Columnas `object` que traen Timestamps sueltos: openpyxl convierte
            # algunas celdas de fecha y otras no, en la misma columna.
            serie = serie.map(
                lambda v: v.strftime("%d/%m/%Y") if isinstance(v, pd.Timestamp) else v
            )
        df[col] = serie.astype("string").str.strip().replace({"": pd.NA, "nan": pd.NA})
    return df


def _marcar_nivel_registro(df: pd.DataFrame) -> pd.DataFrame:
    """Distingue filas de FACTURA y de RENGLÓN. Ver PLAN_MIGRACION.md §1.6.

    En G1 (2012-2023) cada hoja apila dos tipos de fila mutuamente excluyentes:
    las de factura traen Importe/IVA y las de renglón traen Cantidad/Costo.
    Sumar la columna sin separarlas duplica el gasto al ~200%.

    `cantidad` es un discriminador exacto: verificado, es NA en todas las filas
    de factura y en ninguna de renglón (1 sola excepción en 2021).

    En G2/G3 no existe la columna de factura, así que todo es renglón.
    """
    tiene_importe = "importe_factura" in df.columns and df["importe_factura"].notna().any()
    if not tiene_importe:
        df["nivel_registro"] = "renglon"
        return df

    df["nivel_registro"] = np.where(df["cantidad"].isna(), "factura", "renglon")

    ambos = (df["importe_factura"].notna() & df["monto"].notna()).sum()
    if ambos > 1:
        print(
            f"  [ALERTA] {ambos} filas traen Importe y Monto a la vez. "
            f"La hipótesis de niveles excluyentes no se sostiene aquí — revisar."
        )
    return df


def ingerir_todo(incluir_preliminares: bool = True, guardar: bool = True) -> pd.DataFrame:
    """Lee todas las hojas de pólizas y devuelve el crudo concatenado."""
    asegurar_directorios()
    partes = []
    for hoja in hojas_de_polizas(incluir_preliminares=incluir_preliminares):
        print(f"[{hoja.anio}] {hoja.archivo} / {hoja.nombre}")
        df = leer_hoja(hoja)
        print(
            f"    {len(df):>7,} filas  "
            f"({(df['nivel_registro'] == 'renglon').sum():,} renglón / "
            f"{(df['nivel_registro'] == 'factura').sum():,} factura)"
        )
        if guardar:
            df.to_parquet(INTERIM_DIR / f"{hoja.id}.parquet", index=False)
        partes.append(df)
    return pd.concat(partes, ignore_index=True)
