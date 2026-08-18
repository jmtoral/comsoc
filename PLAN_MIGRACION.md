# Plan de migración y actualización — COMSOC / Publicidad Oficial

De un pipeline en R (2012–2023) a un proyecto en Python reproducible (2012–2026),
con un dataset único de **pólizas** armonizado a través de tres generaciones de formato.

> **Estado (6-ago-2026)**
> - ✅ **Fase 0** — estructura reorganizada, proyecto en R preservado en `legacy/`, `config/` completo.
> - ✅ **Fases 1–4** — pipeline **ejecutado y validado en local** (conda `pnt_analysis`).
>   345,390 filas leídas, 196,480 renglones canónicos, 0 colisiones de id,
>   **las tres pruebas de aceptación en verde**. Se descartó Colab.
>   Serie real completa 2012–2025 más el parcial de 2026 (enero–mayo), sin NaN, con el
>   deflactor revisado de FUNDAR 2025.
> - ⬜ **Fase 5** — hojas `Ejercido` declaradas en `layouts.yaml`, aún no cargadas.
> - ⬜ **Fase 3 (beneficiarios)** — falta el catálogo `RFC → canónico`.
> - ⬜ **Fase 6–7** — análisis y entrega. **Es el siguiente paso.**
>
> Ver [HANDOFF.md](HANDOFF.md) para el estado detallado y [README.md](README.md) para el uso.

---

## 1. Diagnóstico: qué encontré en `data/`

Sondeé los 14 archivos (hojas, fila de encabezado, columnas y número de filas). El problema no es
"cambiaron algunos campos": son **tres generaciones de formato incompatibles** y un archivo duplicado
que sí se puede resolver con evidencia.

### 1.1 Tres generaciones

| Gen | Años | Archivos | Hojas | Fila de encabezado | Columnas |
|-----|------|----------|-------|--------------------|----------|
| **G1** | 2012–2023(prelim) | 11 | 2 (Concepto 3600 / Partida 33605) | **6** (`skip=5`) | 27 (A–AA) |
| **G1b** | 2023 (definitiva) | 1 | 2 (`Pólizas_3600` / `Pólizas_33605`) | **7** (`skip=6`) | 27 (A–AA) |
| **G2** | 2024 | 1 | **4** (2 Ejercido + 2 Pólizas) | **8** y **9** | 23 y 22 |
| **G3** | 2025 | 1 | **4** (2 Ejercido + 2 Pólizas) | **10** y **13** | 8 y 25 |

El script actual (`scripts/1_digest.R`) asume `skip = 5` y `excel_sheets()[1:2]` para todos los archivos.
Eso **rompe** en los tres archivos nuevos: en 2024/2025 las hojas 1 y 3 no son pólizas, son presupuesto.

### 1.2 Las hojas nuevas no son "más de lo mismo"

En 2024 y 2025 aparecen hojas **`Ejercido`**: presupuesto por institución
(anual original, ampliaciones y reducciones, modificado, ejercido, comprometido, % de avance).
No son pólizas y no deben concatenarse con ellas.

> **Pero no las tires.** Es la tabla que te permite comparar *presupuesto autorizado* contra
> *pagado a terceros*, y la columna **"Ampliaciones y Reducciones"** es justo donde se ve el
> comportamiento político del gasto (quién amplía a mitad de año). Va en una tabla aparte:
> `ejercido_presupuestal`.

En 2025 además la hoja de pólizas trae un **panel de totales incrustado** (`Monto`, `IVA`, `Monto+IVA`
en C8:D10) antes del encabezado real, y una fecha de corte (15-jun-2026). Sirve como **cifra de control**
para validar tu suma.

### 1.3 El duplicado de 2023: resuelto

| Archivo | Corte | Leyenda | Filas de datos |
|---|---|---|---|
| `Comsoc_Po_lizas_Transp_DICIEMBRE_2023_COM.xlsx` | 17-ene-2024 | **Cifras preliminares** | 10,752 |
| `P_lizas_COMSOC_enero-diciembre_2023.xlsx` | — | **Cifras definitivas** | 15,353 |

