# COMSOC — Publicidad oficial del gobierno federal mexicano

- **Reporte interactivo → <https://jmtoral.github.io/comsoc/>**
  Serie anual, medios en el tiempo, campañas, concentración de proveedores y buscador.
- **¿Quién le paga a quién? → <https://jmtoral.github.io/comsoc/quien-paga-a-quien.html>**
  Treemap de pantalla completa: clic en una institución y se abren las empresas que cobraron.
- **¿En qué medios? → <https://jmtoral.github.io/comsoc/medios.html>**
  Lo mismo por familia de medio, con desglose por producto.

Dataset unificado de **pólizas** de gasto en comunicación social, 2012–2025, a partir de los
Excel que publica la Secretaría Anticorrupción y Buen Gobierno (antes SFP).

Análisis y elaboración: **Manuel Toral**.

---

## De dónde viene esto

Este proyecto empezó en **R, en 2024**, y cubría 2012–2023: cinco scripts que leían doce Excel,
los apilaban y producían una serie del gasto federal en publicidad oficial más siete gráficas.
Funcionaba. Ese código sigue aquí, intacto, en [`legacy/`](legacy/) — no como museo, sino porque
es la **referencia de validación**: una de las pruebas de aceptación compara las cifras nuevas
contra la salida de aquel pipeline.

Al querer actualizarlo aparecieron tres problemas que no se arreglaban con un par de líneas:

1. **Llegaron 2024 y 2025 con otro formato.** No eran «algunos campos distintos»: son tres
   generaciones incompatibles. Las hojas pasaron de 2 a 4, la fila del encabezado se movió
   6 → 7 → 8 → 9 → 10 → 13, y el número de columnas varía entre 22 y 37 según el año.
2. **Los años nuevos metieron todo en pestañas**, y dos de las cuatro no son pólizas sino
   presupuesto agregado. Mezclarlas habría contado el gasto dos veces.
3. **Para 2023 había dos archivos**, ediciones distintas del mismo ejercicio, sin saber cuál usar.

Al migrar salieron además cosas que el pipeline en R no podía ver, porque solo llegaba a 2023:

- Cada hoja de 2012–2023 **apila dos tipos de fila** con el mismo dinero a dos granularidades.
  El código en R lo resolvía por accidente, con un filtro que quitaba justo las filas correctas
  sin que nadie supiera por qué. Sumarlas sin separarlas duplica el gasto al 200%.
- La regla de reparación de fechas heredada del R **arruinaba 1,003 filas de 2025**: convertía
  fechas de 2026 en 2016, lo correcto para un archivo de 2016 y falso para uno cuyo corte es
  junio de 2026.
- La regla de homologación de CONDUSEF exigía acentos, y **679 renglones vienen sin ellos**:
  media institución quedaba fuera de su propio grupo, sin que nada lo señalara.

El diagnóstico completo, con las cifras que lo sostienen, está en
[PLAN_MIGRACION.md](PLAN_MIGRACION.md). Qué se hizo y qué falta, en [HANDOFF.md](HANDOFF.md).

**El principio que ordena todo el rediseño:** lo específico de cada año vive en `config/`, no en
el código. No hay un solo `if anio == ...`. Dar de alta 2026 debería ser agregar un bloque de
YAML, no tocar el pipeline.

Migración del pipeline original en R (`legacy/R/`) a Python, con el objetivo de **detectar
comportamientos en el gasto en publicidad oficial**.

El diagnóstico completo de formatos, el mapeo de campos y las fases del trabajo están en
**[PLAN_MIGRACION.md](PLAN_MIGRACION.md)**. Léelo antes de tocar el pipeline: documenta tres
trampas que rompen las cifras en silencio.

---

## Estructura

