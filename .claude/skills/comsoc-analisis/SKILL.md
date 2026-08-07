---
name: comsoc-analisis
description: Convenciones obligatorias para analizar el dataset COMSOC de publicidad oficial — qué filas incluir, qué columna de dinero usar, cómo comparar entre años y qué preguntas de investigación están planeadas. Úsalo antes de escribir cualquier agregación, gráfica o cifra publicable sobre el gasto en publicidad oficial. Palabras clave: analizar gasto, serie anual, beneficiarios, concentración, red, deflactar, gráfica, ranking, hallazgo.
---

# Análisis del dataset COMSOC

## El filtro base (no negociable)

Toda cifra publicable parte de aquí:

```python
import pandas as pd
from comsoc.config import POLIZAS_PARQUET

df = pd.read_parquet(POLIZAS_PARQUET)

base = df[
    (df["nivel_registro"] == "renglon")   # ver "las tres trampas" abajo
    & (df["vintage"] == "definitiva")     # excluye la edición preliminar de 2023
]
```

Si tu número no lleva estos dos filtros, está mal. `build.construir()` ya aplica el primero al
guardar, pero verifícalo: es el error que duplica el gasto al 200%.

## Qué columna de dinero

| Columna | Qué es | Cuándo |
|---|---|---|
| `monto` | pago al proveedor, sin IVA | comparar precios unitarios |
| `iva` | IVA del renglón | rara vez sola |
| **`monto_total`** | `monto + iva` | **el gasto. Es la de referencia** |
| `monto_real` | `monto_total` deflactado | **toda comparación entre años** |
| `importe_factura` | nivel factura, solo G1 | **nunca** en el dataset canónico; solo reconciliación |

**Nunca compares años en pesos nominales.** El deflactor está en `config/deflactor.csv`
(implícito del PIB, base 2020=100, FUNDAR Nota Metodológica 2025, serie 1993–2026 completa).
Declara siempre el año base en el subtítulo de la gráfica.

⚠ **2025 y 2026 usan deflactor estimado** (`deflactor_estimado == 1`). Si tu gráfica los incluye,
dilo en la nota al pie. Y ojo: esta serie **fue revisada** respecto de la que usaba el pipeline
en R, así que las cifras reales no coinciden con el trabajo original — es correcto, no un error.

## Decisiones que hay que tomar explícitamente

No hay respuesta por defecto correcta; elige y **dilo en la nota al pie**:

- **`es_intercambio`** — publicidad pagada en especie, no en dinero. Recomendado: excluir de
  "gasto" y reportar aparte.
- **`es_reversa`** — contra-asientos con monto negativo. **Súmalos con signo**; excluirlos infla
  el total. Son ≤1.23% (2012) y ~0% desde 2016.
- **`n_identicas > 1`** — 9,036 filas del histórico están exactamente duplicadas y no se sabe si
  son error de captura o inserciones repetidas legítimas. **No deduplicar por defecto**; correr
  el análisis con y sin ellas como test de sensibilidad.
- **`fecha_fuera_de_rango`** — fechas que no caen en su año fuente. Marcadas, no corregidas.
- **`33605` vs `36101-36201`** — naturaleza distinta (operación vs. campaña). Repórtalas
  **separadas y en total**, nunca mezcladas sin decirlo. Usa `partida_grupo`.

## Identificadores

- **`poliza_id`** — la póliza (documento contable). Agrupa sus renglones.
- **`renglon_id`** — la fila. Único en todo el dataset; úsalo como llave al unir tablas.
- **`n_renglones`** — cuántos renglones tiene la póliza de esa fila.

Son hash del contenido: estables entre corridas. **No** uses `fila_num` (el `Núm.` de 2025) como
identificador — es un índice de reporte y cambia con cada republicación.

`poliza_id` es estable entre `vintage`, así que `ids.comparar_vintages(df)` da directamente la
pregunta 6 de abajo. Requiere cargar con `incluir_preliminares=True`.

Para analizar a nivel póliza en vez de renglón, agrega **siempre** desde los renglones:

```python
por_poliza = (base
    .groupby(['poliza_id', 'anio_fuente', 'partida_grupo',
              'clave_entidad', 'institucion'], as_index=False)
    .agg(renglones=('renglon_id', 'size'),
         monto_total=('monto_total', 'sum'),
         beneficiarios=('beneficiario', 'nunique')))
```

Media de 1.8 renglones por póliza, máximo 432. Contar pólizas y contar renglones dan respuestas
muy distintas: di cuál estás usando.

## ⚠ Este dataset es SOLO federal