**Regla:** la definitiva es la canónica. **Pero conserva la preliminar** como *vintage* paralelo:
la diferencia es de **+43% de registros**, y saber *qué instituciones aparecen tarde* es en sí mismo
un hallazgo sobre comportamiento del gasto. Es una variable, no basura.

⚠ **Bug en la versión definitiva de 2023:** la columna `Partida` perdió el primer dígito
(`6101` en vez de `36101`, `3605` en vez de `33605`). Hay que repararla por hoja al ingerir.

⚠ En la definitiva el `Sector` también cambió de códigos numéricos (`0`) a alfanuméricos (`GYN`, `47`).

### 1.4 Mapeo de campos entre generaciones

| G1 (2012–2023) | G2 (2024) | G3 (2025) | Canónico |
|---|---|---|---|
| Sector *(numérico)* | Sector *(texto: "HACIENDA")* | Sector *(texto: "MARINA")* | `sector_raw` + `sector` |
| Tipo Institución | — | — | `tipo_institucion` (NA desde 2024) |
| Entidad `00625` | Clave de la Entidad `06370` | Clave `13176` | `clave_entidad` (5 díg.) |
| Nombre | Institución | Denominación de la institución | `institucion` |
| Mes | Mes | Mes | `mes` |
| Fecha de gasto *(serial Excel)* | Fecha De Gasto *(texto dd/mm/aaaa)* | Fecha de Gasto *(texto)* | `fecha_gasto` |
| Partida | Partida | Partida | `partida` |
| Póliza | Póliza | Póliza | `poliza` |
| Cons. | — | Núm. *(≠, es índice)* | `consecutivo` |
| No. de Contrato/Pedido | No. De Contrato/Pedido | No. De Contrato/Pedido | `contrato` |
| Fecha de Contrato/Pedido | Fecha De Contrato | Fecha de Contrato | `fecha_contrato` |
| Producto | Clave Del Producto | Clave del Producto | `producto_clave` |
| Descripción Producto | Descripción Del Producto | Descripción del Producto | `producto_desc` |
| **Importe** | — | — | `importe_poliza` *(ver nota)* |
| **IVA** | — | — | `iva_poliza` |
| Persona (F/M) → `M`/`F` | Persona (F/M) → `Moral` | Persona (F/M) | `persona` |
| Clase de Beneficiario → `P`/`R` | Clase De Beneficiario → **"DIARIOS…"** | Clase de proveedor | ⚠ `clase_beneficiario` |
| — | **RFCB** | **Proveedor (RFC)** | `rfc_beneficiario` ← **nuevo** |
| Beneficiario | Nombre Del Proveedor | Nombre del proveedor | `beneficiario` |
| Campaña *(clave)* | Clave De Campaña + **Nombre De Campaña** | Clave + Nombre de campaña | `campana_clave`, `campana_nombre` |
| Intercambio | — | — | `intercambio` |
| — | Tipo de Póliza *(solo 33605)* | Tipo de Póliza | `tipo_poliza` |
| Unidad de medida | Unidad De Medida | Unidad de medida | `unidad` |
| Descripción Unidad | Descripción De La Unidad | Descripción de la unidad | `unidad_desc` |
| Cantidad | Cantidad | Cantidad | `cantidad` |
| Costo Unitario | Costo Unitario | Costo Unitario | `costo_unitario` |
| **Costo** | **Monto** | **Monto** | `monto` |
| **IVA del Costo** | **IVA** | **IVA** | `iva` |
| Notas aclaratorias | — | — | `notas` |

**Notas críticas del mapeo:**

1. **G1 tiene dos pares de dinero**: `Importe`/`IVA` (nivel póliza) y `Costo`/`IVA del Costo` (nivel renglón).
   G2/G3 sólo conservan el de renglón, renombrado a `Monto`/`IVA`.
   Tu script en R ya usaba `costo + iva_del_costo` → **el mapeo es consistente**, sólo hay que documentarlo.
