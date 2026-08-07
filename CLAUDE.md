# COMSOC — Publicidad oficial (México, 2012–2025)

Dataset unificado de **pólizas** de gasto en comunicación social del gobierno federal mexicano,
a partir de los Excel de la Secretaría Anticorrupción y Buen Gobierno (antes SFP).
Objetivo: **detectar comportamientos en el gasto en publicidad oficial**.

Migración de un pipeline en R (2012–2023, en `legacy/`) a Python reproducible en Colab (2012–2025).

- **[HANDOFF.md](HANDOFF.md)** — estado actual, qué falta, dónde retomar. **Léelo primero.**
- **[PLAN_MIGRACION.md](PLAN_MIGRACION.md)** — diagnóstico de formatos, mapeo de campos, plan por fases.
- **[README.md](README.md)** — estructura y uso.

## Entorno (importante)

**Todo corre en local.** No hay Colab, no hay Drive, no hay kernel remoto.

- **Environment de conda: `pnt_analysis`** (reutilizado, no creado para esto).
  Intérprete: `C:\Users\User\anaconda3\envs\pnt_analysis\python.exe`.
  Python 3.12.3, pandas 2.2.2, pyarrow 16.1, plotnine 0.13.6, networkx, scipy, matplotlib,
  ipykernel. Se le agregaron `openpyxl`, `pyyaml` y `rapidfuzz`.
  El proyecto está instalado ahí en editable (`pip install -e .`).
- `conda` **no está en el PATH**. Invoca el intérprete por ruta completa, o
  `C:\Users\User\anaconda3\Scripts\conda.exe run -n pnt_analysis python ...`.
- Usa **`python -X utf8`**: sin eso, la consola de Windows rompe la salida con acentos.
- **R 4.5.3** en `C:\Program Files\R\R-4.5.3\bin\Rscript.exe` (`readxl`, `data.table`,
  `tidyverse`, `yaml`). Es la segunda opinión para verificar cifras contra los Excel crudos:
  así se determinó todo el diagnóstico. Escribe el script a un `.R` y ejecútalo; `-e` con
  varias líneas falla por el escape de comillas.
- **PowerShell**: un guard bloquea `Move-Item`/`Remove-Item` con globs tipo `"$var\dir\*"`.
  Usa `-LiteralPath` con rutas completas, iterando con `Get-ChildItem`.
- No es un repositorio git todavía.

## Las tres trampas

Rompen las cifras **sin producir ningún error**. Están medidas, no supuestas.

**1. Dos filas por póliza (2012–2023).** Cada hoja apila dos tipos de fila mutuamente excluyentes:
*factura* (`Importe`/`IVA`) y *renglón* (`Cantidad`/`Costo`). No son "facturado vs. pagado":
son **el mismo dinero a dos granularidades** — verificado, `suma(Importe) ≈ suma(Costo)` con
0.00%–0.21% de diferencia. Sumar la columna sin separarlas **duplica el gasto al ~200%**.

- `cantidad` es discriminador exacto (`NA` en toda fila de factura, en ninguna de renglón).
- El dataset canónico conserva solo `nivel_registro == "renglon"`: es el único nivel que
  sobrevive en 2024–2025, donde la columna `Importe` ya no existe.
- El pipeline en R lo resolvía **por accidente**, con `filter(!is.na(cantidad))`
  en [`legacy/R/1_digest.R:28`](legacy/R/1_digest.R#L28). En Python es explícito.

**2. `Clase de Beneficiario` cambió de significado.** En 2012–2023 es un código (`P`/`R`); en 2024
la columna homónima trae el **tipo de medio** ("DIARIOS EDITADOS EN LA CIUDAD DE MÉXICO").
Se mapean a campos distintos: `clase_beneficiario` / `clase_medio`.

**3. `IVA` cambió de nivel.** En G1 acompaña a `Importe` (factura); en G2/G3 a `Monto` (renglón).

## Principio de diseño

**Todo lo específico de un año vive en `config/`. El código no tiene un solo `if anio == ...`.**

- `config/layouts.yaml` — 15 archivos, 34 hojas: generación, tipo, partida, fila de encabezado.
- `config/columnas.yaml` — mapeo al esquema canónico, **por generación** (así se resuelven las
  trampas 2 y 3).
- El encabezado se **detecta automáticamente** (`layouts.detectar_header_row`): se ha movido
  6 → 7 → 8 → 9 → 10 → 13 en cuatro años. El `header_row` del YAML es una aserción que avisa.
- **Mapea siempre por nombre, nunca por posición**: el número de columnas varía dentro de una
  misma generación (26, 27, 28 y hasta 37 en 2018).

## Identificadores

`poliza_id` (la póliza) y `renglon_id` (la fila) son **hash del contenido**, no contadores:
estables entre corridas y máquinas, independientes del orden de lectura. Ver `src/comsoc/ids.py`.

La llave de póliza es `anio_fuente + partida_grupo + clave_entidad + poliza`, verificada contra
los datos: 6,762 números de póliza los usa más de una entidad el mismo año y 1,328 aparecen en
los dos grupos de partida. **Usa `partida_grupo`, nunca `partida`**: 10 pólizas abarcan 36101 y
36201 a la vez y `partida` las partiría en dos.

`poliza_id` **no** incluye `vintage` a propósito, para poder comparar la edición preliminar
contra la definitiva de 2023. `renglon_id` sí lo incluye, más `ocurrencia`, que desempata las
9,036 filas idénticas del histórico.

La columna `Núm.` de 2025 es única pero es un índice de reporte: cambia con cada republicación.
No la uses como identificador; se conserva como `fila_num`.

## Reglas de trabajo

- **Verifica contra los datos, no supongas.** Las conclusiones de este proyecto salieron de
  sondear los 15 archivos con R. Los scripts están en `legacy/diagnostico/`.
- **Toda regla heredada del pipeline en R está calibrada para 2012–2023.** Antes de aplicarla a
  2024+ hay que acotarla. La regla `2026 → 2016` de reparación de fechas arruinó 1,003 filas de
  2025, donde las fechas de 2026 son legítimas. Las correcciones se acotan por `anio_fuente`.
- **Nunca borres filas raras: márcalas.** Reversas (`es_reversa`), duplicados exactos
  (`n_identicas`), fechas imposibles (`fecha_fuera_de_rango`), intercambios (`es_intercambio`).
  Excluir por defecto sesga el resultado; marcar permite el test de sensibilidad.
- **`legacy/` no se toca.** Es la referencia de validación de la migración.
  `legacy/clean_data/` contiene la salida del pipeline en R.
- **Las tres pruebas de aceptación (`comsoc.validate`) son la condición de entrega.**
  Si alguna falla, la cifra está mal y todo lo construido encima hereda el error.

## Skills del proyecto

| Skill | Cuándo |
|---|---|
| `comsoc-sondeo-xlsx` | inspeccionar la estructura de un .xlsx sin Python |
| `comsoc-nuevo-anio` | dar de alta un archivo nuevo o una re-descarga |
| `comsoc-analisis` | antes de cualquier agregación o cifra publicable |

## Convenciones

- Código, comentarios y documentación **en español**, como el resto del proyecto.
- Nombres canónicos sin acentos (`institucion`, `campana_clave`); los acentos solo en textos.
- Agrupa la serie por **`anio_fuente`**, no por `anio`.
- Compara entre años solo en **`monto_real`** (pesos constantes).
