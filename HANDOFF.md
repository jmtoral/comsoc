# Handoff — 6 de agosto de 2026

Estado del proyecto COMSOC: migración del pipeline en R a Python, dataset validado y reporte
publicable. Punto de entrada para retomar en frío.

Ver [CLAUDE.md](CLAUDE.md) para las reglas del proyecto y [PLAN_MIGRACION.md](PLAN_MIGRACION.md)
para el diagnóstico completo de formatos.

**Repositorio:** <https://github.com/jmtoral/comsoc>

---

## 1. De dónde se partió

Un proyecto en R que producía una serie 2012–2023 del gasto federal en publicidad oficial
(5 scripts, `clean_data.csv`, 7 gráficas). Tres problemas al querer actualizarlo:

- Habían llegado los archivos de **2024 y 2025**, con formato distinto.
- Los años nuevos **metieron todo en pestañas** adicionales.
- Para **2023 había dos archivos**, ediciones distintas, sin saber cuál usar.

---

## 2. Estado actual

### ✅ El pipeline corre y pasa las cuatro pruebas de aceptación

```
total crudo                345,390 filas   (196,480 renglón / 148,910 factura)
partida reparada (2023)     15,892 valores
fechas fuera de rango          107 filas   (marcadas, no corregidas)
pólizas                    104,203          1.89 renglones por póliza
renglon_id colisiones            0
warnings                         0

Factura vs renglón (G1)     OK   26 combinaciones año × vintage × partida
Totales históricos          OK   máxima desviación 0.0016%
Cifra de control 2025       OK   cuadra al centavo
Contraste ARTICLE 19        OK   2018-2024, tasas idénticas al decimal
```

La ingesta reproduce **exactamente** los conteos verificados en R, hoja por hoja
(2012 hoja 1: 29,908 filas = 16,029 renglón + 13,879 factura; 2025: 8,831 renglones).
Los totales coinciden con `legacy/clean_data/`: la migración no duplicó ni perdió dinero.

Salidas: `data/processed/comsoc_polizas.parquet` (196,480 filas) y `docs/index.html`.

Para reconstruir todo desde cero:

```powershell
$py = "C:\Users\User\anaconda3\envs\pnt_analysis\python.exe"
& $py -X utf8 -m comsoc.build      # datos  -> parquet
& $py -X utf8 -m comsoc.reporte    # parquet -> docs/index.html
```

### La serie real — la salida principal

MDP de 2020, ediciones definitivas, sin intercambios en especie. Completa, sin NaN.

| año | nominal | real 2020 | var % |     | año | nominal | real 2020 | var % |
|-----|--------:|----------:|------:|-----|-----|--------:|----------:|------:|
|2012 | 8,957 | 12,735 |   —   | |2019 | 3,151 | 3,296 | **−67.3** |
|2013 | 7,100 |  9,925 | −22.1 | |2020 | 2,172 | 2,172 | −34.1 |
|2014 | 6,799 |  9,107 |  −8.2 | |2021 | 2,305 | 2,206 |  +1.6 |
|2015 | 9,288 | 12,053 | +32.3 | |2022 | 2,427 | 2,177 |  −1.3 |
|2016 |10,312 | 12,618 |  +4.7 | |2023 | 2,458 | 2,107 |  −3.2 |
|2017 |10,696 | 12,278 |  −2.7 | |2024 | 3,608 | 2,948 | **+39.9** |
|2018 | 9,227 | 10,068 | −18.0 | |2025 | 4,342 | 3,399 | **+15.3** |

Tres cosas que son el punto de partida del análisis:

1. **El desplome de 2019 es de −67.3% real**, primer año del sexenio anterior.
2. **Piso plano 2020–2023** en ~2,100–2,200 MDP reales, variación de ±3%.
3. **Dos años consecutivos de alza real: +39.9% en 2024 y +15.3% en 2025.** 2025 es el nivel
   más alto desde 2018. Territorio nuevo: el trabajo original terminaba en 2023.

⚠ El deflactor de 2025 es **estimado**. Debe decirse en cualquier gráfica que lo incluya.

---