2. **`Clase de Beneficiario` cambió de significado.** En G1 es un código (`P`, `R`); en G2/G3 la columna
   con ese nombre contiene el **tipo de medio** ("DIARIOS EDITADOS EN LA CIUDAD DE MÉXICO", "INTERNET",
   "MOBILIARIO URBANO"). Es una trampa de nombre: no las unas ciegamente. Mapea la de G2/G3 a
   `clase_medio`, que en G1 hay que derivar de `producto_desc`.
3. **`rfc_beneficiario` es la mejor noticia del formato nuevo.** Resuelve de raíz el problema que en R
   atacabas con 40 `str_detect()` a mano. Sirve como llave dura de 2024 en adelante y como semilla para
   reconciliar los nombres sucios de 2012–2023.
4. **Clasificador presupuestal:** 2012–2023 reporta "Concepto 3600" (= 36101 + 36201); 2024–2025 reporta
   las partidas explícitas. La serie **no se rompe** (3600 ⊃ {36101, 36201}), pero hay que decirlo en la nota
   metodológica. `33605` va siempre aparte.

### 1.5 Trampas ya conocidas (heredadas del pipeline en R)

- Fechas serial de Excel con años imposibles (2026, 2103, 2105) → el R las corregía con `- years(10/90)`.
- ~35 fechas en texto corruptas (`0014`, `0214`, `2047`, `1012`) → hotfix hardcodeado en `1_digest.R:65-71`.
- Filas de subtotal y encabezados repetidos a media hoja → `filter(mes != "Mes")`.
- **Nuevo:** en G2/G3 la fecha ya viene como texto `dd/mm/aaaa`, no como serial → hace falta un parser dual.
- Nombres de beneficiario con espacios insertados: `"GLOBA L, A.C."`, `"S.A. DE C.V ."` → normalización obligatoria.
- `.RData` (19 MB) y los CSV de `clean_data/` (70 y 76 MB) **no deben ir a git**. Parquet + `.gitignore`.

### 1.6 ⚠ Las "dos filas por póliza": qué son realmente

Este es el hallazgo más importante para no romper las cifras. **Cada hoja de G1 (2012–2023)
apila dos tipos de fila mutuamente excluyentes**:

| Tipo de fila | Columnas pobladas | Columnas vacías | Granularidad |
|---|---|---|---|
| **A — factura** | `Importe`, `IVA` | `Cantidad`, `Costo Unitario`, `Costo`, `IVA del Costo`, `Unidad de medida` | nivel factura |
| **B — renglón** | `Cantidad`, `Costo Unitario`, `Costo`, `IVA del Costo`, `Unidad` | `Importe`, `IVA` | nivel inserción |

Verificado en las 24 hojas de 2012–2023:

```
anio  filas_tipo_A  filas_tipo_B   AMBOS   suma(Importe)   suma(Costo)   dif
2012        17,896       20,391       0      7,817.9 M     7,817.9 M   0.00%
2014        18,651       24,736       0      5,930.2 M     5,930.1 M   0.00%
2018        12,869       13,836       0      7,957.2 M     7,957.2 M   0.00%
2022         5,334        6,029       0      2,097.0 M     2,092.7 M   0.21%
2023d        6,575        7,100       0      2,120.5 M     2,119.6 M   0.04%
```

**Tres hechos que cierran el asunto:**

1. **`AMBOS = 0`** en todas las hojas de todos los años (1 sola fila de excepción, en 2021).
   Los dos conjuntos son perfectamente complementarios.
2. **`Cantidad` es un discriminador perfecto**: es `NA` en *exactamente* todas las filas tipo A
   y en ninguna tipo B.
