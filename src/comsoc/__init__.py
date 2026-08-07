"""COMSOC — gasto en publicidad oficial del gobierno federal mexicano, 2012-2025."""

# `reporte` y `zoom` no se importan aquí a propósito: son puntos de entrada de CLI
# y cargarlos de forma anticipada hace que `python -m comsoc.reporte` avise de una
# doble ejecución del módulo.
from . import clean, config, deflate, entities, export, ids, ingest, layouts, schema, validate

__version__ = "0.1.0"

__all__ = [
    "clean", "config", "deflate", "entities", "export", "ids",
    "ingest", "layouts", "schema", "validate",
]
