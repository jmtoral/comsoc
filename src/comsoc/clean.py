"""Limpieza y armonización del dataset canónico."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import yaml

from .config import CONFIG_DIR

ORIGEN_EXCEL = pd.Timestamp("1899-12-30")
PARTIDAS_VALIDAS = {"33605", "36101", "36201"}


@lru_cache(maxsize=1)
def _reglas_fechas() -> dict:
    with open(CONFIG_DIR / "fechas_corruptas.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def parsear_fechas(serie: pd.Series, anio_fuente: pd.Series | None = None) -> pd.Series:
    """Parser dual: serial de Excel (G1) y texto dd/mm/aaaa (G2/G3).

    G1 guarda las fechas como número serial; G2 y G3 como texto. Mezclar ambos
    formatos en la misma columna es el motivo de que esto no sea un to_datetime.

    `anio_fuente` acota las correcciones de año: una fecha de 2026 es un error de
    captura en un archivo de 2016, pero es legítima en el de 2025, cuya fecha de
    corte es junio de 2026. Sin este parámetro, la corrección arruina 1,003 filas
    del ejercicio 2025.
    """
    crudo = serie.astype(str).str.strip()

    # Rama 1: serial de Excel. 30000 ~ 1982, 60000 ~ 2064.
    como_num = pd.to_numeric(crudo, errors="coerce")
    es_serial = como_num.between(20000, 60000)
    fechas = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    fechas[es_serial] = ORIGEN_EXCEL + pd.to_timedelta(como_num[es_serial], unit="D")

    # Rama 2: texto dd/mm/aaaa
    resto = ~es_serial & crudo.notna()
    fechas[resto] = pd.to_datetime(crudo[resto], dayfirst=True, errors="coerce")

    # Rama 3: texto con el año mal capturado (~35 casos en 2012-2023)
    reglas = _reglas_fechas()
    malas = fechas.isna() & resto
    if malas.any():
        reparado = crudo[malas].copy()
        for anio_bueno, patrones in reglas["sustituciones_anio"].items():
            for patron in patrones:
                reparado = reparado.str.replace(patron, str(anio_bueno), regex=False)
        # format="mixed": tras sustituir el año quedan formatos heterogéneos en la
        # misma serie (dd/mm/aaaa e ISO). Sin esto, pandas avisa por cada mezcla.
        fechas[malas] = pd.to_datetime(
            reparado, dayfirst=True, errors="coerce", format="mixed"
        )

    # Rama 4: años imposibles por desfase sistemático de captura.
    # Sólo se corrige si el año resultante queda MÁS CERCA del año del archivo que
    # el original. Así la regla 2026->2016 arregla los typos de los archivos viejos
    # sin tocar las fechas de 2026 del archivo de 2025, que son reales.
    tol = reglas["tolerancia_anios"]
    for anio_malo, desfase in reglas["desfase_anios"].items():
        sel = fechas.dt.year == int(anio_malo)
        if not sel.any():
            continue
        if anio_fuente is not None:
            origen = anio_fuente[sel]
            mejora = (int(anio_malo) - origen).abs() > tol
            sel = sel & sel.index.isin(origen[mejora].index)
        if sel.any():
            fechas[sel] = fechas[sel] - pd.DateOffset(years=-desfase)

    return fechas


def reparar_partida(df: pd.DataFrame) -> pd.DataFrame:
    """Repara el bug de la fuente en el 2023 definitivo.

    En P_lizas_COMSOC_enero-diciembre_2023.xlsx la columna Partida perdió el
    primer dígito: 36101 -> 6101, 33605 -> 3605. Se reconstruye anteponiendo
    el '3' cuando el valor no es una partida válida pero sí lo es con el prefijo.
    """
    partida = df["partida"].astype(str).str.replace(r"\D", "", regex=True)
    reparable = ~partida.isin(PARTIDAS_VALIDAS) & ("3" + partida).isin(PARTIDAS_VALIDAS)
    n = int(reparable.sum())
    if n:
        print(f"  [reparado] {n:,} valores de 'partida' con el primer dígito perdido (bug 2023)")
        partida = partida.where(~reparable, "3" + partida)

    # Última red: si sigue inválida, inferir del grupo de partida de la hoja
    invalida = ~partida.isin(PARTIDAS_VALIDAS)
    if invalida.any():
        partida = partida.where(~(invalida & (df["partida_grupo"] == "33605")), "33605")
    df["partida"] = partida
    return df


def normalizar_llaves(df: pd.DataFrame) -> pd.DataFrame:
    """Claves de entidad a 5 dígitos y textos sin ruido de captura."""
    df["clave_entidad"] = (
        df["clave_entidad"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(5)
    )
    for col in ("institucion", "beneficiario", "campana_nombre", "producto_desc"):
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(r"\s+", " ", regex=True)
                .str.replace(r"\s+([.,])", r"\1", regex=True)  # "C.V ." -> "C.V."
                .str.strip()
                # "<NA>" y "NaT" son lo que produce astype(str) sobre un nulo de
                # pandas. Sin ellos, 176 mil filas acaban con ese texto como si
                # fuera un dato, y así se publicaba en el CSV.
                .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA,
                          "<NA>": pd.NA, "NaT": pd.NA, "nat": pd.NA})
            )
    if "rfc_beneficiario" in df.columns:
        df["rfc_beneficiario"] = (
            df["rfc_beneficiario"].astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
        ).replace({"": pd.NA, "NAN": pd.NA})
    return df


def agregar_banderas(df: pd.DataFrame) -> pd.DataFrame:
    """Banderas analíticas. Nada se borra: se marca.

    - es_reversa:     contra-asiento (monto negativo). Se SUMA con signo; ver §1.6.1.
    - es_intercambio: publicidad pagada en especie. En G1 era una columna propia;
                      en G2/G3 es un valor de `tipo_poliza`.
    - n_identicas:    tamaño del grupo de filas exactamente iguales. 9,036 filas
                      del histórico están duplicadas y NO se deduplican a ciegas.
    """
    df["es_reversa"] = df["monto"].fillna(0) < 0

    por_columna = df.get("intercambio")
    marca_col = (
        por_columna.notna() & (por_columna.astype(str).str.strip() != "")
        if por_columna is not None
        else pd.Series(False, index=df.index)
    )
    marca_tipo = df["tipo_poliza"].astype(str).str.strip().str.lower().eq("intercambio")
    df["es_intercambio"] = marca_col | marca_tipo

    llave = [
        "anio_fuente", "partida", "clave_entidad", "poliza", "consecutivo",
        "producto_clave", "beneficiario", "cantidad", "monto",
    ]
    llave = [c for c in llave if c in df.columns]
    df["n_identicas"] = df.groupby(llave, dropna=False)["monto"].transform("size")

    return df


# Texto que produce `astype(str)` sobre un nulo de pandas y que se cuela como si
# fuera un dato. Se barren todas las columnas de texto, no solo las conocidas:
# apareció en 16 columnas distintas y 176 mil filas antes de detectarse.
BASURA_NULA = ["<NA>", "NaT", "nan", "None", "NAN", "nat", ""]


def barrer_nulos_de_texto(df: pd.DataFrame) -> pd.DataFrame:
    columnas = [c for c in df.columns
                if df[c].dtype == object or str(df[c].dtype) == "string"]
    for col in columnas:
        df[col] = df[col].replace(dict.fromkeys(BASURA_NULA, pd.NA))
    return df


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Pipeline completo de limpieza sobre el crudo concatenado."""
    df = df.copy()
    df["fecha_gasto"] = parsear_fechas(df["fecha_gasto"], df["anio_fuente"])
    df["fecha_contrato"] = parsear_fechas(df["fecha_contrato"], df["anio_fuente"])
    df = reparar_partida(df)
    df = normalizar_llaves(df)
    df = agregar_banderas(df)

    df["anio"] = df["fecha_gasto"].dt.year
    df["mes_gasto"] = df["fecha_gasto"].dt.month
    df["monto_total"] = df["monto"].fillna(0) + df["iva"].fillna(0)

    tol = _reglas_fechas()["tolerancia_anios"]
    df["fecha_fuera_de_rango"] = (df["anio"] - df["anio_fuente"]).abs() > tol
    fuera = int(df["fecha_fuera_de_rango"].sum())
    if fuera:
        print(f"  [calidad] {fuera:,} filas con fecha_gasto fuera de su año fuente (marcadas, no corregidas)")

    df = barrer_nulos_de_texto(df)
    return df
