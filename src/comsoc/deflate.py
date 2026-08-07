"""Deflactación a pesos constantes.

Deflactor implícito del PIB, base 2020=100. Fuente: FUNDAR, Nota Metodológica 2025
https://fundar.org.mx/wp-content/uploads/2025/09/Nota_Metodologica_2025.pdf

OJO — la serie fue REVISADA en esa nota. No son los mismos valores que la versión
2023-2024 que usaba el pipeline en R (conservada en `legacy/inputs/`): INEGI
recalculó el deflactor y, por ejemplo, 2012 pasó de 71.545 a 70.335 y 2023 de
118.474 a 116.654. Por eso `config/deflactor.csv` se reemplazó completo en vez de
extenderse: mezclar ambas versiones produciría una serie real incoherente.

2025 y 2026 están marcados como estimados (`/e` en la fuente). El renglón final de
la tabla publicada dice "2006/e", pero es un typo evidente: 2006 ya aparece antes
con 51.37 y el valor 132.869 continúa la secuencia después de 2025. Se registra
como 2026.
"""

from __future__ import annotations

import pandas as pd

from .config import CONFIG_DIR


def cargar_deflactor() -> pd.DataFrame:
    return pd.read_csv(CONFIG_DIR / "deflactor.csv")


def deflactar(df: pd.DataFrame, base: int = 2020, estricto: bool = True) -> pd.DataFrame:
    """Agrega `monto_real` en pesos constantes del año `base`.

    Con `estricto=True` falla si falta el factor de algún año, en vez de producir
    NaN silenciosos en la parte más reciente de la serie.
    """
    defl = cargar_deflactor().rename(columns={"estimado": "deflactor_estimado"})
    if base not in set(defl["ciclo"]):
        raise ValueError(f"El año base {base} no está en config/deflactor.csv")
    factor_base = float(defl.loc[defl["ciclo"] == base, "deflactor_pib_2020_100"].iloc[0])

    # Se deflacta por `anio_fuente` (el ejercicio que reporta el archivo), no por
    # `anio` (derivado de fecha_gasto): éste último arrastra fechas mal capturadas
    # —2001, 2055— que producirían NaN dispersos e imposibles de rastrear.
    out = df.merge(defl, left_on="anio_fuente", right_on="ciclo", how="left").drop(columns=["ciclo"])

    faltan = sorted(
        out.loc[out["deflactor_pib_2020_100"].isna() & out["anio_fuente"].notna(), "anio_fuente"].unique()
    )
    if faltan:
        mensaje = (
            f"Faltan factores de deflactor para: {[int(a) for a in faltan]}. "
            f"Agrégalos a config/deflactor.csv (deflactor implícito del PIB, base 2020=100)."
        )
        if estricto:
            raise ValueError(mensaje)
        print(f"  [aviso] {mensaje}")

    out["monto_real"] = out["monto_total"] * (factor_base / out["deflactor_pib_2020_100"])
    out["anio_base"] = base

    estimados = sorted(
        out.loc[out["deflactor_estimado"] == 1, "anio_fuente"].dropna().unique().astype(int)
    )
    if estimados:
        print(
            f"  [nota] Deflactor ESTIMADO (no definitivo) para {estimados}. "
            f"Dilo en la nota al pie de cualquier gráfica que los incluya."
        )
    return out