```
.
├── PLAN_MIGRACION.md          Diagnóstico, mapeo de campos y plan por fases
├── config/
│   ├── layouts.yaml           (archivo, hoja) → generación, tipo, partida, encabezado
│   ├── columnas.yaml          mapeo de columnas fuente → esquema canónico, por generación
│   ├── beneficiarios_map.csv  37 reglas de homologación, portadas del proyecto en R
│   ├── instituciones_map.csv  22 reglas de homologación, portadas del proyecto en R
│   ├── deflactor.csv          deflactor implícito del PIB, base 2020=100 (FUNDAR)
│   └── fechas_corruptas.yaml  reglas de reparación de fechas mal capturadas
├── src/comsoc/
│   ├── config.py              rutas (respeta $COMSOC_ROOT para Colab)
│   ├── layouts.py             registro de hojas + detección automática del encabezado
│   ├── schema.py              esquema canónico y normalización de nombres
│   ├── ingest.py              lector único para las tres generaciones
│   ├── clean.py               fechas, partidas, llaves, banderas
│   ├── ids.py                 poliza_id / renglon_id (hash de contenido)
│   ├── entities.py            homologación de beneficiarios e instituciones
│   ├── deflate.py             pesos constantes
│   ├── validate.py            pruebas de aceptación
│   ├── export.py              exportación a parquet / CSV
│   ├── reporte.py             genera docs/index.html (sitio autocontenido)
│   ├── zoom.py                genera docs/quien-paga-a-quien.html (treemap con zoom)
│   └── build.py               pipeline completo (CLI)
├── data/
│   ├── raw/                   los 15 .xlsx originales
│   ├── interim/               un parquet por hoja + reconciliación de facturas
│   └── processed/             comsoc_polizas.parquet ← la salida
├── docs/index.html            el reporte publicable — GitHub Pages sirve de aquí
├── notebooks/                 análisis
├── referencias/               documentos externos (informe A19, notas metodológicas)
├── reports/                   tablas de calidad y reconciliación que genera el pipeline
├── tests/
└── legacy/                    proyecto original en R, intacto
    ├── R/                     los 5 scripts originales
    ├── clean_data/            salida del pipeline en R — referencia de validación
    ├── diagnostico/           scripts con que se determinó la estructura de los archivos
    ├── graphs/                gráficas originales
    └── inputs/                deflactor original en xlsx
```

## Descargar el dataset