## 3. Qué se construyó

### 3.1 Diagnóstico: tres generaciones de formato

| Gen | Años | Hojas | Encabezado | Columnas |
|-----|------|-------|-----------|----------|
| G1  | 2012–2023 prelim | 2 | fila 6 | 26–37 (varía) |
| G1b | 2023 definitiva | 2 | fila 7 | 27 |
| G2  | 2024 | 4 | filas 8 y 9 | 23 y 22 |
| G3  | 2025 | 4 | filas 10 y 13 | 8 y 25 |

**El duplicado de 2023, resuelto con evidencia interna del archivo:**

| Archivo | Leyenda | Filas |
|---|---|---|
| `Comsoc_Po_lizas_Transp_DICIEMBRE_2023_COM.xlsx` | Cifras **preliminares** (corte 17-ene-2024) | 10,752 |
| `P_lizas_COMSOC_enero-diciembre_2023.xlsx` | Cifras **definitivas** | 15,353 |

La definitiva es canónica. La preliminar se conserva con `vintage='preliminar'`: el +43% de
registros que aparecen después del corte es una medida directa de opacidad, no basura.

**Las pestañas nuevas no son pólizas.** En 2024–2025 dos de las cuatro hojas son `Ejercido`:
presupuesto por institución. Tabla aparte, aún sin cargar (pendiente 2).

### 3.2 El hallazgo principal: las "dos filas por póliza"

Cada hoja de G1 apila filas de **factura** (`Importe`/`IVA`) y de **renglón** (`Cantidad`/`Costo`),
mutuamente excluyentes (`AMBOS = 0`, una sola excepción en 2021). `suma(Importe) ≈ suma(Costo)`
con 0.00%–0.21% de diferencia: **es el mismo dinero a dos granularidades**, y sumar sin separar
duplica el gasto al ~200%.

El pipeline en R lo resolvía **por accidente**, con `filter(!is.na(cantidad))`. Ahora es explícito
(`nivel_registro`) y las filas de factura se guardan para reconciliación en vez de descartarse.

### 3.3 Otros hallazgos del diagnóstico

- **El RFC del proveedor existe en 2012–2016 y 2024–2025**, no en 2017–2023: hay anclas duras en
  los dos extremos y solo un hueco de 7 años que puentear por nombre.
- **Bug de la fuente en 2023 definitivo**: `Partida` perdió el primer dígito (`6101` por `36101`).
  Se repara en `clean.reparar_partida`.
- **Reversas** (monto negativo): marginales (≤1.23% en 2012, ~0% desde 2016). Se suman con signo.
- **9,036 filas exactamente duplicadas.** No se deduplican a ciegas; se marcan con `n_identicas`.
- **Cifra de control gratuita**: el archivo de 2025 incrusta sus propios totales.

### 3.4 Identificadores (`ids.py`)

`poliza_id` y `renglon_id`, hash del contenido — estables entre corridas y máquinas.
Llave verificada contra los datos (`legacy/diagnostico/llave_poliza.R`):

- 6,762 números de póliza los usa **más de una entidad** el mismo año → `clave_entidad` en la llave.
- 1,328 números aparecen en **los dos grupos de partida** → `partida_grupo` en la llave.
- 10 pólizas abarcan 36101 y 36201 → la llave usa `partida_grupo`, **no** `partida`.
- `Núm.` de 2025 es único pero es índice de reporte: no sirve como id.

`poliza_id` no incluye `vintage` a propósito, para poder comparar preliminar contra definitiva
(`ids.comparar_vintages`). `renglon_id` sí, más `ocurrencia`, que desempata las filas idénticas.

### 3.5 Homologación de nombres (`entities.py`)

Las reglas escritas a mano en `legacy/R/3_analysis_and_vizes.R` están portadas a
`config/beneficiarios_map.csv` (37) y `config/instituciones_map.csv` (23).
Cobertura: **63.1% del gasto** en beneficiarios, 33.2% en instituciones.

**Tres correcciones al original:**

