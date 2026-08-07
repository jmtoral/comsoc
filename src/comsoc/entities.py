"""Homologación de nombres de beneficiarios e instituciones.

Porta las reglas que estaban escritas a mano en `legacy/R/3_analysis_and_vizes.R`
(39 de beneficiarios en las líneas 63-110, 22 de instituciones en 205-233 y
383-411) a `config/beneficiarios_map.csv` y `config/instituciones_map.csv`.

Están como DATOS y no como código a propósito: son un criterio editorial que hay
que poder auditar, citar y corregir sin tocar el pipeline.

## Dos cambios deliberados respecto del original en R

1. **El match ignora acentos.** El R comparaba con acentos y eso dejaba fuera
   variantes reales de la fuente: `COMISION NACIONAL PARA LA PROTECCION Y DEFEN-SA`
   (sin acentos, como la captura el COMSOC en varios años) no entraba en la regla
   de CONDUSEF, que exigía `COMISIÓN...PROTECCIÓN`.
2. **Se fusionaron reglas duplicadas.** El R tenía dos reglas para Radio y TV de
   Hidalgo (una con acento, otra sin) que producían DOS nombres canónicos distintos
   —"Radio y TV de Hidalgo" y "Radioy TV de Hgo."— para la misma empresa, según
   cómo viniera escrita. Lo mismo con EyPME. Ahora cada una es una sola regla.

El orden importa: gana la primera regla que coincide, igual que el `case_when` del R.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import pandas as pd

from .config import CONFIG_DIR

MAPEOS = {
    "beneficiario": "beneficiarios_map.csv",
    "institucion": "instituciones_map.csv",
}


def plegar(texto: object) -> str:
    """Quita acentos y colapsa espacios. La forma sobre la que se hace el match."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


@lru_cache(maxsize=4)
def cargar_reglas(campo: str) -> pd.DataFrame:
    if campo not in MAPEOS:
        raise KeyError(f"campo sin mapeo: {campo!r}. Disponibles: {list(MAPEOS)}")
    reglas = pd.read_csv(CONFIG_DIR / MAPEOS[campo], dtype=str).fillna("")
    reglas["orden"] = reglas["orden"].astype(int)
    return reglas.sort_values("orden").reset_index(drop=True)


def canonizar(serie: pd.Series, campo: str, minusculas: bool = True) -> pd.Series:
    """Aplica las reglas de `campo` y devuelve el nombre canónico.

    `minusculas=True` para beneficiarios (el R comparaba en minúsculas);
    `False` para instituciones (comparaba en mayúsculas).
    """
    reglas = cargar_reglas(campo)
    original = serie.astype("string").fillna("")
    plegada = original.map(plegar)
    trabajo = plegada.str.lower() if minusculas else plegada.str.upper()

    pre = reglas[(reglas.tipo == "reemplazo") & (reglas.orden < 100)]
    for _, r in pre.iterrows():
        patron = r.patron.lower() if minusculas else r.patron.upper()
        trabajo = trabajo.str.replace(patron, r.canonico, regex=True)
    trabajo = trabajo.str.strip().str.replace(r"\s+", " ", regex=True)

    # Fallback igual que el R: Title Case para beneficiarios, tal cual para instituciones
    salida = trabajo.str.title() if minusculas else trabajo
    asignado = pd.Series(False, index=serie.index)

    for _, r in reglas[reglas.tipo == "regex"].iterrows():
        patron = r.patron.lower() if minusculas else r.patron.upper()
        pega = ~asignado & trabajo.str.contains(patron, regex=True, na=False)
        salida = salida.mask(pega, r.canonico)
        asignado |= pega

    post = reglas[(reglas.tipo == "reemplazo") & (reglas.orden >= 100)]
    for _, r in post.iterrows():
        salida = salida.str.replace(r.patron, r.canonico, regex=False)

    return salida.str.strip()


def agregar_canonicos(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega `beneficiario_canonico` e `institucion_canonica`."""
    df = df.copy()
    df["beneficiario_canonico"] = canonizar(df["beneficiario"], "beneficiario", minusculas=True)
    df["institucion_canonica"] = canonizar(df["institucion"], "institucion", minusculas=False)
    return df


def reporte(df: pd.DataFrame, campo: str = "beneficiario", top: int = 12) -> pd.DataFrame:
    """Cuánto gasto queda cubierto por una regla explícita y cuál cubre qué.

    Lo no cubierto cae al fallback (Title Case), que NO agrupa razones sociales
    distintas de un mismo grupo: es la medida de cuánto falta por homologar.
    """
    reglas = set(cargar_reglas(campo).query("tipo == 'regex'").canonico)
    col = f"{campo}_canonico" if campo == "beneficiario" else "institucion_canonica"
    base = df[df.vintage == "definitiva"]
    con_regla = base[col].isin(reglas)

    total = base.monto_real.sum()
    print(f"--- {campo}: {len(reglas)} reglas explícitas")
    print(f"    gasto cubierto por regla : {100 * base.loc[con_regla, 'monto_real'].sum() / total:.1f}%")
    print(f"    renglones cubiertos      : {100 * con_regla.mean():.1f}%")
    print(f"    nombres crudos           : {base[campo].nunique():,}")
    print(f"    nombres canónicos        : {base[col].nunique():,}")

    return (
        base[con_regla].groupby(col)
        .agg(mdp_real=("monto_real", lambda s: round(s.sum() / 1e6, 1)),
             razones_sociales=(campo, "nunique"),
             renglones=("renglon_id", "size"))
        .sort_values("mdp_real", ascending=False).head(top)
    )
