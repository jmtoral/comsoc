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


# Sufijos de razón social: no distinguen empresas, solo estorban al comparar.
_SUFIJOS = (r"(S\.?A\.?P\.?I\.?|S\.?A\.?B\.?|S\.?A\.?|S\.?C\.?|S\.?DE\.?R\.?L\.?|S\.?R\.?L\.?|"
            r"S\.?N\.?C\.?|A\.?C\.?|S\.?AS\.?|DE\.?C\.?V\.?|C\.?V\.?|DE|SOFOM|ENR)")


def clave_dura(nombre: object) -> str:
    """Forma comparable de una razón social: sin acentos, sin puntuación, SIN ESPACIOS.

    Quitar los espacios es lo que resuelve el ruido de captura de esta fuente, que
    parte palabras a la mitad: «INFOR MACIÓN», «NAC IONAL», «TAB ASCO». Con espacios
    esas variantes son cadenas distintas; sin ellos, la misma.
    """
    t = plegar(nombre).upper()
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    t = re.sub(r"\b" + _SUFIJOS + r"\b", " ", t)
    return re.sub(r"\s+", "", t)


def _componentes(pares: list[tuple[str, str]]) -> dict[str, str]:
    """Union-find: agrupa lo que está conectado y devuelve {miembro: raíz}."""
    padre: dict[str, str] = {}

    def raiz(x: str) -> str:
        padre.setdefault(x, x)
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for a, b in pares:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[rb] = ra
    return {x: raiz(x) for x in padre}


def consolidar_beneficiarios(df: pd.DataFrame) -> pd.Series:
    """Un nombre representativo por empresa, antes de aplicar las reglas editoriales.

    Dos señales, ambas deterministas —nada de similitud aproximada, que produce
    fusiones falsas difíciles de auditar:

    1. **Clave dura**: dos escrituras que colapsan al quitar espacios y puntuación
       son la misma empresa.
    2. **RFC**: dos claves duras que comparten RFC son la misma empresa, aunque se
       llamen distinto. Solo alcanza a 2012-2016 y 2024-2025, que es donde la fuente
       publica el RFC.

    El representante de cada grupo es el nombre crudo más frecuente: es el que la
    fuente escribe bien más veces.
    """
    cd = df["beneficiario"].map(clave_dura)
    rfc = df["rfc_beneficiario"]

    pares = [(c, c) for c in cd.unique()]
    con_rfc = df.loc[rfc.notna()]
    if len(con_rfc):
        por_rfc = pd.DataFrame({"cd": cd[rfc.notna()], "rfc": rfc[rfc.notna()]}).drop_duplicates()
        for _, g in por_rfc.groupby("rfc")["cd"]:
            claves = list(g)
            pares += [(claves[0], k) for k in claves[1:]]

    raiz = _componentes(pares)

    frec = (df.assign(_cd=cd).groupby(["_cd", "beneficiario"], observed=True)
            .size().rename("n").reset_index())
    frec["_raiz"] = frec["_cd"].map(raiz)
    repr_ = (frec.sort_values("n", ascending=False)
             .groupby("_raiz")["beneficiario"].first())

    return cd.map(raiz).map(repr_).fillna(df["beneficiario"])


@lru_cache(maxsize=1)
def catalogo_medios() -> pd.DataFrame:
    """`producto_clave` -> familia de medio y nombre limpio del producto.

    La clave es el catálogo estable: existe al 100% en los 14 años y solo tiene 37
    valores. `producto_desc` es la misma información pero con ruido de captura —la
    clave 21 aparece con 17 redacciones distintas—, y `clase_medio` solo existe en
    2024-2025. Por eso el medio se deriva de la clave, no del texto.
    """
    cat = pd.read_csv(CONFIG_DIR / "medios.csv", dtype={"producto_clave": str})
    return cat.set_index("producto_clave")


def agregar_canonicos(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega los nombres canónicos de beneficiario, institución y medio."""
    df = df.copy()
    # Primero se consolidan las razones sociales por clave dura y RFC; las reglas
    # editoriales se aplican sobre el representante, no sobre cada variante.
    df["beneficiario_consolidado"] = consolidar_beneficiarios(df)
    df["beneficiario_canonico"] = canonizar(
        df["beneficiario_consolidado"], "beneficiario", minusculas=True)
    df["institucion_canonica"] = canonizar(df["institucion"], "institucion", minusculas=False)

    cat = catalogo_medios()
    clave = df["producto_clave"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    df["medio_familia"] = clave.map(cat["familia"]).fillna("Sin clasificar")
    df["medio_producto"] = clave.map(cat["producto"]).fillna(
        df["producto_desc"].astype("string").str.title()).fillna("Sin clasificar")
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
