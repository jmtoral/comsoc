# Referencias

Documentos **externos** usados como fuente o contraste. No los genera el pipeline
(para eso está `reports/`) ni son insumos de configuración (para eso, `config/`).

---

## `A19_2025_PublicidadOficial2024.pdf`

**Publicidad Oficial 2024: Los estados concentran la mayor parte del gasto nacional**
ARTICLE 19 México y Centroamérica + Política Colectiva, octubre de 2025. 20 pp.

Analiza las mismas partidas que este proyecto (**36101, 36201 y 33605**) del mismo sistema
COMSOC, más el gasto de los 32 estados (concepto 3600 de las Cuentas Públicas estatales, que
está **fuera** del alcance de este proyecto: aquí solo hay federal).

Sirve como **la única verificación contra una fuente independiente**. Sus cifras federales están
codificadas en `validate.A19_FEDERAL_MDP_2025` y el contraste corre en cada `comsoc.build`.

### Resultado del contraste (2018–2024)

**Las tasas de crecimiento real coinciden al decimal**, que es la prueba fuerte: no dependen del
deflactor elegido, así que un desajuste significaría datos distintos.

| | nuestro | A19 |
|---|---:|---:|
| 2019 vs 2018 | −67.3% | −67.3% |
| 2024 vs 2023 | +39.9% | +39.9% |
| 2024 vs 2018 | −70.7% | −70.7% |

En niveles, una vez reescalado al deflactor de A19, la diferencia es **0.00% en 2018, 2019, 2020,
2021 y 2024**, y ≤0.20% en 2022–2023.

### Dos diferencias, ambas explicadas

**1. Deflactor de 2025 (0.77%, uniforme).** A19 usa un factor implícito de **128.738**; nosotros
127.759 (FUNDAR, Nota Metodológica 2025). Ambos son **estimados** de un año que no ha cerrado.
Por eso los niveles nominales difieren 0.77% de forma constante y las tasas no difieren en nada.

**2. Nivel de agregación (≤0.20%, solo 2021–2023).** A19 cita los reportes agregados de
*Estrategia de comunicación social*; nosotros sumamos el **detalle de pólizas**. Los residuos
caen exactamente en los años donde nuestra propia reconciliación factura↔renglón detecta
descuadres en la fuente:

| año | nuestro (renglón) | nuestro (factura) | A19 |
|-----|------------------:|------------------:|----:|
| 2021 | **2,839.86** | 2,836.83 | 2,839.85 |
| 2022 | 2,802.93 | **2,808.61** | 2,808.60 |
| 2023 | 2,712.45 | **2,713.71** | 2,713.74 |

A19 coincide en cada año con el mayor de los dos niveles, que es lo esperable si la cifra
agregada oficial incluye facturas cuyo desglose por renglón está incompleto en el Excel.
Es el mismo descuadre de ≤0.21% documentado en `PLAN_MIGRACION.md` §1.6 — no es un error
nuestro ni de ellos, es de la fuente.

### Conclusión

El pipeline reproduce, desde el detalle transaccional, las cifras que una organización
independiente obtiene de los agregados oficiales. **Las dos rutas se validan mutuamente.**

### Contexto que aporta y este proyecto no cubre

El informe documenta que el gasto **estatal** pasó de 47.2% del total nacional en 2018 a 71.9%
en 2024, y que los estados llevan desde 2020 concentrando más del 75%. Este proyecto solo cubre
el gasto federal: cualquier afirmación sobre "el gasto en publicidad oficial en México" sin
matizar que es federal se queda con menos de un tercio del total.

Fuente citada por A19 para lo federal:
<https://www.gob.mx/buengobierno/documentos/estrategia-de-comunicacion-social>

---

## `Nota_Metodologica_2025` (FUNDAR) — pendiente de archivar

El deflactor de `config/deflactor.csv` viene de
<https://fundar.org.mx/wp-content/uploads/2025/09/Nota_Metodologica_2025.pdf>.
Conviene guardar el PDF aquí para que el proyecto no dependa de que la URL siga viva.