Los 32 estados gastan **más** que la federación y no están aquí: pasaron de 47.2% del total
nacional en 2018 a **71.9% en 2024** (ARTICLE 19, ver `referencias/`). Nunca escribas "el gasto
en publicidad oficial en México" a secas — di **federal**, o te quedas con menos de un tercio.

La serie federal está validada contra ARTICLE 19 para 2018–2024: las tasas de crecimiento real
coinciden al decimal. Si tu cifra federal se aleja >0.5% de `validate.A19_FEDERAL_MDP_2025`,
algo se rompió.

## Año de la serie

Usa **`anio_fuente`** (el ejercicio que reporta el archivo), no `anio` (derivado de
`fecha_gasto`). Hay pagos registrados con fecha del año anterior o siguiente; agrupar por `anio`
reparte gasto a años que la fuente no reporta y tu total deja de cuadrar con el oficial.

## Beneficiarios

Usa **`beneficiario_canonico`** e **`institucion_canonica`**, no los campos crudos. Las reglas
están en `config/beneficiarios_map.csv` (37) y `config/instituciones_map.csv` (22), portadas del
proyecto en R. Gana la primera regla que coincide; el match ignora acentos.

**Cobertura: 63.1% del gasto** (beneficiarios) y 33.2% (instituciones). El resto cae a un
Title Case que **no agrupa** razones sociales de un mismo grupo. Para un top-10 alcanza; para
afirmar "el grupo X recibió N", verifica que X tenga regla.

⚠ **Dos reglas heredadas están sobre-incluyentes. Audítalas antes de citarlas:**

- **`Imagen`** agrupa 58 razones sociales y 50 RFC distintos (3,936 MDP). Solo ~2,408 MDP son
  claramente Grupo Imagen; el resto entró por tener "imagen" en el nombre
  (`ESPECIALISTA EN IMAGEN PUBLICA`, `IMAGENAGROPECUARIA.COM.MX`). **La cifra de Imagen está
  inflada hasta 39%.**
- **`Soc. Mex. de la Radio`** se traga `SOCIEDAD MEXICANA DE FÍSICA` y
  `...DE INGENIERÍA BIOMÉDICA (CINVESTAV)`.

**`rfc_beneficiario` es la llave dura** y existe en **2012–2016 y 2024–2025**. Úsalo para
resolver cualquier duda de agrupación; el hueco 2017–2023 se puentea por nombre.

No inventes agrupaciones nuevas sin dejarlas en el CSV: si no es reproducible, no es citable.

## Preguntas planeadas (Fase 6)

1. **Ciclo electoral** — gasto mensual real contra el calendario (2012, 2015, 2018, 2021, 2024).
   ¿Hay pico sistemático antes de la veda? Ruptura estructural en dic-2018 y oct-2024.
2. **Concentración** — HHI anual por beneficiario, participación del top-10, curva de Lorenz.
3. **Migración a 33605** — hipótesis: al recortarse 36101 (campañas, con escrutinio) sube 33605
   (operación). Ratio por institución y año.
4. **Red institución ↔ beneficiario** — grafo bipartito, comunidades, y **proveedores cautivos**
   (≥90% de su ingreso de una sola institución).
5. **Anomalías de precio** — mismo `producto_clave` + `unidad` + mes con `costo_unitario` muy
   dispar entre instituciones. Complementar con Benford sobre `monto`.
6. **Vintage 2023** — qué instituciones aparecen solo en la definitiva (medida de opacidad del
   reporte preliminar). Requiere cargar con `incluir_preliminares=True`.
7. **Presupuesto vs. pagado** (2024–2025) — quién amplía a mitad de año y quién subejerce.
   Requiere la Fase 5 (hojas `Ejercido`), aún pendiente.

## Gráficas

`plotnine` es ggplot2 en Python: las del proyecto original se portan casi literalmente desde
[`legacy/R/3_analysis_and_vizes.R`](legacy/R/3_analysis_and_vizes.R). Los bump charts usaban
`ggbump`, que no tiene equivalente directo — hay que rehacerlos a mano.

Antes de escribir código de gráficas, **carga el skill `dataviz`**.

Pie de fuente sugerido:

> Fuente: Sistema COMSOC, Secretaría Anticorrupción y Buen Gobierno.
> Pesos constantes de {base}. {Nota sobre cifras preliminares si aplica.}

## Las tres trampas

Están documentadas en `CLAUDE.md` y en `PLAN_MIGRACION.md` §1.6. Si vas a tocar cifras, léelas.
La primera duplica el gasto al 200% y no produce ningún error: solo un número mal.