1. **El match ignora acentos.** La regla de CONDUSEF del R exigía `COMISIÓN...PROTECCIÓN`, pero
   679 renglones vienen sin acentos: cerca de la mitad de esa institución quedaba fuera del grupo
   sin que nada lo señalara.
2. **Reglas duplicadas fusionadas.** El R daba **dos nombres canónicos distintos** a Radio y TV de
   Hidalgo según cómo viniera escrita. Igual con EyPME.
3. **El acrónimo final se quita** (ver abajo).

**La fuente dejó de escribir el acrónimo en 2024.** Hasta 2023: `INSTITUTO MEXICANO DEL SEGURO
SOCIAL (IMSS)`; desde 2024: sin el paréntesis. **109 instituciones quedaban partidas en dos** y
cualquier serie por institución se rompía justo en 2024, en silencio. Corregido con una regla que
quita el paréntesis final (279 instituciones canónicas en vez de 366). Las siglas no se pierden:
`reporte.py` las extrae de los nombres crudos y las indexa aparte para el buscador.
⚠ La regla es **solo para instituciones**: en beneficiarios el paréntesis suele traer la marca.

**Dos reglas heredadas siguen sobre-incluyentes:**

- **`imagen|image`** agrupa 58 razones sociales y **50 RFC distintos**, 3,936 MDP. Solo ~2,408 son
  inequívocamente Grupo Imagen. **La cifra está inflada hasta 39%.** Dos casos valen 1,401 MDP:

  | RFC | razón social | MDP | años |
  |---|---|---:|---|
  | `CSI0508264PA0` | COMERCIALIZADORA DE SERVICIOS IMAGEN | 911.7 | 2012–2016 |
  | `ISI050826EQ50` | IMAGEN SOLUCIONES INTEGRALES | 489.5 | 2012–2016 |

  Ambos RFC codifican la misma fecha de constitución (26-ago-2005), así que son hermanas. Pero son
  anteriores a las entidades actuales del grupo y **el dataset no permite decidir** si pertenecen.
  Se resuelve consultando esos dos RFC en el registro corporativo.
- **`sociedad mexicana`** se traga `SOCIEDAD MEXICANA DE FÍSICA` y `...DE INGENIERÍA BIOMÉDICA
  (CINVESTAV)`. 8 renglones, monto marginal, mal clasificados.

`isa ` e `imu` se acotaron con límites de palabra y **sí** están limpias: capturan exactamente las
5 empresas del grupo ISA y la única Comercializadora IMU.

### 3.6 El deflactor fue REVISADO, no solo extendido

