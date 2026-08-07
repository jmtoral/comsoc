"""Identificadores estables de póliza y de renglón.

Diseño verificado contra los datos (ver legacy/diagnostico/llave_poliza.R):

  - 6,762 números de póliza los usa más de una entidad el mismo año
    -> `clave_entidad` es indispensable.
  - 1,328 números de póliza aparecen en los dos grupos de partida
    -> `partida_grupo` es indispensable.
  - 10 pólizas abarcan dos partidas (36101 y 36201) dentro del mismo grupo
    -> la llave usa `partida_grupo`, NUNCA `partida`, o partiría una póliza en dos.
  - La columna `Núm.` de 2025 es única, pero es un índice de reporte: cambia con
    cada republicación. No sirve como identificador.

`poliza_id` NO incluye `vintage` a propósito: así la misma póliza en la edición
preliminar y en la definitiva de 2023 recibe el mismo id, que es lo que permite
diferenciarlas (Fase 6.6 del plan). `renglon_id` sí lo incluye.

Los ids son un hash del contenido, no un contador: son estables entre corridas y
entre máquinas, y no dependen del orden de lectura de los archivos.
"""

from __future__ import annotations

import hashlib

import pandas as pd

# Llave de la póliza (el documento contable).
LLAVE_POLIZA = ["anio_fuente", "partida_grupo", "clave_entidad", "poliza"]

# Llave del renglón. `ocurrencia` desempata las 9,036 filas del histórico que son
# idénticas en todos los campos; sin ella colisionarían entre sí.
LLAVE_RENGLON = [
    "poliza_id",
    "vintage",
    "nivel_registro",
    "consecutivo",
    "producto_clave",
    "unidad",
    "beneficiario",
    "cantidad",
    "costo_unitario",
    "monto",
    "iva",
    "ocurrencia",
]

LONGITUD_HASH = 16  # hex chars; 64 bits


def _texto_normalizado(serie: pd.Series) -> pd.Series:
    """Representación canónica y estable de una columna para hashear.

    Los flotantes se fijan a 2 decimales: sin esto, el ruido de coma flotante
    (140979.20000000001 en el crudo de 2022) produciría ids distintos para el
    mismo renglón en corridas distintas.
    """
    if pd.api.types.is_float_dtype(serie):
        return serie.map(lambda v: "" if pd.isna(v) else f"{v:.2f}")
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie.dt.strftime("%Y-%m-%d").fillna("")
    return (
        serie.astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )


def _hash_columnas(df: pd.DataFrame, columnas: list[str], longitud: int = LONGITUD_HASH) -> pd.Series:
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise KeyError(f"faltan columnas para el hash: {faltan}")
    partes = [_texto_normalizado(df[c]) for c in columnas]
    concatenado = partes[0]
    for p in partes[1:]:
        concatenado = concatenado + "\x1f" + p  # separador que no aparece en los datos
    return pd.Series(
        [hashlib.blake2b(s.encode("utf-8"), digest_size=longitud // 2).hexdigest() for s in concatenado],
        index=df.index,
        dtype="string",
    )


def agregar_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega `poliza_id`, `renglon_id` y las columnas de apoyo.

    Columnas resultantes:
      poliza_id       hash de (anio_fuente, partida_grupo, clave_entidad, poliza)
      ocurrencia      0,1,2... dentro de un grupo de renglones idénticos
      renglon_id      hash del contenido del renglón; único en todo el dataset
      n_renglones     cuántos renglones tiene la póliza a la que pertenece la fila
    """
    df = df.copy()

    df["poliza_id"] = _hash_columnas(df, LLAVE_POLIZA)

    # Desempate de filas idénticas. Estable porque se ordena por contenido, no por
    # el orden de lectura del Excel.
    columnas_contenido = [c for c in LLAVE_RENGLON if c not in ("poliza_id", "ocurrencia")]
    df["ocurrencia"] = df.groupby(
        ["poliza_id"] + columnas_contenido, dropna=False
    ).cumcount()

    df["renglon_id"] = _hash_columnas(df, LLAVE_RENGLON)

    renglones = df[df["nivel_registro"] == "renglon"]
    conteo = renglones.groupby("poliza_id")["renglon_id"].size().rename("n_renglones")
    df = df.merge(conteo, on="poliza_id", how="left")
    df["n_renglones"] = df["n_renglones"].fillna(0).astype("int32")

    return df


def verificar_ids(df: pd.DataFrame) -> dict:
    """Diagnóstico de los identificadores. `renglon_id` debe ser único."""
    n = len(df)
    unicos = df["renglon_id"].nunique()
    colisiones = n - unicos
    resumen = {
        "filas": n,
        "renglon_id_unicos": unicos,
        "colisiones": colisiones,
        "polizas": df["poliza_id"].nunique(),
        "renglones_por_poliza_media": round(
            df[df["nivel_registro"] == "renglon"].groupby("poliza_id").size().mean(), 2
        ),
    }
    if colisiones:
        print(
            f"  [ALERTA] {colisiones:,} colisiones en renglon_id. "
            f"Revisa que `ocurrencia` se esté calculando sobre todas las columnas de contenido."
        )
    return resumen


def comparar_vintages(df: pd.DataFrame) -> pd.DataFrame:
    """Diferencia entre la edición preliminar y la definitiva de un mismo año.

    Funciona porque `poliza_id` es estable entre vintages. Es la base de la
    pregunta 6 de la Fase 6: qué instituciones aparecen sólo en la definitiva.
    """
    anios = df.groupby("anio_fuente")["vintage"].nunique()
    anios = anios[anios > 1].index.tolist()
    if not anios:
        return pd.DataFrame()

    sub = df[df["anio_fuente"].isin(anios) & (df["nivel_registro"] == "renglon")]
    pivote = sub.pivot_table(
        index=["anio_fuente", "clave_entidad", "institucion"],
        columns="vintage",
        values="monto_total",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()

    if {"preliminar", "definitiva"}.issubset(pivote.columns):
        pivote["diferencia"] = pivote["definitiva"] - pivote["preliminar"]
        pivote["solo_en_definitiva"] = pivote["preliminar"] == 0
        pivote = pivote.sort_values("diferencia", ascending=False)
    return pivote
