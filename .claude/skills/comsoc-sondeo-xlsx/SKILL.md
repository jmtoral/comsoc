---
name: comsoc-sondeo-xlsx
description: Inspecciona la estructura interna de un .xlsx (nombres de hojas, fila de encabezado real, columnas, número de filas) sin depender de Python. Úsalo cuando llegue un archivo COMSOC nuevo o re-descargado, cuando el pipeline falle al leer una hoja, o cuando haya que averiguar si dos archivos del mismo año son ediciones distintas. Palabras clave: sondear, inspeccionar excel, estructura xlsx, encabezado, hojas, layout nuevo.
---

# Sondeo de estructura de archivos .xlsx

## Por qué existe este skill

Para sondear un archivo desconocido conviene **no** usar el mismo lector que el pipeline: si el
pipeline falla, necesitas una herramienta independiente que te diga por qué. Tres vías, de menor
a mayor dependencia:

| Vía | Cuándo | Ruta |
|---|---|---|
| PowerShell + `System.IO.Compression` | estructura: hojas, encabezados, conteo de filas | no necesita nada instalado |
| R + `readxl` | segunda opinión sobre cifras, sin tocar el código Python | `C:\Program Files\R\R-4.5.3\bin\Rscript.exe` |
| Python + `openpyxl` | ya dentro del pipeline | `C:\Users\User\anaconda3\envs\pnt_analysis\python.exe` |

Un `.xlsx` es un ZIP. Su XML se puede leer sin librerías de hojas de cálculo, y eso hace a la
primera vía inmune a cualquier problema de entorno.

**Todo el diagnóstico de este proyecto se hizo con las dos primeras**, y por eso las cifras de
`validate.TOTALES_ESPERADOS_MDP` son una verificación real y no una tautología: las produjo R,
no el código que validan.

## Paso 1 — Nombres de hojas

```powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($ruta)
$e = $zip.Entries | Where-Object { $_.FullName -eq 'xl/workbook.xml' }
$sr = New-Object System.IO.StreamReader($e.Open()); $xml = $sr.ReadToEnd(); $sr.Close(); $zip.Dispose()
[regex]::Matches($xml,'<sheet[^>]*name="([^"]*)"') | ForEach-Object { $_.Groups[1].Value }
```

## Paso 2 — Filas de encabezado y columnas

Usa el script incluido, que resuelve las cadenas compartidas (`sharedStrings.xml`) y vuelca las
primeras N filas con su referencia de celda:

```powershell
. "<proyecto>\.claude\skills\comsoc-sondeo-xlsx\scripts\dump_xlsx.ps1"
Dump-Xlsx -Path "<proyecto>\data\raw\ARCHIVO.xlsx" -MaxRows 14
```

**Sube `-MaxRows` si no aparece el encabezado.** En 2025 está en la fila 13 porque el archivo
incrusta un panel de totales antes de la tabla. No asumas que 8 filas bastan.

## Paso 3 — Conteo de filas por hoja

Sirve para decidir cuál de dos ediciones del mismo año es la definitiva:

```powershell
$m = [regex]::Matches($textoDeSheetN, '<row[^>]*r="(\d+)"')
$m[$m.Count-1].Groups[1].Value   # última fila con datos
```

## Paso 4 — Contenido, con R

Para todo lo que requiera leer valores (tipos, sumas, duplicados), escribe un `.R` en el
scratchpad y ejecútalo. **No pases scripts de varias líneas con `-e`**: falla por el escape de
comillas en PowerShell.

```powershell
& "C:\Program Files\R\R-4.5.3\bin\Rscript.exe" --vanilla "<scratchpad>\sondeo.R" 2>$null
```

Los sondeos que produjeron el diagnóstico están en `legacy/diagnostico/` — reutilízalos como
plantilla antes de escribir uno nuevo.

Paquetes disponibles: `readxl`, `data.table`, `dplyr`, `readr`, `janitor`, `tidyverse`, `yaml`.

Al leer con `readxl`, usa **`col_types = "text"`**. Por defecto adivina el tipo con las primeras
1000 filas y convierte a `NA` columnas enteras que sí tienen datos más abajo — así fue como el
pipeline en R perdió la columna `Importe`.

## Qué reportar siempre

1. Nombres de las hojas y cuáles son de **pólizas** vs. de **ejercido** (presupuesto agregado).
2. Fila del encabezado **por hoja** (varía dentro del mismo archivo: en 2024 es 8 y 9).
3. Lista completa de columnas, comparada contra `config/columnas.yaml`.
4. Filas de datos por hoja.
5. Leyenda de "Cifras preliminares" vs. "Cifras definitivas" y la fecha de corte.
6. Cualquier panel de totales incrustado — es una cifra de control gratuita para validar.

## Trampas conocidas

- El mismo nombre de columna puede significar cosas distintas entre años. `Clase de Beneficiario`
  pasó de ser un código (`P`/`R`) a ser el tipo de medio. Compara **valores**, no solo nombres.
- El número de columnas varía dentro de una misma generación: 26, 27, 28 y hasta **37** (2018).
  Nunca mapees por posición.
- Un archivo puede traer el mismo dato en dos granularidades apiladas en la misma hoja
  (ver `CLAUDE.md`, "las tres trampas"). Si `%NA` de dos columnas de dinero suma ~100%, son
  complementarias, no opcionales.
