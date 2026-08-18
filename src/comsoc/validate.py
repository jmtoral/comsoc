"""Pruebas de aceptación del dataset.

Estas comprobaciones son el corazón de la migración: si pasan, no se duplicó
ni se perdió dinero al armonizar tres formatos distintos.
"""

from __future__ import annotations

import pandas as pd

from .layouts import cargar_control

# Totales nominales verificados contra los Excel crudos (millones de pesos,
# ambas hojas, suma de renglones). Sirven de red de seguridad ante refactors.
TOTALES_ESPERADOS_MDP = {
    2012: 7817.9, 2013: 6234.0, 2014: 5930.1, 2015: 8080.6,
    2016: 8980.0, 2017: 9286.0, 2018: 7957.2, 2019: 2717.5,
    2020: 1873.4, 2021: 1988.4, 2022: 2092.7, 2023: 2119.6,
}

# Contraste externo: gasto federal en publicidad oficial (partidas 36101, 36201 y
# 33605) según ARTICLE 19 + Política Colectiva, "Publicidad Oficial 2024" (oct-2025),
# en millones de pesos constantes de 2025. Ver referencias/.
#
# Es la única verificación contra una fuente INDEPENDIENTE de este pipeline. Ellos
# citan los reportes agregados de "Estrategia de comunicación social"; nosotros
# sumamos el detalle de pólizas. Que coincidan valida las dos rutas.
A19_FEDERAL_MDP_2025 = {
    2018: 12961.62, 2019: 4243.31, 2020: 2796.69, 2021: 2839.85,
    2022: 2808.60, 2023: 2713.74, 2024: 3795.45,
}

# Deflactor de 2025 implícito en las cifras de A19. Difiere del nuestro (127.759,
# FUNDAR Nota Metodológica 2025) en 0.77%: ambos son ESTIMADOS de un año no cerrado.
# Para comparar niveles hay que reescalar; las tasas de crecimiento no se ven afectadas.
A19_DEFLACTOR_2025_IMPLICITO = 128.738


def reconciliar_factura_vs_renglon(df: pd.DataFrame, tolerancia: float = 0.25) -> pd.DataFrame:
    """La prueba clave (PLAN_MIGRACION.md §1.6).

    En 2012-2023 la suma de los renglones debe igualar la suma de las facturas,
    porque son el mismo dinero a dos granularidades. Diferencias esperadas:
    0.00%-0.21%. Una diferencia grande significa que el filtro de
    `nivel_registro` se rompió y el total está duplicado o mutilado.
    """
    g1 = df[df["generacion"].isin(["G1", "G1b"])]
    llave = ["anio_fuente", "vintage", "partida_grupo"]  # 2023 tiene dos ediciones
    renglon = (
        g1[g1["nivel_registro"] == "renglon"]
        .groupby(llave)["monto"].sum()
        .rename("suma_renglon")
    )
    factura = (
        g1[g1["nivel_registro"] == "factura"]
        .groupby(llave)["importe_factura"].sum()
        .rename("suma_factura")
    )
    rec = pd.concat([renglon, factura], axis=1).reset_index()
    rec["dif_pct"] = 100 * (rec["suma_factura"] - rec["suma_renglon"]) / rec["suma_renglon"]
    rec["ok"] = rec["dif_pct"].abs() <= tolerancia
    return rec


def verificar_cifras_de_control(df: pd.DataFrame, tolerancia: float = 1.0) -> pd.DataFrame:
    """Contrasta contra los totales que los propios archivos incrustan.

    Desde 2025 las hojas de pólizas traen un panel Monto/IVA/Monto+IVA antes del
    encabezado. Se declaran en `layouts.yaml: control` y se verifican al peso: es la
    única prueba que compara contra la fuente y no contra nosotros mismos.
    """
    filas = []
    for anio, grupos in cargar_control().items():
        for grupo, esperado in grupos.items():
            sel = df[(df["anio_fuente"] == anio) & (df["partida_grupo"] == grupo)]
            filas.append(
                {
                    "anio": anio,
                    "partida_grupo": grupo,
                    "monto_calculado": sel["monto"].sum(),
                    "monto_control": esperado["monto"],
                    "iva_calculado": sel["iva"].sum(),
                    "iva_control": esperado["iva"],
                }
            )
    rec = pd.DataFrame(filas)
    rec["dif_monto"] = rec["monto_calculado"] - rec["monto_control"]
    rec["ok"] = rec["dif_monto"].abs() <= tolerancia
    return rec


def verificar_totales_historicos(df: pd.DataFrame, tolerancia_pct: float = 0.5) -> pd.DataFrame:
    """Contra los totales verificados en el diagnóstico (legacy/diagnostico/)."""
    obs = (
        df[(df["nivel_registro"] == "renglon") & (df["vintage"] == "definitiva")]
        .groupby("anio_fuente")["monto"].sum() / 1e6
    )
    rec = pd.DataFrame({"esperado_mdp": pd.Series(TOTALES_ESPERADOS_MDP)})
    rec["observado_mdp"] = obs.round(1)
    rec["dif_pct"] = 100 * (rec["observado_mdp"] - rec["esperado_mdp"]) / rec["esperado_mdp"]
    rec["ok"] = rec["dif_pct"].abs() <= tolerancia_pct
    return rec.reset_index(names="anio")


def contraste_a19(df: pd.DataFrame, tolerancia_pct: float = 0.5) -> pd.DataFrame:
    """Contrasta la serie real contra ARTICLE 19 / Política Colectiva (2018-2024).

    Requiere el dataset YA deflactado (`monto_real`). Se comparan dos cosas:

    - **Tasas de crecimiento real**: deben coincidir al decimal. No dependen del
      deflactor elegido, así que un desajuste aquí significa que los datos difieren.
    - **Niveles**: se reescalan al deflactor implícito de A19 antes de comparar,
      porque ambos usan estimados distintos para 2025.
    """
    base = df[(df["vintage"] == "definitiva") & (~df["es_intercambio"])]
    serie = base.groupby("anio_fuente")["monto_real"].sum() / 1e6

    factor = A19_DEFLACTOR_2025_IMPLICITO / 100.0
    rec = pd.DataFrame({"a19_mdp_2025": pd.Series(A19_FEDERAL_MDP_2025)})
    rec["nuestro_mdp_2025"] = (serie * factor).round(2)
    rec["dif_pct"] = (100 * (rec["nuestro_mdp_2025"] / rec["a19_mdp_2025"] - 1)).round(3)
    rec["var_nuestro"] = (serie.pct_change() * 100).round(1)
    rec["var_a19"] = (pd.Series(A19_FEDERAL_MDP_2025).pct_change() * 100).round(1)
    rec["ok"] = rec["dif_pct"].abs() <= tolerancia_pct
    return rec.dropna(subset=["a19_mdp_2025"]).reset_index(names="anio")


def reporte(df: pd.DataFrame) -> None:
    for titulo, tabla in (
        ("Factura vs renglón (G1)", reconciliar_factura_vs_renglon(df)),
        ("Totales históricos", verificar_totales_historicos(df)),
        ("Cifras de control de la fuente", verificar_cifras_de_control(df)),
    ):
        fallos = (~tabla["ok"]).sum()
        estado = "OK" if fallos == 0 else f"{fallos} FALLO(S)"
        print(f"\n===== {titulo}: {estado}")
        print(tabla.to_string(index=False))