| Archivo | Tamaño | Para quién |
|---|---:|---|
| [`comsoc_polizas_csv.zip`](https://jmtoral.github.io/comsoc/datos/comsoc_polizas_csv.zip) | 15.7 MB | Excel, R, pandas, Stata |
| [`comsoc_polizas.parquet`](https://jmtoral.github.io/comsoc/datos/comsoc_polizas.parquet) | 11.7 MB | Python o R, con tipos |

196,480 renglones × 58 columnas, 2012–2025. El reporte incluye el diccionario completo de las 58
columnas y un tercer botón que genera al vuelo el resumen por entidad y año (13,894 filas).

Va en **ZIP y no en GZIP** por una razón práctica: Windows abre `.zip` con doble clic y `.gz` no,
así que un `.csv.gz` se descarga bien y aun así no se puede abrir sin instalar nada.

Se regeneran con `python -c "from comsoc import export; export.publicar_descargas()"`.

## Los datos de origen

**Los 15 Excel no están versionados** (45 MB, y son públicos). Para correr el pipeline hay que
descargarlos y ponerlos en `data/raw/` con su nombre original:

<https://www.gob.mx/buengobierno/documentos/estrategia-de-comunicacion-social>

`config/layouts.yaml` lista los 15 nombres de archivo exactos que el pipeline espera. Si alguno
cambia de nombre o de estructura, ese archivo es el único lugar que hay que tocar — ver el skill
`comsoc-nuevo-anio`.

El reporte publicado en `docs/index.html` **sí** trae sus datos embebidos, así que se puede leer
sin descargar nada.

## Uso

Todo corre **en local**, sobre el environment de conda **`pnt_analysis`**.

```powershell
$py = "C:\Users\User\anaconda3\envs\pnt_analysis\python.exe"
& $py -X utf8 -m comsoc.build
```

`-X utf8` es necesario: sin él la consola de Windows rompe la salida con acentos.
`conda` no está en el PATH; invoca el intérprete por ruta completa o usa
`conda run -n pnt_analysis`.

El parseo de los 15 Excel tarda ~1 minuto y produce `data/processed/comsoc_polizas.parquet`.
Hazlo **una vez** y trabaja sobre el parquet.

En VS Code, selecciona el kernel `pnt_analysis` y abre
[`notebooks/00_construir_dataset.ipynb`](notebooks/00_construir_dataset.ipynb).

### El environment

`pnt_analysis` se **reutilizó**, no se creó para este proyecto: ya traía pandas 2.2.2,
pyarrow 16.1, plotnine 0.13.6, networkx, scipy, matplotlib e ipykernel. Se le agregaron
`openpyxl`, `pyyaml` y `rapidfuzz`, y se instaló el proyecto en editable:

```powershell
& $py -m pip install openpyxl pyyaml rapidfuzz
& $py -m pip install -e .
```

`comsoc.export` genera copias en parquet y CSV comprimido para compartir
(`export.exportar(df, formatos=("parquet", "csv"))`) y `export.muestra(df, n=5000)` un
subconjunto ligero.

## Identificadores

| Columna | Qué identifica |
|---|---|
| `poliza_id` | la **póliza**: hash de `anio_fuente + partida_grupo + clave_entidad + poliza` |
| `renglon_id` | el **renglón**; único en todo el dataset |
| `n_renglones` | cuántos renglones tiene la póliza de esa fila |
| `ocurrencia` | desempata las filas idénticas |

Son hash del contenido, no contadores: estables entre corridas y entre máquinas, e
independientes del orden de lectura de los archivos.

La llave está verificada contra los datos ([`legacy/diagnostico/llave_poliza.R`](legacy/diagnostico/llave_poliza.R)):
6,762 números de póliza los usa más de una entidad el mismo año, y 1,328 aparecen en los dos
grupos de partida — por eso la llave lleva entidad y grupo. Usa `partida_grupo` y **no** `partida`
porque 10 pólizas abarcan 36101 y 36201 a la vez, y `partida` las partiría en dos.

`poliza_id` **no** incluye `vintage` a propósito: así la misma póliza en la edición preliminar y
en la definitiva de 2023 recibe el mismo id, que es lo que permite compararlas
(`ids.comparar_vintages`).

## Los tres formatos

Los archivos cambiaron de estructura dos veces. Todo lo específico de cada año vive en
`config/`; el código no tiene un solo `if anio == ...`.

| Gen | Años | Hojas | Encabezado | Notas |
|-----|------|-------|-----------|-------|
| G1  | 2012–2023 | 2 | fila 6 | dos tipos de fila (factura / renglón) |
| G1b | 2023 definitiva | 2 | fila 7 | bug: `Partida` sin el primer dígito |
| G2  | 2024 | 4 | filas 8 y 9 | + `Ejercido`; vuelve el RFC; sin `Importe` |
| G3  | 2025 | 4 | filas 10 y 13 | + `Núm.`, + panel de totales incrustado |

Agregar 2026 = agregar un bloque a `config/layouts.yaml`. Si el encabezado se mueve otra vez,
`layouts.detectar_header_row()` lo encuentra solo y avisa de la discrepancia.

## Las tres trampas

1. **Dos filas por póliza (§1.6).** En 2012–2023 cada hoja apila filas de *factura*
   (`Importe`/`IVA`) y de *renglón* (`Cantidad`/`Costo`), mutuamente excluyentes.
   No son "facturado vs. pagado": son el mismo dinero a dos granularidades, y sumar la columna
   sin separarlas **duplica el gasto al ~200%**. `ingest` marca `nivel_registro` y el dataset
   canónico conserva sólo `renglon` — el único nivel que sobrevive en 2024–2025.
2. **`Clase de Beneficiario` cambió de significado.** En G1 es un código (`P`/`R`); en G2 la
   columna homónima trae el tipo de medio. Se mapean a campos distintos
   (`clase_beneficiario` / `clase_medio`).
3. **`IVA` cambió de nivel.** En G1 acompaña a `Importe` (factura); en G2/G3 a `Monto` (renglón).

## Validación

`python -m comsoc.build` corre cuatro pruebas de aceptación:

- **Factura vs. renglón**: sus sumas deben coincidir dentro de 0.25% por año y partida.
- **Totales históricos**: contra las cifras verificadas en `legacy/diagnostico/`.
- **Cifra de control 2025**: el archivo incrusta su propio total
  (`36101-36201`: 3,702,598,799.12 · `33605`: 46,359,752.98). Debe cuadrar exacto.
- **Contraste externo**: contra ARTICLE 19 / Política Colectiva, *Publicidad Oficial 2024*
  (2018–2024). Es la única verificación contra una fuente **independiente** de este pipeline;
  las tasas de crecimiento real coinciden al decimal. Ver [`referencias/`](referencias/README.md).

## El reporte publicable

```powershell
& $py -X utf8 -m comsoc.reporte      # -> docs/index.html
```

Un solo archivo autocontenido, ~47 KB, **sin ninguna dependencia externa**: los datos van
embebidos como JSON y no hay CDN, webfont ni script remoto. Se abre con doble clic o se publica
tal cual.

**Para GitHub Pages:** en *Settings → Pages*, elegir la rama y la carpeta `/docs`. No hace falta
build ni Jekyll (puedes añadir un `.nojekyll` vacío si algún día usas archivos con guion bajo).

Tema **único claro sobre crema** (`#FBF5E6`), por decisión: el reporte se publica y se imprime,
y un cambio automático a oscuro invertiría el sentido de la rampa secuencial de los treemaps.

La autoría (**Manuel Toral**) va en el `<meta name="author">`, en la cabecera, en el pie de fuente
y —lo que importa— **dentro de cada SVG**: cualquier captura o recorte de una gráfica se lleva el
crédito consigo.

## Deflactor

`config/deflactor.csv` — implícito del PIB, base 2020=100, serie 1993–2026 completa, de la
[Nota Metodológica 2025 de FUNDAR](https://fundar.org.mx/wp-content/uploads/2025/09/Nota_Metodologica_2025.pdf).

**Es una serie revisada**, no la misma que usaba el pipeline en R (2012 pasó de 71.545 a 70.335,
2023 de 118.474 a 116.654). Reemplaza por completo a `legacy/inputs/`; mezclarlas daría una serie
real incoherente. Por eso las cifras reales no coinciden con el trabajo original.

2025 y 2026 son **estimados** (`estimado == 1` en el CSV); `deflate.deflactar` lo avisa en cada
corrida y debe decirse en la nota al pie de cualquier gráfica que los incluya.

## Pendientes conocidos

- **Reconciliación de beneficiarios**: el catálogo `RFC → canónico` (Fase 3) aún no está.
  Hay RFC en 2012–2016 y 2024–2025; el hueco 2017–2023 se puentea por nombre.
- **Hojas `Ejercido`** (2024–2025): declaradas en `layouts.yaml` pero aún no cargadas
  a `comsoc_ejercido.parquet` (Fase 5).
- El código Python **no se ha ejecutado en esta máquina** (no hay intérprete instalado);
  se escribió contra la estructura real de los archivos, verificada con R. La primera
  corrida en Colab es también su primera prueba.

## Fuente

Secretaría Anticorrupción y Buen Gobierno (antes Secretaría de la Función Pública),
Sistema de Gastos de Comunicación Social (COMSOC).
Deflactor: [FUNDAR](https://fundar.org.mx/wp-content/uploads/2022/04/Base-deflactor-2023.pdf).