`config/deflactor.csv` viene de la [Nota Metodológica 2025 de
FUNDAR](https://fundar.org.mx/wp-content/uploads/2025/09/Nota_Metodologica_2025.pdf) y
**reemplaza por completo** la versión 2023-2024 del pipeline en R (en `legacy/inputs/`):

| año | versión vieja | versión 2025 |
|-----|--------------:|-------------:|
| 2012 | 71.545207 | 70.335125 |
| 2018 | 92.254262 | 91.643434 |
| 2023 | 118.474246 | 116.653616 |

**No mezcles las dos versiones.** Por eso las cifras reales de este handoff no coinciden con las
del trabajo original en R — es correcto, no un error.

Dos advertencias: **2025 y 2026 son estimados** (columna `estimado` del CSV), y **la tabla
publicada tiene un typo** — el último renglón dice `2006/e` pero es 2026, y así se registró.

### 3.7 Validación contra fuente externa

`referencias/A19_2025_PublicidadOficial2024.pdf` — ARTICLE 19 + Política Colectiva, oct-2025.
Mismas partidas, mismo sistema, pero citando los **reportes agregados** oficiales en vez del
detalle de pólizas. Es la única verificación contra una fuente independiente, y corre en cada
`comsoc.build`.

Las **tasas de crecimiento real coinciden al decimal** — la prueba fuerte, porque no dependen del
deflactor. En niveles, reescalado al deflactor de A19: 0.00% de diferencia en 2018, 2019, 2020,
2021 y 2024; ≤0.20% en 2022–2023, justo en los años donde nuestra propia reconciliación
factura↔renglón detecta descuadres **de la fuente**. Detalle en `referencias/README.md`.

⚠ A19 cubre además el gasto de los 32 estados. **Este proyecto es solo federal.**

### 3.8 Reporte publicable (`reporte.py`)

`python -m comsoc.reporte` genera **`docs/index.html`**: 692 KB, **179 KB con gzip**, sin CDN ni
webfont ni script remoto. La única URL del archivo es el namespace XML de SVG. Se abre con doble
clic o se publica tal cual.

Contiene, en orden:

- **Barras** de la serie anual deflactada, con los sexenios marcados; clic fija el año.
- **Dos treemaps** a ancho completo (1000×470), 30 entidades con cuadro propio y la cola partida
  en tramos de posición marcados con trama diagonal. Sin partir, ese "Otros" valía **21%–39%**
  del año en empresas; ahora el bloque mayor es 19.7%.
- **Portadas** de las dos vistas de pantalla completa, con miniatura del treemap.
- **Medios en el tiempo**: nueve líneas en un plano, con crosshair (§3.13 y §3.15).
- **Campañas**: treemap por año, rampa verde azulada. Solo 2024–2025, y se dice por qué.
- **Concentración de proveedores**: barras ordenadas de la institución más concentrada a la
  menos, con selector de medida (1, 3 o 5 proveedores mayores), umbral y año.
- **Buscador** de las 13,894 combinaciones entidad×año, insensible a acentos y con alias.
- **Descargas** del dataset completo, con el diccionario de las 58 columnas.

**Aclaración importante del buscador:** el monto es **erogado** en los renglones de institución y
**recibido** en los de empresa — las dos caras del mismo peso. El contador los suma por separado;
sumarlos juntos daría 194,180 MDP, exactamente el doble del real.

**Autoría: Manuel Toral.** En `<meta name="author">`, la cabecera, el pie de fuente y **dentro de
cada SVG**, para que sobreviva a capturas y recortes.

Paleta verificada con el validador del skill `dataviz` (portado a Python porque no hay node):
rampa `#FB7EBC → #F62477 → #C4104F → #92003A`, ΔL 0.116 / 0.108 / 0.107 sobre el piso ordinal de
0.06. `#FFADEE` (L 0.85) y `#FFE185` (L 0.92) están muy por encima de la banda para ser marcas:
se usan solo como fondo y realce. Tema único claro sobre crema `#FBF5E6`, deliberado.

### 3.9 Treemaps con zoom (`zoom.py`) — dos vistas

`python -m comsoc.zoom` genera **dos** páginas independientes del reporte, desde el mismo código
parametrizado por el diccionario `VISTAS`:

| página | nivel 0 → nivel 1 | peso | gzip |
|---|---|---:|---:|
| `quien-paga-a-quien.html` | institución → empresas | 1,145 KB | 269 KB |
| `medios.html` | **medio de comunicación** → producto | 575 KB | 155 KB |

En `medios.html` cada caja del nivel 0 es una **empresa** —Televisa 14,958 MDP, TV Azteca 12,171,
La Jornada 2,110— y al abrirla se ve qué le vendió al gobierno. Ahí salta un contraste de modelo
de negocio: **TV Azteca vendió 27 productos distintos y Televisa solo 11**, con más dinero.

Cada caja se abre al darle clic y los hijos **crecen desde esa misma caja** hasta llenar el lienzo.

La animación interpola las coordenadas de cada celda en vez de aplicar un `transform` al grupo:
así el texto no se deforma al escalar y no depende de cómo cada navegador resuelva
`transform-box` en SVG. Al volver, las instituciones se despliegan desde la caja donde estabas.

Lleva el cruce **completo** institución × empresa × año: 45,763 tripletas, 1,122 KB / **257 KB con
gzip**. No se recorta la cola porque es justo lo que hace interesante el zoom — el IMSS le pagó a
**705 empresas distintas**.

Se descartan 785 pares por debajo de 10 mil pesos (1.7 MDP de 97,090, un 0.0018%): al redondear a
2 decimales quedaban en 0.00 y una celda de área cero hace dividir entre cero al squarify.

Geometría verificada con los datos reales: 15 layouts de instituciones × 4 tamaños de pantalla y
2,057 de empresas × 2, **sin un solo desborde ni traslape**.

### 3.10 Publicación del dataset

`export.publicar_descargas()` escribe en `docs/datos/` y el reporte los enlaza:

| archivo | tamaño |
|---|---:|
| `comsoc_polizas_csv.zip` | 15.7 MB |
| `comsoc_polizas.parquet` (zstd) | 11.7 MB |

Las 58 columnas completas, con **diccionario de las 58** agrupado por tema en el reporte.
El CSV lleva **BOM y entrecomillado con comillas duplicadas**: sin eso Excel en Windows rompe los
acentos y parte las columnas en nombres con coma («DEMOS, DESARROLLO DE MEDIOS»).

⚠ **ZIP y no GZIP.** Se publicó primero como `.csv.gz` y el usuario reportó que «no servía».
La descarga funcionaba —Pages entregaba un gzip válido— pero **Windows no abre `.gz` con doble
clic** ni Excel lo reconoce. Pesan casi lo mismo. *Lección: que el archivo llegue no significa
que se pueda usar.*

Un tercer botón genera el resumen por entidad y año en el navegador, sin peso extra.

⚠ El repo pesa ~31 MB con estos archivos. Si crece demasiado con las actualizaciones anuales,
moverlos a un Release de GitHub.

### 3.11 El buscador necesita alias, no solo el nombre canónico

Los dos buscadores compartían un fallo: **la homologación borra justo lo que la gente teclea.**
Quita el acrónimo, así que `imss` ya no aparecía en «INSTITUTO MEXICANO DEL SEGURO SOCIAL»; y
renombra, así que «LOTERÍA NACIONAL» quedó como `LOTENAL` y buscar «lotería» daba cero.

`reporte.alias_busqueda()` indexa, por nombre canónico, las palabras de sus nombres crudos que no
estén ya en el canónico. No se muestran, solo se buscan. Lo usan las dos páginas.

*Lección: cada vez que se agregue una regla de homologación hay que preguntarse si borra un
término por el que alguien buscaría.*

### 3.12 El texto «&lt;NA&gt;» publicado como si fuera un dato

**176,153 filas llevaban la cadena literal `"<NA>"`** en `campana_nombre`, y el mismo texto
aparecía en 16 columnas más. Se publicó así en el CSV descargable durante varios commits.

Origen: `astype(str)` sobre un nulo de pandas produce la cadena `"<NA>"`, y la lista de
reemplazos de `normalizar_llaves` solo contemplaba `"nan"`, `"None"` y `""`.

Corregido con `clean.barrer_nulos_de_texto`, que barre **todas** las columnas de texto —no solo
las conocidas— contra `BASURA_NULA`. Verificado: 0 casos.

*Lección: el bug no estaba en la columna que se estaba tocando, sino en las quince que nadie
miraba. Cuando se normaliza texto, la pasada tiene que ser sobre todo el ancho de la tabla.*

### 3.13 Medios: el catálogo está en la clave, no en el texto

`config/medios.csv` mapea las 37 `producto_clave` a **9 familias** (Televisión, Radio, Diarios,
Internet, Exterior, Revistas, Cine, Producción y servicios, Otros) y a un nombre limpio de
producto. Produce `medio_familia` y `medio_producto`.

Se deriva de la **clave** y no de `producto_desc` ni de `clase_medio` por dos razones medidas:
la clave está completa en los 14 años y solo tiene 37 valores, mientras `producto_desc` trae
ruido de captura —la clave 21 aparece con **17 redacciones distintas**— y `clase_medio` solo
existe en 2024–2025.

Verificado: las 9 familias suman el total de cada año con 0.20 MDP de diferencia máxima, y no
queda ninguna fila «Sin clasificar».

**Lo que muestra**, en % del gasto del año:

| familia | 2012 | 2025 | |
|---|---:|---:|---|
| Televisión | 35.7% | 17.8% | **−17.9 pp** |
| Internet | 4.3% | 26.7% | **+22.5 pp** |
| Diarios | 9.3% | 20.8% | +11.6 pp |
| Exterior | 5.9% | 0.7% | −5.2 pp |

Internet pasó de marginal a segundo medio y casi alcanza a la televisión.

### 3.14 Las tres rampas y por qué son tres

Cada jerarquía tiene su familia de color, para que el cambio de nivel se note:

| uso | rampa | ΔL entre pasos | paso claro |
|---|---|---|---|
| instituciones, barras | `#FB7EBC → #92003A` | 0.116 / 0.108 / 0.107 | 2.19 |
| empresas | `#D8930F → #7A4A02` | 0.088 / 0.091 / 0.081 | 2.38 |
| campañas | `#4FB8A3 → #0C4E45` | 0.082 / 0.122 / 0.128 | 2.35 |

Todas pasan el criterio ordinal (ΔL ≥ 0.06, paso más claro ≥ 2.0 de contraste sobre el fondo
crema). El ámbar se eligió sobre ciruela y verde azulado por ser la más separable del rosa
(ΔE 14.9 normal, 5.5 bajo daltonismo, contra 9.7 de la ciruela).

### 3.15 Nueve series no llevan nueve colores

La gráfica de medios en el tiempo son **nueve líneas en un mismo plano**, y ninguna tiene color
propio. No es pereza: se probó una paleta categórica de nueve y falla medido.

| par | ΔE normal | ΔE daltonismo | piso |
|---|---:|---:|---|
| `#F62477 / #2E9E8B` | 34.2 | **5.3** | 6.0 |
| `#92003A / #7A4A02` | 14.9 | **6.0** | 6.0 |
| `#7A4A02 / #8A6A1F` | **9.3** | 8.7 | 15.0 |

Solución: las líneas van en un tono neutro, **la identidad la dan las etiquetas al final** de cada
línea —con su valor, y separadas con un empuje mínimo de 15 px para que no se encimen— y el acento
solo marca la línea que el cursor está señalando. El crosshair muestra los nueve valores del año
ordenados de mayor a menor.

*Si alguien quiere «arreglarlo» poniendo nueve colores: ya se midió, no se puede. Con ocho series
o menos sí; con nueve, la identidad tiene que venir de otro canal.*

### 3.16 Entorno: conda local

Se descartó Colab. Todo corre en local sobre **`pnt_analysis`**, environment **reutilizado** de
otro proyecto del mismo dominio: Python 3.12.3, pandas 2.2.2, pyarrow 16.1, plotnine 0.13.6,
networkx, scipy, matplotlib, ipykernel. Se le agregaron `openpyxl`, `pyyaml` y `rapidfuzz`.

Intérprete: `C:\Users\User\anaconda3\envs\pnt_analysis\python.exe`. `conda` no está en el PATH.
Correr siempre con `-X utf8`.

### 3.17 Código

`src/comsoc/`: `config`, `layouts`, `schema`, `ingest`, `clean`, `entities`, `ids`, `deflate`,
`validate`, `export`, `reporte`, `zoom`, `build`.
`config/`: `layouts.yaml`, `columnas.yaml`, `beneficiarios_map.csv`, `instituciones_map.csv`,
`medios.csv`, `deflactor.csv`, `fechas_corruptas.yaml`.

El sitio se regenera con tres comandos:

```powershell
& $py -X utf8 -m comsoc.build       # Excel -> parquet
& $py -X utf8 -m comsoc.reporte     # parquet -> docs/index.html
& $py -X utf8 -m comsoc.zoom        # parquet -> las dos vistas de pantalla completa
& $py -X utf8 -c "from comsoc import export; export.publicar_descargas()"
```
Más `pyproject.toml`, `.gitignore`, `README.md`, `notebooks/00_construir_dataset.ipynb`,
`referencias/` y los 3 skills en `.claude/skills/`.

Todo lo viejo se **movió, nada se borró**: el proyecto en R está íntegro en `legacy/`, más
`legacy/diagnostico/` con los 7 scripts que produjeron el diagnóstico.

---

## 4. Bugs encontrados y corregidos

1. `fecha_gasto` mezclaba seriales y texto en columna `object`; pyarrow no podía inferir el tipo.
   → `ingest._a_texto`.
2. Columnas ausentes creadas como `object` todo-NA: el `concat` las descartaba al inferir tipos.
   → dtype explícito (`np.nan` numéricas, `pd.NA` texto).
3. La reconciliación factura/renglón no separaba por `vintage` y mezclaba las dos ediciones de 2023.
4. Una fecha en 2047 sobrevivía a la reparación. → agregada a `desfase_anios`.
5. **El peor: la regla `2026 → 2016` heredada del R arruinaba 1,003 filas de 2025.** En los archivos
   viejos una fecha de 2026 es un typo; en el de 2025 es legítima (su corte es junio de 2026).
   Ahora `parsear_fechas` recibe `anio_fuente` y solo corrige si el resultado queda más cerca del
   ejercicio. Fechas fuera de rango: 1,057 → 107.
   *Lección: toda regla heredada del R está calibrada para 2012–2023 y hay que acotarla antes de
   aplicarla a los años nuevos.*
6. La deflactación cruzaba por `anio` (con basura como 2001 y 2055) en vez de `anio_fuente`.
7. El contador del buscador sumaba instituciones y empresas juntas: mostraba el doble del real.
8. **176,153 filas con el texto literal `"<NA>"` como si fuera un dato**, publicado en el CSV
   descargable. `astype(str)` sobre un nulo de pandas produce esa cadena. Ver §3.12.
9. Los dos buscadores no encontraban `imss` ni `lotería`: la homologación borra justo lo que la
   gente teclea. Ver §3.11.
10. El CSV se publicó como `.csv.gz`, que Windows no abre con doble clic. Ver §3.10.

---

## 5. Pendientes, en orden

| # | Pendiente | Nota |
|---|---|---|
| 1 | **Fase 6 — análisis** | Parcialmente hecho: el reporte ya cubre serie, medios en el tiempo, campañas y concentración. Faltan el ciclo electoral, la red institución↔beneficiario y las anomalías de precio. Las 7 preguntas están en el skill `comsoc-analisis`. |
| 2 | **Verificar 2 RFC de Imagen** | `CSI0508264PA0` y `ISI050826EQ50`. Cinco minutos de consulta deciden 1,401 MDP y si la cifra de Imagen está inflada 39%. |
| 3 | **Fase 5 — hojas `Ejercido`** | Declaradas en `layouts.yaml`, sin lector. Falta tabla puente institución↔clave (no traen clave, ~120 por año). Permitiría cruzar presupuesto autorizado contra pagado. |
| 4 | **Cola larga de beneficiarios** | Catálogo `RFC → canónico` con 2012–2016 + 2024–2025, y `rapidfuzz` para el hueco 2017–2023. Hoy 4,955 nombres crudos → 4,719 canónicos: las reglas apenas tocan 236. |
| 5 | **Tests** | `tests/` está vacío. Invariantes obvios: complementariedad de niveles, mapeo de columnas por generación, parser dual de fechas, unicidad de `renglon_id`. |

---

## 6. Decisiones tomadas

| Decisión | Resuelto |
|---|---|
| 2023 duplicado | Definitiva canónica; preliminar conservada como `vintage` |
| Nivel de registro | Renglón (único que sobrevive en 2024–2025) |
| Reversas | Se suman con signo |
| Duplicados exactos | No se deduplican; se marcan con `n_identicas` |
| Serie principal | 33605 separada de 36101-36201, más el total |
| Año de agrupación | `anio_fuente`, no `anio` |
| Base del deflactor | 2020=100 |
| Intercambios en especie | Excluidos del gasto, reportados aparte |
| pandas vs polars | pandas — 250k filas no justifican reaprender la API |
| Tema del reporte | Claro único sobre crema; sin modo oscuro, deliberado |

## 7. Abiertas

- ¿Extender la serie antes de 2012? (Recomendación: no en la v1.)
- ¿Scraper del portal para no depender de descargas manuales? (Vale la pena solo si actualizas por
  trimestre; si es anual, la descarga manual está bien.)