3. **`suma(Importe) ≈ suma(Costo)` con diferencia de 0.00%–0.21%.** No son "facturado" y "pagado":
   **son el mismo dinero, contado a dos granularidades**. Sumar la columna completa sin filtrar
   duplicaría el gasto al ~200%.

> **Tu recuerdo era correcto en el fondo y equivocado en la etiqueta.** No es facturado vs. pagado;
> es **factura vs. desglose de renglones**. Y no siempre son "dos": una factura puede tener varios
> renglones (razón 1:1.14 en promedio, hasta 1:N en pólizas grandes del IMSS).

**Tu código en R ya lo resolvía — pero por accidente.** El filtro
[`1_digest.R:28`](scripts/1_digest.R#L28) `filter(!is.na(cantidad))` se queda exactamente con las
filas tipo B. Es correcto, pero no está documentado y nadie recordaba por qué. **En Python esto debe
ser explícito**: una columna `nivel_registro ∈ {factura, renglon}` y un filtro con nombre, no un
efecto lateral.

**Cuál conservar: las filas tipo B (renglón).** Razones:
- Traen `producto`, `unidad`, `cantidad`, `costo_unitario` → indispensables para el análisis de
  precios atípicos (Fase 6.5).
- Su suma iguala el total facturado de todos modos.
- **Es el único nivel que sobrevive**: 2024 y 2025 ya sólo publican el renglón
  (`Monto` + `IVA`), sin columna `Importe`. Elegir el nivel factura rompería la serie en 2024.

**Pero no tires el tipo A en silencio**: úsalo como *reconciliación*. Las diferencias de 2022 (0.21%,
≈4.3 MDP) y 2023 (0.04%) son facturas sin renglón de desglose o desgloses que no cuadran. Eso es
un reporte de calidad, no un redondeo.

### 1.6.1 Otros dos temas de conteo (distintos del anterior)

**Reversas / contra-asientos (costo negativo).** Existen, pero son marginales y **no hay que borrarlas**:

| año | % filas negativas | efecto en el total |
|---|---|---|
| 2012 | 0.42% | −1.23% |
| 2015 | 0.54% | −0.35% |
| 2016–2023 | ≤0.13% | ≤0.01% |

Sólo el 34% tiene espejo positivo exacto; el resto son ajustes parciales legítimos.
**Súmalas con signo** — excluirlas infla el total.

**Filas exactamente idénticas.** 3,002 grupos / **9,036 filas** en 2012–2023 (≈5.4%), idénticas en
las 30 columnas incluido `Cons.` (p. ej. ISSSTE, póliza `107-000089`, producto 22, `$11,741.73`, dos veces).
No se puede decidir a ciegas si son error de captura o inserciones repetidas legítimas.
**Recomendación: no deduplicar por defecto.** Marca con `n_identicas` y publica el análisis
principal con y sin ellas (test de sensibilidad). En 2025 hay **0 duplicados exactos**, así que
el problema es histórico, no estructural.

**En 2024–2025 esto desaparece.** Un solo tipo de fila, `Monto` + `IVA` por renglón, y aparece
`Tipo de Póliza ∈ {Normal, Intercambio}` — que resucita la vieja columna `Intercambio` de G1
como tipo de póliza (3 filas en 2025). El **intercambio es publicidad pagada en especie**:
decide si entra en "gasto" o se reporta aparte. En 2025 hay además 3 filas con `Monto` negativo.

Validación: `sum(Monto)` 2025 = **3,702,598,799** == la cifra de control incrustada en la hoja. Cuadra exacto.

### 1.7 El RFC del proveedor existe en los extremos de la serie

| Años | `RFCB` | Cobertura |
|---|---|---|
| **2012–2016** | ✅ presente | 96–99% poblada |
| 2017–2023 | ❌ ausente | — |
| **2024–2025** | ✅ presente (`RFCB` / `Proveedor (RFC)`) | — |

Cambia la estrategia de la Fase 3: no hay que reconciliar 14 años de nombres sucios a mano.
Tienes **anclas de RFC en los dos extremos** y sólo un hueco de 7 años (2017–2023) que puentear
por nombre. Construye el catálogo `RFC → beneficiario_canónico` con 2012–2016 + 2024–2025,
y úsalo para resolver el hueco por fuzzy matching contra un universo ya conocido.

*(Nota: el número de columnas en G1 varía más de lo esperado — 2020: 26, 2019/2021/2022/2023: 27,
2012–2016: 28, **2018: 37**. Otra razón para mapear por nombre y nunca por posición: el
`select(1:30)` de `1_digest.R:41` es frágil.)*

---

## 2. Arquitectura propuesta

```
comsoc/
├── notebooks/
│   ├── 00_sondeo_layouts.ipynb      # inspecciona xlsx nuevos → propone layouts.yaml
│   ├── 01_ingesta.ipynb             # xlsx → parquet interim
│   ├── 02_armonizacion.ipynb        # interim → dataset canónico
│   ├── 03_entidades.ipynb           # normalización de beneficiarios
│   └── 10_analisis_*.ipynb          # aquí se van los créditos de Colab
├── src/comsoc/
│   ├── layouts.py     # carga config/layouts.yaml, detecta encabezado
│   ├── ingest.py      # lector genérico por (archivo, hoja)
│   ├── schema.py      # esquema canónico + validación (pandera)
│   ├── clean.py       # fechas, montos, partidas, sectores
│   ├── entities.py    # beneficiarios: RFC + reglas + fuzzy
│   └── deflate.py
├── config/
│   ├── layouts.yaml           # (archivo, hoja) → generación, año, partida, header
│   ├── deflactor.csv          # FUNDAR, base 2020=100, extendido a 2026
│   ├── beneficiarios_map.csv  # tus 40 reglas del R, ahora en datos
│   ├── sectores_ramos.csv
│   └── fechas_corruptas.csv   # el hotfix, ahora en datos
├── data/{raw,interim,processed}/   # en Drive, fuera de git
└── tests/
```

### Decisiones de diseño

**1. Registro declarativo de layouts, no `if/else` por año.**
`config/layouts.yaml` declara para cada `(archivo, hoja)`: `anio`, `generacion`, `tipo`
(`polizas` | `ejercido`), `partida_grupo`, `vintage` (`preliminar` | `definitiva`).
El mapeo de columnas vive **por generación**, no por archivo. Agregar 2026 = agregar 5 líneas de YAML.

**2. Detección automática del encabezado.**
En vez de `skiprows` fijo, busca la primera fila que contenga simultáneamente `Sector` y `Póliza`
(normalizando acentos y espacios). Esto ya te habría salvado del cambio de fila 6 → 7 → 8 → 9 → 13,
y te salvará del archivo de 2026.

**3. Columnas de linaje en todas las filas.**
`archivo`, `hoja`, `generacion`, `anio_fuente`, `partida_grupo`, `vintage`, `es_definitiva`,
`fecha_corte`. Sin esto no puedes auditar ni reproducir, y es lo que da credibilidad al dataset.

**4. Parquet como formato de trabajo.**
~250 mil filas totales. Parsear los 14 xlsx toma 1–2 min; hacerlo en cada sesión de Colab es tirar créditos.
Parquet en Drive → carga en segundos.

### Stack

| R | Python | Nota |
|---|---|---|
| `readxl` | `pandas` + `openpyxl` | `read_only=True` para los archivos grandes |
| `dplyr` / `tidyr` | `pandas` (o `polars` si quieres velocidad) | con 250k filas pandas basta |
| `janitor::clean_names` | función propia (unidecode + snake_case) | |
| `ggplot2` | **`plotnine`** | misma gramática — transición casi literal |
| `ggraph` / `igraph` / `tidygraph` | `networkx` + `python-igraph` | |
| `ggbump` | `plotnine` a mano o `altair` | los bump charts hay que rehacerlos |
| — | **`pandera`** | validación de esquema, no tenías equivalente |
| — | **`rapidfuzz`** | matching de beneficiarios |

En Colab: repo en GitHub, `data/raw` en Drive, `!pip install -e .` desde el repo clonado.
Los créditos van a la Fase 6 (análisis), no a la ingesta.

---

## 3. Fases

### Fase 0 — Andamio
Repo git + `.gitignore` (excluye `.RData`, `.Rhistory`, `clean_data/*.csv`, `data/raw/`).
Estructura de carpetas. `config/layouts.yaml` generado por el notebook de sondeo.
Notebook base de Colab que monta Drive y clona el repo.
**Conserva el código R** en `legacy/` — es tu referencia de verdad para validar la migración.

### Fase 1 — Ingesta
Lector genérico `(archivo, hoja) → DataFrame crudo` con detección de encabezado.
Salida: un parquet por hoja en `data/interim/` (28 tablas). Sin transformar todavía.

### Fase 2 — Armonización
Aplicar el mapeo de §1.4 por generación → esquema canónico → concatenar.
Resolver 2023 (definitiva canónica, preliminar marcada `vintage='preliminar'` y excluida por defecto).

**Paso obligatorio (§1.6): clasificar `nivel_registro`.**
```python
df["nivel_registro"] = np.where(df["cantidad"].isna(), "factura", "renglon")
# el dataset canónico se queda con nivel_registro == "renglon"
# las filas "factura" se guardan aparte en data/interim/reconciliacion_facturas.parquet
```
Nunca implícito. Assert de que la intersección (`Importe` y `Costo` ambos no nulos) sea ~0.

Validación `pandera`: fecha dentro del año fuente, `partida ∈ {33605, 36101, 36201}`,
`clave_entidad` de 5 dígitos. **`monto` puede ser negativo** (reversas, §1.6.1) — no lo restrinjas.

### Fase 3 — Limpieza
- Fechas: parser dual (serial Excel / texto `dd/mm/aaaa`) + `config/fechas_corruptas.csv`.
- Reparar `partida` de 2023-definitiva (dígito perdido, inferido de la hoja de origen).
- Normalizar `sector`: los códigos numéricos de G1 y los nombres de ramo de G2/G3 a un catálogo único.
- `clave_entidad`: zero-pad a 5 dígitos (`625` → `00625`) para que 2022 y 2023 crucen.
- **Beneficiarios**: construir el catálogo `RFC → canónico` con **2012–2016 y 2024–2025** (§1.7),
  portar tus 40 reglas a `beneficiarios_map.csv`, y resolver el hueco 2017–2023 con `rapidfuzz`
  contra ese universo ya conocido.
- **Duplicados exactos**: NO deduplicar por defecto (§1.6.1). Añadir `n_identicas` y correr el
  análisis principal con y sin ellas.
- **Reversas**: conservar con signo. Añadir bandera `es_reversa = monto < 0`.
- **Intercambio**: bandera `es_intercambio` unificando la columna `Intercambio` de G1 con
  `Tipo de Póliza == 'Intercambio'` de G2/G3.

### Fase 4 — Deflactación
Actualizar el deflactor de FUNDAR a 2025–2026 (`inputs/Deflactor_2023-2024_codigo.xlsx` llega a 2024).
Guardar `monto_real` (base 2020=100) **y** `monto_nominal`. Sugerencia: rebasear a 2025 para publicar
—"pesos de 2025" se lee mejor en 2026 que "pesos de 2020".

### Fase 5 — Presupuesto
Cargar las 4 hojas `Ejercido` (2024, 2025) en `ejercido_presupuestal`.
Llave de cruce con pólizas: nombre de institución normalizado (no traen clave) → tabla puente manual,
son ~120 instituciones por año.

### Fase 6 — Análisis: buscar comportamientos
Esta es la parte que justifica los créditos. Preguntas concretas, no exploración vaga:

1. **Ciclo electoral.** Gasto mensual deflactado contra el calendario electoral (2012, 2015, 2018, 2021, 2024).
   ¿Hay pico sistemático antes de la veda? Test de ruptura estructural en dic-2018 y oct-2024.
2. **Concentración.** HHI anual por beneficiario, participación del top-10, curva de Lorenz.
   ¿Se concentró o se dispersó el gasto entre sexenios?
3. **Migración a 33605.** Hipótesis: cuando se recorta 36101 (campañas, con escrutinio), sube 33605
   (operación, sin campaña asociada). Ratio 33605/36101 por institución y año.
4. **Red institución ↔ beneficiario.** Grafo bipartito, comunidades (Louvain), y detección de
   **proveedores cautivos**: beneficiarios que reciben ≥90% de su ingreso de una sola institución.
   Es la actualización natural de `red_amlo.png` / `red_epn.png`.
5. **Anomalías de precio.** Mismo `producto_clave` + `unidad` + mes, con `costo_unitario` muy dispar
   entre instituciones → tabla de outliers. Complementa con ley de Benford sobre `monto`.
6. **Vintage 2023.** Qué instituciones y qué montos aparecen sólo en la cifra definitiva.
   Es una medida directa de opacidad en el reporte preliminar.
7. **Presupuesto vs. pagado** (2024–2025): quién amplía a mitad de año y quién subejerce.

### Fase 7 — Entrega
Notebook reproducible de punta a punta, dataset publicado (parquet + CSV comprimido),
README, y una **ficha metodológica** que documente cada decisión de armonización de §1.4.
Esa ficha es lo que hace el dataset citable.

---

## 4. Validación de la migración

No des por buena la migración hasta que:

- [ ] Total deflactado 2012–2023 en Python == el de `clean_data/deflacted_data.csv` (tolerancia < 0.01%).
- [ ] Conteo de filas por (año, partida) coincide con el pipeline en R.
- [ ] **`sum(monto)` de las filas `renglon` == `sum(importe)` de las filas `factura`**, por año y
      partida, con diferencia < 0.25% (§1.6). Es la prueba de que no se duplicó ni se perdió nada.
      Cifras esperadas (nominales, ambas hojas): 2012 = 7,817.9 M · 2015 = 8,080.6 M ·
      2018 = 7,957.2 M · 2022 = 2,092.7 M · 2023 = 2,119.6 M.
- [ ] Ninguna fila con `importe` y `monto` simultáneamente no nulos (salvo la única de 2021).
- [ ] `gasto_total.png` y `rank_beneficiario.png` regenerados en plotnine son visualmente equivalentes.
- [ ] Suma de `monto` e `IVA` 2025 == el panel de control incrustado en la hoja
      (`Monto = 3,702,598,799.12`, `IVA = 592,232,269.46` para 36101-36201;
      `Monto = 46,359,752.98`, `IVA = 4,958,995.15` para 33605).
- [ ] Ningún registro con `fecha_gasto` fuera de su `anio_fuente` ± 1 mes.

El punto 4 es oro: es la única cifra de control que la propia fuente te da. Úsala.

---

## 5. Decisiones abiertas (mi recomendación por defecto)

| Decisión | Recomendación |
|---|---|
| ¿Serie principal incluye 33605? | **Separada + total.** Su naturaleza es distinta (operación vs. campaña); mezclarlas confunde la lectura. |
| ¿Base del deflactor? | **Rebasear a 2025** para publicación; conservar 2020=100 para comparar con tu trabajo previo. |
| ¿2023 preliminar? | **Excluida por defecto**, disponible vía bandera `vintage`. |
| ¿Extender antes de 2012? | No en la v1. Cierra 2012–2026 primero. |
| ¿Scraper del portal? | Fase 8, opcional. Vale la pena si vas a actualizar cada trimestre; si es anual, la descarga manual está bien. |
| ¿pandas o polars? | **pandas.** 250k filas no justifican el costo de reaprender la API. |
