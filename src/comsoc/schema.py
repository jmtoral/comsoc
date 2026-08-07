"""Esquema canónico y normalización de nombres de columna.

El mapeo vive en config/columnas.yaml, por generación. Aquí sólo está la
mecánica: normalizar nombres, resolver el mapeo y declarar el orden canónico.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import yaml

from .config import CONFIG_DIR

# Generaciones que comparten el mismo layout de columnas.
ALIAS_GENERACION = {"G1b": "G1"}

# Orden canónico del dataset final.
COLUMNAS_CANONICAS = [
    # identificación de la institución que gasta
    "sector",
    "tipo_institucion",
    "clave_entidad",
    "institucion",
    # tiempo
    "mes",
    "fecha_gasto",
    # clasificación presupuestal
    "partida",
    # documento
    "poliza",
    "consecutivo",
    "tipo_poliza",
    "contrato",
    "fecha_contrato",
    # qué se compró
    "producto_clave",
    "producto_desc",
    "unidad",
    "unidad_desc",
    "cantidad",
    "costo_unitario",
    # a quién se le pagó
    "persona",
    "clase_beneficiario",
    "clase_medio",
    "rfc_beneficiario",
    "beneficiario",
    # campaña
    "campana_clave",
    "campana_nombre",
    "intercambio",
    # dinero — nivel RENGLÓN (el que se conserva)
    "monto",
    "iva",
    # dinero — nivel FACTURA (sólo G1; se separa, no se suma junto al anterior)
    "importe_factura",
    "iva_factura",
    # misc
    "notas",
    "fila_num",
]

# Columnas que deben terminar siendo numéricas.
COLUMNAS_NUMERICAS = [
    "cantidad",
    "costo_unitario",
    "monto",
    "iva",
    "importe_factura",
    "iva_factura",
]

# Columnas de linaje que agrega el lector. Sin esto no hay auditoría posible.
COLUMNAS_LINAJE = [
    "archivo",
    "hoja",
    "generacion",
    "anio_fuente",
    "partida_grupo",
    "vintage",
    "nivel_registro",
]

# Palabras que identifican la fila de encabezado dentro de la hoja.
# Se busca la primera fila que contenga TODAS estas (ya normalizadas).
ANCLAS_ENCABEZADO = ("sector", "poliza")


def normalizar_nombre(nombre: object) -> str:
    """'  Descripción De La Unidad ' -> 'descripcion de la unidad'

    Quita acentos, puntuación y colapsa espacios. Es lo que permite que
    'No. de Contrato/Pedido' y 'No. De Contrato/Pedido' sean la misma llave.
    """
    if nombre is None:
        return ""
    texto = str(nombre)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


@lru_cache(maxsize=1)
def _mapeos() -> dict[str, dict[str, str]]:
    with open(CONFIG_DIR / "columnas.yaml", encoding="utf-8") as fh:
        crudo = yaml.safe_load(fh)
    crudo.pop("comun", None)  # es sólo el ancla YAML
    return {gen: {normalizar_nombre(k): v for k, v in cols.items()} for gen, cols in crudo.items()}


def mapeo_de(generacion: str) -> dict[str, str]:
    """Devuelve {nombre_normalizado_fuente: nombre_canonico} para una generación."""
    gen = ALIAS_GENERACION.get(generacion, generacion)
    mapeos = _mapeos()
    if gen not in mapeos:
        raise KeyError(f"generación desconocida en columnas.yaml: {generacion!r}")
    return mapeos[gen]


def aplicar_mapeo(columnas: list[str], generacion: str) -> tuple[dict[str, str], list[str]]:
    """Traduce una lista de columnas fuente al esquema canónico.

    Devuelve (renombres, sin_mapear). `sin_mapear` NO es un error: en 2018 hay
    columnas vacías de relleno y en las hojas de ejercido hay columnas que no
    pertenecen al esquema de pólizas. Pero se reporta siempre, para que un
    campo nuevo en 2026 no pase inadvertido.
    """
    mapeo = mapeo_de(generacion)
    renombres: dict[str, str] = {}
    sin_mapear: list[str] = []
    for col in columnas:
        clave = normalizar_nombre(col)
        if not clave or clave.startswith("unnamed"):
            continue
        destino = mapeo.get(clave)
        if destino is None:
            sin_mapear.append(str(col))
        else:
            renombres[col] = destino
    return renombres, sin_mapear
