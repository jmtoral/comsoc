---
name: comsoc-nuevo-anio
description: Da de alta un archivo COMSOC nuevo (o una re-descarga) en el pipeline sin romper la serie 2012-2025. Úsalo cuando la Secretaría Anticorrupción publique el ejercicio de un año nuevo, cuando aparezca una edición definitiva que sustituya a una preliminar, o cuando el pipeline falle con un archivo que antes leía bien. Palabras clave: agregar año, nuevo archivo, 2026, actualizar dataset, layouts.yaml, edición definitiva.
---

# Alta de un año nuevo en el pipeline COMSOC

El formato ha cambiado dos veces en cuatro años y la fila de encabezado se ha movido
6 → 7 → 8 → 9 → 10 → 13. **Asume que este archivo también cambió.** El objetivo de este
procedimiento es que el cambio se declare en `config/` y no toque el código.

## 0. Nunca sobrescribas

Coloca el archivo en `data/raw/` con su nombre original. Si ya existe otro del mismo año, **no
lo reemplaces**: las dos ediciones conviven y se distinguen por `vintage` en `layouts.yaml`.
La diferencia entre preliminar y definitiva es en sí un objeto de análisis (en 2023 fue +43%
de registros).

## 1. Sondear

Usa el skill `comsoc-sondeo-xlsx`. No sigas hasta tener, **por hoja**:
nombre, tipo (`polizas` / `ejercido`), grupo de partida, fila del encabezado, lista de columnas
y número de filas.

## 2. Declarar en `config/layouts.yaml`

```yaml
  - archivo: NOMBRE_EXACTO_DEL_ARCHIVO.xlsx
    anio: 2026
    generacion: G4          # generación nueva si las columnas cambiaron
    vintage: definitiva     # o 'preliminar' si dice "Cifras preliminares"
    control:                # si el archivo incrusta sus propios totales, cópialos
      "36101-36201": {monto: 0.0, iva: 0.0}
    hojas:
      - {indice: 1, nombre: "...", tipo: ejercido, partida_grupo: "36101-36201", header_row: 10}
      - {indice: 2, nombre: "...", tipo: polizas,  partida_grupo: "36101-36201", header_row: 13}
```

`header_row` es una **aserción**, no el mecanismo: el lector detecta el encabezado solo y avisa
si difiere. Ponlo igual a lo que viste; si el aviso salta después, actualiza el YAML.

## 3. Mapear columnas en `config/columnas.yaml`

Solo si el layout cambió. Crea un bloque de generación nueva heredando el ancla `comun`:

```yaml
G4:
  <<: *comun
  <nombre normalizado en el excel>: <nombre canónico>
```

Las llaves van **normalizadas**: minúsculas, sin acentos, sin puntuación, espacios simples
(`"Descripción De La Unidad"` → `descripcion de la unidad`). Ver `schema.normalizar_nombre`.

**Antes de mapear una columna por su nombre, mira sus valores.** Dos columnas se han renombrado
conservando el nombre y cambiando el significado:

| Columna | Significado viejo | Significado nuevo |
|---|---|---|
| `IVA` | IVA de la factura (G1) | IVA del renglón (G2/G3) |
| `Clase de Beneficiario` | código `P`/`R` (G1) | tipo de medio (G2) |

Si una columna nueva no existe en el esquema canónico, agrégala a `COLUMNAS_CANONICAS` en
`src/comsoc/schema.py` — el lector descarta lo que no esté ahí.

## 4. Deflactor

`config/deflactor.csv` llega a **2024**. Si el año nuevo no está, agrégalo (deflactor implícito
del PIB, base 2020=100, fuente FUNDAR/SHCP) o el pipeline fallará explícitamente. Eso es
deliberado: es preferible a `NaN` silenciosos en el año más reciente.

## 5. Correr y leer las tres pruebas

```bash
python -m comsoc.build
```

- **Factura vs. renglón** — solo aplica a G1. Debe cuadrar dentro de 0.25%.
- **Totales históricos** — no debe moverse ni un peso al agregar un año nuevo.
  Si se movió, rompiste algo aguas arriba.
- **Cifra de control** — si el archivo trae su propio total, debe cuadrar exacto.

Si el año nuevo trae control propio, agrégalo también a `validate.TOTALES_ESPERADOS_MDP` una vez
verificado, para que quede fijado contra regresiones.

## 6. Documentar

Actualiza en `PLAN_MIGRACION.md`: la tabla de generaciones (§1.1) y, si hubo campos nuevos o
que cambiaron de significado, el mapeo (§1.4). **La ficha metodológica es lo que hace el dataset
citable**; un cambio de formato sin documentar vale menos que no tener el año.

## Señales de alarma

| Síntoma | Causa probable |
|---|---|
| El total de un año viejo cambió | mapeo por posición, o filtro de `nivel_registro` roto |
| El total nuevo es ~2× lo esperado | se están sumando filas de factura Y de renglón |
| Muchos `[sin mapear]` en la ingesta | generación nueva no declarada en `columnas.yaml` |
| `No encontré el encabezado` | subir `MAX_FILAS_SONDEO`, o cambiaron las anclas `Sector`/`Póliza` |
| `partida` con valores de 4 dígitos | bug de la fuente (pasó en 2023); ver `clean.reparar_partida` |
