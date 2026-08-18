"""Genera el reporte interactivo como HTML autocontenido.

    python -m comsoc.reporte            -> docs/index.html (para GitHub Pages)
    python -m comsoc.reporte --fragmento -> docs/_fragmento.html (sin <html>/<head>)

El archivo no depende de nada externo: los datos van embebidos como JSON y no hay
CDN, webfont ni script remoto. Se puede abrir con doble clic o publicar tal cual.

Tema único claro sobre crema, por decisión: el reporte se publica y se imprime, y
un flip automático a oscuro cambiaría el sentido de la rampa secuencial.

Paleta, verificada con el validador del skill `dataviz`:

  fondo   #FBF5E6 crema · tarjeta #FFFCF4 · notas #FDF3DC
  acentos #F62477 (L 0.637, contraste 3.55) · #92003A (L 0.422, contraste 8.46)
  suaves  #FFADEE · #FFE185 — demasiado claros para ser marcas (L 0.85 y 0.92),
          se usan solo como fondo y realce, que es para lo que sirven
  rampa   #FB7EBC -> #F62477 -> #C4104F -> #92003A
          ordinal: dL = 0.116 / 0.108 / 0.107 (piso 0.06);
          paso mas claro a 2.19 de contraste sobre el fondo (piso 2.0)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DOCS_DIR, POLIZAS_PARQUET, asegurar_directorios
from .layouts import MESES, cargar_parciales

# Entidades con cuadro propio por año, y cortes para partir la cola.
#
# El resto NO se agrupa en un solo bloque opaco: se parte en tramos de posición.
# La cola de empresas es larguísima —al cortar en 30, "Otros" vale entre 21% y 39%
# del año, hasta 449 empresas en 2025— y un cuadro de ese tamaño esconde
# justamente lo que interesa ver. La de instituciones es corta (2%–10%), así que
# le basta un corte.
def _mdp(x: float) -> float:
    """Millones de pesos, con la precisión que corresponde a la magnitud.

    Redondear todo a 1 o 2 decimales convertía en 0 lo menor a 5,000 pesos ANTES de
    llegar al navegador, y el formateo de la página no puede recuperar lo que ya se
    perdió aquí. Pero seis decimales para todo es igual de absurdo al revés: guardar
    12,734.700000 pesa el doble y no aporta nada sobre 12,734.7.

    Se conservan siempre ~5 cifras significativas.
    """
    v = float(x) / 1e6
    a = abs(v)
    if a >= 100:
        return round(v, 1)
    if a >= 1:
        return round(v, 3)
    return round(v, 6)


PANELES = {
    "instituciones": {"campo": "institucion_canonica", "top": 30, "cortes": [60]},
    "beneficiarios": {"campo": "beneficiario_canonico", "top": 30, "cortes": [75, 150, 300]},
}


# ─────────────────────────────────────────────────────────────── datos

def alias_busqueda(b: pd.DataFrame, crudo: str, canonico: str) -> dict[str, str]:
    """Palabras extra para buscar una entidad por como se llama en la fuente.

    Hace falta porque la homologación borra justo lo que la gente teclea: quita el
    acrónimo final —así `imss` ya no aparece en «INSTITUTO MEXICANO DEL SEGURO
    SOCIAL»— y renombra —«LOTERÍA NACIONAL» quedó como `LOTENAL`, de modo que
    buscar «lotería» no encontraba nada.

    Devuelve, por nombre canónico, las palabras de sus nombres crudos que no estén
    ya en el canónico. No se muestran: solo se indexan.
    """
    from .entities import plegar

    out: dict[str, str] = {}
    for canon, grupo in b.groupby(canonico, observed=True)[crudo]:
        base = set(plegar(canon).lower().split())
        palabras: list[str] = []
        for valor in grupo.dropna().unique():
            for w in re.split(r"[^0-9a-z]+", plegar(str(valor)).lower()):
                if len(w) > 1 and w not in base and w not in palabras:
                    palabras.append(w)
        if palabras:
            out[canon] = " ".join(palabras)
    return out


def construir_datos(df: pd.DataFrame) -> dict:
    b = df[(df.vintage == "definitiva") & (~df.es_intercambio)]

    def treemap(campo: str, top: int, cortes: list[int]) -> dict:
        out = {}
        for anio, g in b.groupby("anio_fuente"):
            s = (g.groupby(campo)["monto_real"].sum() / 1e6).sort_values(ascending=False)
            s = s[s > 0]
            items = [{"n": str(k), "v": _mdp(v * 1e6)} for k, v in s.head(top).items()]

            # La cola se parte en tramos de posición en vez de un solo "Otros".
            for ini, fin in zip([top] + cortes, cortes + [len(s)]):
                tramo = s.iloc[ini:fin]
                if not len(tramo) or tramo.sum() <= 0:
                    continue
                items.append({
                    "n": f"{ini + 1}–{min(fin, len(s))}",
                    "v": _mdp(tramo.sum() * 1e6),
                    "grupo": int(len(tramo)),
                })

            out[str(int(anio))] = {"items": items, "total": _mdp(s.sum() * 1e6),
                                   "n_total": int(len(s))}
        return out

    a = b.groupby("anio_fuente").agg(real=("monto_real", "sum"), nominal=("monto_total", "sum"),
                                     obs=("renglon_id", "size"), polizas=("poliza_id", "nunique"))

    def sexenio(y):
        return "EPN" if y <= 2018 else ("AMLO" if y <= 2024 else "Sheinbaum")

    anios_serie = [int(y) for y in a.index]

    # Años que no cubren doce meses. 2026 llega a mayo: 97 MDP contra 4,346 de 2025.
    # Puesto junto sin marca se lee como desplome, y no lo es —el rango histórico de
    # enero-mayo va de 0.3% a 13.1% del año, y 2025 llevaba 139 MDP a la misma altura.
    # Se marca en la serie y se EXCLUYE de todo cálculo que compare años entre sí.
    parciales = cargar_parciales()
    anios_completos = [y for y in anios_serie if y not in parciales]

    serie = [{"anio": int(y), "real": round(float(r.real / 1e6), 1),
              "nominal": round(float(r.nominal / 1e6), 1), "obs": int(r.obs),
              "polizas": int(r.polizas), "sexenio": sexenio(y),
              **({"p": parciales[int(y)]} if int(y) in parciales else {})}
             for y, r in a.iterrows()]

    # Tabla buscable: un renglón por entidad y año, las dos dimensiones juntas.
    # Los nombres van en un diccionario aparte porque se repiten catorce veces;
    # sin eso el bloque pesa el triple.
    filas, nombres = [], set()
    for tipo, campo in ((0, "institucion_canonica"), (1, "beneficiario_canonico")):
        g = b.groupby(["anio_fuente", campo]).agg(
            real=("monto_real", "sum"), nominal=("monto_total", "sum"),
            pol=("poliza_id", "nunique"), ren=("renglon_id", "size")).reset_index()
        op = (b[b.partida_grupo == "33605"].groupby(["anio_fuente", campo])["monto_real"]
              .sum().rename("op").reset_index())
        g = g.merge(op, on=["anio_fuente", campo], how="left").fillna({"op": 0.0})
        for r in g.itertuples(index=False):
            nombres.add(r[1])
            filas.append((int(r.anio_fuente), tipo, r[1], _mdp(r.real),
                          _mdp(r.nominal), int(r.pol), int(r.ren), _mdp(r.op)))
    nom = sorted(nombres)
    ind = {n: i for i, n in enumerate(nom)}

    siglas = alias_busqueda(b, "institucion", "institucion_canonica")
    siglas.update(alias_busqueda(b, "beneficiario", "beneficiario_canonico"))
    alias = [siglas.get(n, "") for n in nom]

    tabla = {"nombres": nom, "alias": alias,
             "filas": [[f[0], f[1], ind[f[2]], f[3], f[4], f[5], f[6], f[7]] for f in filas]}

    # Concentración de proveedores por institución. Se precalcula porque hacerlo en
    # el navegador obligaría a embarcar el cruce completo institución x empresa.
    par = (b.groupby(["anio_fuente", "institucion_canonica", "beneficiario_canonico"],
                     observed=True)["monto_real"].sum())
    escenarios = {"": par.groupby(level=[1, 2]).sum()}
    for anio, g in par.groupby(level=0):
        escenarios[str(int(anio))] = g.droplevel(0)

    conc = {}
    for clave, serie_ in escenarios.items():
        filas_c = []
        for institucion, grupo in serie_.groupby(level=0):
            v = np.sort(grupo.to_numpy())[::-1]
            total = float(v.sum())
            if total <= 0:
                continue
            sh = v / total
            filas_c.append([ind[institucion], _mdp(total), int(len(v)),
                            round(100 * float(sh[0]), 1),
                            round(100 * float(sh[:3].sum()), 1),
                            round(100 * float(sh[:5].sum()), 1),
                            int(round(10000 * float((sh ** 2).sum())))])
        conc[clave] = filas_c

    # Medios por año: 9 familias x 14 años. Se manda la serie completa y el %
    # se calcula en el navegador.
    fam = (b.groupby(["medio_familia", "anio_fuente"], observed=True)["monto_real"].sum() / 1e6)
    orden_fam = (fam.groupby(level=0).sum().sort_values(ascending=False).index.tolist())
    medios = {"familias": orden_fam,
              "serie": {f: [round(float(fam.get((f, a), 0.0)), 1) for a in anios_serie]
                        for f in orden_fam}}

    # Ciclo electoral. Se compara cada año contra el PROMEDIO DE SUS VECINOS y no
    # contra el anterior: el nivel se desplomó 67% en 2019, así que una variación
    # interanual mezcla el ciclo con el cambio de régimen. El promedio de los dos
    # años contiguos controla ese desplazamiento.
    ELECCIONES = {2012: "presidencial", 2015: "intermedia", 2018: "presidencial",
                  2021: "intermedia", 2024: "presidencial"}
    # Sobre años completos: si 2026 (5 meses) entrara como vecino, 2025 se compararía
    # contra un promedio hundido y aparecería como un pico electoral inexistente.
    real = {int(y): float(v) for y, v in (a.real / 1e6).items() if int(y) in anios_completos}
    ciclo = []
    for y in anios_completos:
        prev, sig = real.get(y - 1), real.get(y + 1)
        vs = None
        if prev is not None and sig is not None:
            vs = round(100 * (real[y] / ((prev + sig) / 2) - 1), 1)
        ciclo.append({"anio": y, "mdp": round(real[y], 1), "vs": vs,
                      "tipo": ELECCIONES.get(y, "")})

    # Ganadores y perdedores. Se compara SEXENIO contra SEXENIO y no año contra año:
    # el cambio interanual mediano de participación es 0.021 pp, o sea que un ranking
    # anual mide sobre todo ruido. Y se compara PARTICIPACIÓN porque el gasto real
    # cayó 67% en 2019: en montos absolutos perdieron todos.
    # Tres periodos. Sheinbaum solo tiene 2025 completo en los datos: 2024 se
    # atribuye entero a AMLO porque nueve de sus doce meses corrieron bajo su
    # gobierno. La asimetría se advierte en la página.
    # Sobre años COMPLETOS: el promedio de participación pondera cada año igual, así
    # que 2026 —560 renglones, 78 empresas— pesaría lo mismo que un año de 15,000 y
    # le daría a Sheinbaum el perfil de cinco meses de una sola dependencia.
    SEXENIOS = [
        ("epn", "Peña Nieto", [a for a in anios_completos if 2013 <= a <= 2018]),
        ("amlo", "López Obrador", [a for a in anios_completos if 2019 <= a <= 2024]),
        ("sheinbaum", "Sheinbaum", [a for a in anios_completos if a >= 2025]),
    ]
    SEXENIOS = [(k, e, ys) for k, e, ys in SEXENIOS if ys]

    por_emp = (b.groupby(["anio_fuente", "beneficiario_canonico"], observed=True)["monto_real"]
               .sum().unstack(0).fillna(0.0) / 1e6)
    part = por_emp.div(por_emp.sum(axis=0), axis=1) * 100

    cols = {}
    for k, _, ys in SEXENIOS:
        cols[f"sh_{k}"] = part[ys].mean(axis=1)
        cols[f"mdp_{k}"] = por_emp[ys].mean(axis=1)
    gp = pd.DataFrame(cols)

    # Solo lo que puede llegar a mostrarse: el umbral más bajo de la vista es 0.05%
    claves = [k for k, _, _ in SEXENIOS]
    relevante = gp[[f"sh_{k}" for k in claves]].max(axis=1) >= 0.05
    gp = gp[relevante]

    ganperd = {
        "periodos": [{"clave": k, "etq": e, "anios": [ys[0], ys[-1]], "n": len(ys)}
                     for k, e, ys in SEXENIOS],
        "umbral": 0.25,
        "emp": [[ind.get(nombre, 0)]
                + [round(float(r[f"sh_{k}"]), 3) for k in claves]
                + [_mdp(r[f"mdp_{k}"] * 1e6) for k in claves]
                for nombre, r in gp.iterrows()],
    }

    # Campañas: el nombre solo existe desde 2024; antes solo hay una clave opaca.
    camp = b[b.campana_nombre.notna()]
    campanas = {}
    for anio, g in camp.groupby("anio_fuente"):
        s = (g.groupby("campana_nombre", observed=True)["monto_real"].sum() / 1e6)
        s = s[s > 0].sort_values(ascending=False)
        campanas[str(int(anio))] = {
            "items": [{"n": str(k), "v": _mdp(v * 1e6)} for k, v in s.items()],
            "total": _mdp(s.sum() * 1e6)}

    return {"serie": serie,
            "instituciones": treemap(**PANELES["instituciones"]),
            "beneficiarios": treemap(**PANELES["beneficiarios"]),
            "tabla": tabla,
            "conc": conc,
            "medios": medios,
            "campanas": campanas,
            "ganperd": ganperd,
            "ciclo": ciclo,
            "meta": {"renglones": int(len(b)), "columnas": int(len(df.columns)),
                     "polizas": int(b.poliza_id.nunique()),
                     "total_real": round(float(b.monto_real.sum() / 1e6), 1),
                     "anio_ini": anios_serie[0], "anio_fin": anios_serie[-1],
                     "anio_fin_completo": anios_completos[-1],
                     "n_completos": len(anios_completos),
                     # {"2026": {"meses": 5, "hasta": "mayo"}} — la página arma sus
                     # propias etiquetas con esto; ningún año va escrito en el HTML.
                     "parciales": {str(y): {"meses": m, "hasta": MESES[m - 1]}
                                   for y, m in parciales.items()}}}


# ─────────────────────────────────────────────────────────────── plantilla

TOKENS = """
:root{
  --bg:#FBF5E6; --surface:#FFFCF4; --surface-2:#FDF3DC;
  --ink:#331018; --ink-2:#71454F; --ink-3:#9C7C74;
  --line:#EDE0C8; --line-2:#E0CFAE;
  --accent:#F62477; --accent-deep:#92003A;
  --soft-pink:#FFADEE; --soft-yellow:#FFE185;
  --r1:#FB7EBC; --r2:#F62477; --r3:#C4104F; --r4:#92003A;
  --on-r1:#331018; --on-r2:#331018; --on-r3:#FFFCF4; --on-r4:#FFFCF4;
  --otros:#E6D8BC; --on-otros:#5C4636;
  --shadow:0 1px 2px rgba(51,16,24,.05),0 8px 26px rgba(51,16,24,.045);
  --font-display:'Bahnschrift','DIN Alternate','Roboto Condensed','Arial Narrow',ui-sans-serif,system-ui,sans-serif;
  --font-body:ui-sans-serif,system-ui,'Segoe UI Variable Text','Segoe UI',Roboto,'Helvetica Neue',sans-serif;
  --font-mono:ui-monospace,'Cascadia Mono','Segoe UI Mono','SF Mono',Consolas,monospace;
  color-scheme:light;
}
"""

ESTILO = TOKENS + """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-body);
     font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:52px 24px 96px}
@media (max-width:640px){.wrap{padding:32px 16px 64px}}

.eyebrow{font-family:var(--font-display);text-transform:uppercase;letter-spacing:.14em;
  font-size:12px;font-weight:600;color:var(--accent);margin:0 0 12px}
h1{font-family:var(--font-display);font-weight:700;letter-spacing:-.015em;
  font-size:clamp(34px,6vw,58px);line-height:1.02;margin:0 0 16px;text-wrap:balance}
h1 em{font-style:normal;color:var(--accent-deep)}
.lede{max-width:64ch;color:var(--ink-2);font-size:17px;margin:0 0 18px}
.byline{margin:0;font-family:var(--font-display);font-size:13px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3);display:inline-flex;align-items:center;gap:9px}
.byline::before{content:"";width:26px;height:2px;background:var(--accent);display:block}
.byline b{color:var(--accent-deep);font-weight:700;letter-spacing:.04em}
.credito{fill:var(--ink-3);font-family:var(--font-display);font-size:10px;
  letter-spacing:.09em;text-transform:uppercase;opacity:.8;pointer-events:none;user-select:none}
h2{font-family:var(--font-display);font-weight:700;letter-spacing:-.01em;
  font-size:clamp(22px,3vw,29px);line-height:1.1;margin:0 0 6px;text-wrap:balance}
.sub{color:var(--ink-2);font-size:14.5px;margin:0 0 20px;max-width:72ch}
a{color:var(--accent-deep)}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:36px 0 56px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:18px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.tile::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--accent)}
.tile:nth-child(2)::before{background:var(--accent-deep)}
.tile:nth-child(3)::before{background:var(--soft-pink)}
.tile:nth-child(4)::before{background:var(--soft-yellow)}
.tile .k{font-family:var(--font-display);font-size:clamp(28px,3.4vw,38px);font-weight:700;
  line-height:1;letter-spacing:-.02em;font-variant-numeric:tabular-nums;margin-bottom:6px}
.tile .l{font-size:12.5px;color:var(--ink-2);line-height:1.35}
.tile .u{font-size:11px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.08em;margin-top:2px}

section{margin:0 0 60px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
  padding:24px;box-shadow:var(--shadow)}
@media (max-width:640px){.card{padding:16px}}
.chart-scroll{overflow-x:auto}
svg{display:block;width:100%;height:auto}

.grid-line{stroke:var(--line-2);stroke-width:1}
.axis-txt{fill:var(--ink-3);font-family:var(--font-mono);font-size:11px}
.axis-yr{fill:var(--ink-2);font-family:var(--font-mono);font-size:12px}
.bar{fill:var(--accent);cursor:pointer;transition:fill .12s ease}
.bar:hover,.bar.sel{fill:var(--accent-deep)}
/* Año incompleto: rayado en vez de macizo. Es la única codificación que sobrevive
   a la impresión en blanco y negro y a no leer el pie de la gráfica. */
.bar.parcial{fill:url(#rayado)}
.bar.parcial:hover,.bar.parcial.sel{fill:url(#rayado-sel)}
.axis-yr.parcial{fill:var(--ink-3)}
.bar-val{fill:var(--ink);font-family:var(--font-display);font-size:12.5px;font-weight:700;
  text-anchor:middle;font-variant-numeric:tabular-nums;pointer-events:none}
.era-rule{stroke:var(--line-2);stroke-width:1.5}
.era-txt{fill:var(--ink-3);font-family:var(--font-display);font-size:11.5px;font-weight:600;
  text-transform:uppercase;letter-spacing:.1em}

.years{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 18px}
.yr{font-family:var(--font-mono);font-size:13px;padding:6px 11px;border-radius:9px;
  border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);
  cursor:pointer;transition:all .12s ease}
.yr:hover{border-color:var(--accent);color:var(--ink)}
.yr[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);
  color:#FFFCF4;font-weight:700}
.yr.parcial{border-style:dashed}
.yr.parcial::after{content:"*"}

.maps{display:grid;grid-template-columns:1fr;gap:22px}
.map-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:12px}
.map-head h3{font-family:var(--font-display);font-size:19px;font-weight:700;margin:0}
.map-head .tot{font-family:var(--font-mono);font-size:12.5px;color:var(--ink-2);
  font-variant-numeric:tabular-nums}
.cell{transition:opacity .12s ease}
.cell:hover{opacity:.84}
.cell-name{font-family:var(--font-body);font-size:10.5px;font-weight:600;pointer-events:none}
.cell-val{font-family:var(--font-mono);font-size:9.5px;pointer-events:none;font-variant-numeric:tabular-nums}

.salto{margin:20px 0 0;padding:16px 18px;border-radius:14px;background:var(--surface-2);
  border:1px solid var(--line-2);border-left:3px solid var(--accent);
  font-size:14.5px;color:var(--ink-2);line-height:1.5}
.salto a{font-family:var(--font-display);font-weight:700;font-size:16px;
  color:var(--accent-deep);text-decoration:none;border-bottom:2px solid var(--soft-pink)}
.salto a:hover{border-color:var(--accent)}

.legend{display:flex;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap}
.legend .lbl{font-size:11.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.08em;
  font-family:var(--font-display);font-weight:600}
.ramp{display:flex;gap:2px}
.ramp i{width:34px;height:11px;border-radius:2px;display:block}

#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s ease;z-index:50;
  background:var(--ink);color:var(--surface);padding:8px 11px;border-radius:9px;
  font-size:12.5px;line-height:1.45;max-width:290px;box-shadow:0 6px 20px rgba(51,16,24,.24)}
#tip b{font-family:var(--font-display);font-size:13.5px;display:block;margin-bottom:2px}
#tip .n{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
#tip .tip-parc{color:var(--soft-yellow);font-size:11.5px;font-style:italic}

details{margin-top:18px;border-top:1px solid var(--line);padding-top:14px}
summary{cursor:pointer;font-family:var(--font-display);font-size:13px;font-weight:600;
  color:var(--accent-deep);text-transform:uppercase;letter-spacing:.08em}
summary::marker{color:var(--accent)}
table{border-collapse:collapse;width:100%;margin-top:14px;font-size:13px}
th,td{text-align:right;padding:6px 10px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}
th{font-family:var(--font-display);font-size:11.5px;text-transform:uppercase;
  letter-spacing:.07em;color:var(--ink-3);font-weight:600}
td{font-family:var(--font-mono);font-variant-numeric:tabular-nums;color:var(--ink-2)}
td:first-child{font-family:var(--font-body);color:var(--ink)}
.tbl-scroll{overflow-x:auto}

/* ── buscador ── */
.filtros{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:16px}
.busca{flex:1 1 280px;position:relative;display:flex;align-items:center}
.busca input{width:100%;font-family:var(--font-body);font-size:15px;padding:11px 14px 11px 38px;
  border-radius:11px;border:1px solid var(--line-2);background:var(--surface);color:var(--ink)}
.busca input::placeholder{color:var(--ink-3)}
.busca input:focus{border-color:var(--accent);outline:none;box-shadow:0 0 0 3px rgba(246,36,119,.14)}
.busca svg.lupa{position:absolute;left:13px;width:16px;height:16px;stroke:var(--ink-3);
  fill:none;stroke-width:2;pointer-events:none}
.filtros select{font-family:var(--font-body);font-size:14px;padding:10px 12px;border-radius:11px;
  border:1px solid var(--line-2);background:var(--surface);color:var(--ink);cursor:pointer}
.filtros select:focus{border-color:var(--accent);outline:none}
.cuenta{font-family:var(--font-mono);font-size:13px;color:var(--ink-2);margin:0 0 10px;
  font-variant-numeric:tabular-nums}
.cuenta b{color:var(--accent-deep)}
.aviso{font-size:14px;line-height:1.5;color:var(--ink-2);background:var(--surface-2);
  border:1px solid var(--line-2);border-left:3px solid var(--accent);border-radius:12px;
  padding:14px 16px;margin:0 0 20px;max-width:78ch}
.aviso b{color:var(--ink)}
.aviso .pill{vertical-align:1px}
.aviso.corto{margin:0 0 14px;padding:10px 14px;font-size:13.5px;border-left-color:var(--c3)}
.aviso.corto[hidden]{display:none}
/* Cobertura parcial del año en curso. Amarillo suave y no rosa: es una advertencia
   de lectura, no un dato, y no debe competir con las cifras. Va arriba del todo. */
.aviso.cobertura{background:var(--soft-yellow);border-color:var(--line-2);
  border-left:4px solid var(--accent-deep);max-width:64ch;margin:18px 0 22px}
#tblBusca th{cursor:pointer;user-select:none;white-space:nowrap}
#tblBusca th:hover{color:var(--accent-deep)}
#tblBusca th[data-dir]::after{content:" ▾";color:var(--accent)}
#tblBusca th[data-dir="asc"]::after{content:" ▴"}
#tblBusca tbody tr:hover{background:var(--surface-2)}
.pill{display:inline-block;font-family:var(--font-display);font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.07em;padding:2px 7px;border-radius:5px;
  color:var(--ink);white-space:nowrap}
.pill.inst{background:var(--soft-pink)}
.pill.emp{background:var(--soft-yellow)}
.pag{display:flex;gap:8px;align-items:center;justify-content:center;margin-top:16px;flex-wrap:wrap}
.pag button{font-family:var(--font-body);font-size:14px;padding:8px 14px;border-radius:10px;
  border:1px solid var(--line-2);background:var(--surface);color:var(--ink-2);cursor:pointer}
.pag button:hover:not(:disabled){border-color:var(--accent);color:var(--ink)}
.pag button:disabled{opacity:.4;cursor:default}
.pag .idx{font-family:var(--font-mono);font-size:13px;color:var(--ink-2);
  font-variant-numeric:tabular-nums}
.vacio{text-align:center;padding:32px 12px;color:var(--ink-3);font-size:14.5px}

/* ── rampa de campañas: tercera familia, verde azulado ──
   Pasa el criterio ordinal sobre la tarjeta crema (ΔL 0.082/0.122/0.128, paso más
   claro a 2.35 de contraste) y no se confunde ni con el rosa ni con el ámbar. */
:root{
  --c1:#4FB8A3; --c2:#2E9E8B; --c3:#17766A; --c4:#0C4E45;
  --on-c1:#331018; --on-c2:#331018; --on-c3:#FFFCF4; --on-c4:#FFFCF4;
  --a1:#D8930F; --a2:#B8790A; --a3:#966006; --a4:#7A4A02;
}

/* ── portadas de las vistas de pantalla completa ── */
.portadas{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}
.portada{display:flex;flex-direction:column;gap:9px;padding:20px;border-radius:16px;
  border:1px solid var(--line-2);background:var(--surface);box-shadow:var(--shadow);
  text-decoration:none;color:var(--ink-2);font-size:14px;line-height:1.5;
  transition:border-color .14s ease,transform .14s ease,box-shadow .14s ease}
.portada:hover{border-color:var(--accent);transform:translateY(-2px);
  box-shadow:0 4px 10px rgba(51,16,24,.07),0 14px 34px rgba(51,16,24,.08)}
.portada b{font-family:var(--font-display);font-size:21px;color:var(--ink);font-weight:700;
  letter-spacing:-.01em}
.portada .mini{display:grid;grid-template-columns:repeat(4,1fr);grid-template-rows:repeat(3,1fr);
  gap:3px;height:86px;margin-bottom:4px}
.portada .mini i{display:block;border-radius:3px}
.portada .ir{font-family:var(--font-display);font-weight:700;color:var(--accent-deep);
  font-size:14px;margin-top:auto;letter-spacing:.02em}

/* ── líneas de medios ──
   El color no distingue series: son nueve y ninguna paleta de nueve sobrevive al
   daltonismo. La identidad la dan las etiquetas al final; el acento solo marca
   la línea que estás señalando. */
.linea{fill:none;stroke:var(--ink-3);stroke-width:1.6;opacity:.5;
  stroke-linejoin:round;stroke-linecap:round;transition:stroke .1s ease,opacity .1s ease}
.linea.act{stroke:var(--accent);stroke-width:2.8;opacity:1}
.guia{stroke:var(--line-2);stroke-width:1;fill:none}
.guia.act{stroke:var(--accent)}
.etq-linea{font-family:var(--font-body);font-size:11.5px;fill:var(--ink-2);pointer-events:none}
.etq-linea.act{fill:var(--accent-deep);font-weight:700}
.etq-val{font-family:var(--font-mono);font-size:11px;fill:var(--ink-3);
  font-variant-numeric:tabular-nums;pointer-events:none}
.cross{stroke:var(--accent);stroke-width:1;opacity:.4;stroke-dasharray:3 3}
.punto{fill:var(--surface);stroke:var(--ink-3);stroke-width:1.4}
.punto.act{fill:var(--accent);stroke:var(--surface);stroke-width:2}
#mCaptura{cursor:crosshair}
#tip .fl{display:flex;justify-content:space-between;gap:14px;opacity:.72;padding:1px 0}
#tip .fl.act{opacity:1;font-weight:700}
.nota-pie{font-size:12.5px;color:var(--ink-3);margin:14px 0 0}

/* ── descargas ── */
.bajar{display:grid;grid-template-columns:repeat(auto-fit,minmax(238px,1fr));gap:12px}
.bj{display:flex;flex-direction:column;gap:3px;text-align:left;padding:16px 18px;border-radius:14px;
  border:1px solid var(--line-2);background:var(--surface-2);color:var(--ink-2);
  text-decoration:none;cursor:pointer;font-family:var(--font-body);font-size:13px;
  transition:border-color .12s ease,transform .12s ease}
.bj:hover{border-color:var(--accent);transform:translateY(-1px)}
.bj b{font-family:var(--font-display);font-size:16px;color:var(--ink);font-weight:700}
.bj .q{color:var(--ink-3);font-size:12px}
.bj.primario{background:var(--soft-yellow);border-color:#E8C65C}
.bj.primario b{color:var(--accent-deep)}
.bj.primario .q{color:#7A5C10}
#tblDicc td{vertical-align:top}
#tblDicc td code{font-size:12px;color:var(--ink);white-space:nowrap}
#tblDicc tr.grupo td{font-family:var(--font-display);font-size:11.5px;text-transform:uppercase;
  letter-spacing:.09em;color:var(--accent-deep);font-weight:700;padding-top:16px;
  border-bottom:1px solid var(--line-2)}

/* ── ciclo electoral ── */
.eje-cero{stroke:var(--ink-3);stroke-width:1.2}
.barra-ciclo{cursor:default}
.banda-parcial{fill:var(--soft-yellow);opacity:.5;pointer-events:none}
.voto{fill:var(--accent-deep);font-family:var(--font-display);font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.06em;text-anchor:middle}
.resumen-ciclo{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;
  margin-top:18px}
.rc{background:var(--surface-2);border:1px solid var(--line-2);border-radius:12px;padding:14px 16px}
.rc b{display:block;font-family:var(--font-display);font-size:26px;line-height:1;
  color:var(--accent-deep);font-variant-numeric:tabular-nums;margin-bottom:5px}
.rc span{font-size:12.5px;color:var(--ink-2);line-height:1.4}

/* ── ganadores y perdedores ── */
.gp-cab,.gp-fila{display:grid;
  grid-template-columns:minmax(130px,1.5fr) minmax(150px,2fr) 66px 92px 96px;
  gap:12px;align-items:center}
.gp-cab{font-family:var(--font-display);font-size:11px;text-transform:uppercase;
  letter-spacing:.07em;color:var(--ink-3);font-weight:600;padding:0 4px 8px;
  border-bottom:1px solid var(--line-2)}
.gp-cab .der,.gp-fila .der{text-align:right}
.gp-fila{padding:6px 4px;border-bottom:1px solid var(--line);font-size:13px}
.gp-fila:hover{background:var(--surface-2)}
.gp-fila .nombre{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.gp-fila .num{font-family:var(--font-mono);font-variant-numeric:tabular-nums;
  color:var(--ink-2);text-align:right;font-size:12.5px}
/* Barra divergente: el cero al centro, gana a la derecha y pierde a la izquierda. */
.dv{position:relative;height:17px;background:linear-gradient(var(--line),var(--line)) no-repeat
  center/1px 100%}
.dv i{position:absolute;top:2px;height:13px;border-radius:3px}
.dv i.mas{left:50%;background:var(--accent)}
.dv i.menos{right:50%;background:var(--c3)}
.dv b{position:absolute;top:0;font-family:var(--font-mono);font-size:11.5px;line-height:17px;
  font-variant-numeric:tabular-nums;font-weight:700}
.dv b.mas{color:var(--accent-deep)}
.dv b.menos{color:var(--c4)}
@media (max-width:640px){
  .gp-cab,.gp-fila{grid-template-columns:minmax(100px,1.3fr) minmax(90px,1.6fr) 56px}
  .gp-cab span:nth-child(n+4),.gp-fila .mdp{display:none}
}

/* ── concentración ── */
.conc-cab,.conc-fila{display:grid;grid-template-columns:minmax(150px,1.6fr) minmax(120px,2.2fr) 58px 72px 92px;
  gap:12px;align-items:center}
.conc-cab{font-family:var(--font-display);font-size:11px;text-transform:uppercase;
  letter-spacing:.07em;color:var(--ink-3);font-weight:600;padding:0 4px 8px;
  border-bottom:1px solid var(--line-2)}
.conc-cab .der,.conc-fila .der{text-align:right}
.conc-scroll{max-height:min(70vh,620px);overflow-y:auto;overflow-x:hidden;padding-right:4px}
.conc-fila{padding:5px 4px;border-bottom:1px solid var(--line);font-size:13px}
.conc-fila:hover{background:var(--surface-2)}
.conc-fila .nombre{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.conc-fila .pista{height:15px;background:var(--line);border-radius:4px;overflow:hidden}
.conc-fila .pista i{display:block;height:100%;border-radius:4px}
.conc-fila .num{font-family:var(--font-mono);font-variant-numeric:tabular-nums;color:var(--ink-2);
  text-align:right}
.conc-fila .num.fuerte{color:var(--ink);font-weight:600}
@media (max-width:640px){
  .conc-cab,.conc-fila{grid-template-columns:minmax(110px,1.4fr) minmax(70px,1.6fr) 50px 58px}
  .conc-cab span:last-child,.conc-fila .mdp{display:none}
}

.notes{background:var(--surface-2);border:1px solid var(--line-2);border-radius:16px;padding:24px}
.notes h2{font-size:20px;margin-bottom:14px}
.notes ul{margin:0;padding-left:0;list-style:none;display:grid;gap:12px}
.notes li{font-size:14px;color:var(--ink-2);line-height:1.5;padding-left:16px;
  border-left:2px solid var(--line-2)}
.notes li b{color:var(--ink);font-weight:600}
.flag{border-left-color:var(--accent)}
.flag b{color:var(--accent-deep)}
.src{margin-top:26px;font-size:12.5px;color:var(--ink-3);line-height:1.6}

:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
@media (prefers-reduced-motion:reduce){*{transition:none !important;animation:none !important}}
@media print{.years,#tip{display:none}.card,.notes{box-shadow:none;break-inside:avoid}}
"""

CUERPO = """
<div class="wrap">
  <p class="eyebrow">Sistema COMSOC &middot; Gobierno federal de M&eacute;xico</p>
  <h1>Publicidad oficial,<br><em>__RANGO__</em></h1>
  <p class="lede">
    __COBERTURA__ reconstruidos
    desde el detalle de p&oacute;lizas: __RENGLONES__ renglones de __POLIZAS__ p&oacute;lizas.
    Todas las cifras en <b>millones de pesos constantes de 2020</b>.
  </p>
  __AVISO__
  <p class="byline">An&aacute;lisis y elaboraci&oacute;n de <b>__AUTOR__</b></p>

  <div class="stats" id="stats"></div>

  <section>
    <h2>El gasto total por a&ntilde;o</h2>
    <p class="sub">Cada barra es el gasto federal del ejercicio, deflactado.
      Da clic en una barra para cambiar el a&ntilde;o de los treemaps de abajo.</p>
    <div class="card">
      <div class="chart-scroll"><svg id="bars" viewBox="0 0 1000 400" role="img"
        aria-label="Gasto federal en publicidad oficial por a&ntilde;o, __RANGO__, en millones de pesos de 2020"></svg></div>
      <details>
        <summary>Ver los datos</summary>
        <div class="tbl-scroll"><table id="tblSerie"></table></div>
      </details>
    </div>
  </section>

  <section>
    <h2>Qui&eacute;n gasta y qui&eacute;n cobra</h2>
    <p class="sub">Cada cuadrado es un monto en pesos deflactados: su &aacute;rea y su color
      codifican lo mismo. Arriba, las instituciones que pagan; abajo, las empresas que reciben.
      Se muestran las __TOP__ mayores de cada a&ntilde;o con cuadro propio; la cola se parte en
      tramos de posici&oacute;n del ranking, marcados <b>con trama diagonal</b>.</p>

    <div class="years" id="years" role="group" aria-label="Seleccionar a&ntilde;o"></div>

    <div class="maps">
      <div class="card">
        <div class="map-head"><h3>Instituciones que pagan</h3><span class="tot" id="totInst"></span></div>
        <svg id="mapInst" viewBox="0 0 1000 470" role="img" aria-label="Treemap de instituciones"></svg>
      </div>
      <div class="card">
        <div class="map-head"><h3>Empresas que reciben</h3><span class="tot" id="totBen"></span></div>
        <svg id="mapBen" viewBox="0 0 1000 470" role="img" aria-label="Treemap de empresas"></svg>
      </div>
    </div>

    <div class="legend">
      <span class="lbl">Menor monto</span>
      <span class="ramp"><i style="background:var(--r1)"></i><i style="background:var(--r2)"></i><i
        style="background:var(--r3)"></i><i style="background:var(--r4)"></i></span>
      <span class="lbl">Mayor monto</span>
    </div>

    <div class="card" style="margin-top:20px">
      <details>
        <summary>Ver los datos del a&ntilde;o seleccionado</summary>
        <div class="tbl-scroll"><table id="tblAnio"></table></div>
      </details>
    </div>

  </section>

  <section>
    <h2>&iquest;Se gasta m&aacute;s en a&ntilde;o electoral?</h2>
    <p class="sub">Cada a&ntilde;o comparado contra el <b>promedio de sus dos vecinos</b>.
      As&iacute; se ve el ciclo sin que lo tape el desplome de 2019.</p>
    <div class="card">
      <div class="chart-scroll">
        <svg id="cCiclo" viewBox="0 0 1000 300" role="img"
             aria-label="Gasto de cada a&ntilde;o comparado con el promedio de sus vecinos"></svg>
      </div>
      <p class="nota-pie" id="cNota"></p>
      <div class="resumen-ciclo" id="cResumen"></div>
    </div>
    <p class="aviso">
      <b>No hay an&aacute;lisis por mes, y no por descuido.</b> Ninguno de los tres campos de
      fecha aguanta esa resoluci&oacute;n. El campo <code>mes</code> no dice cu&aacute;ndo se
      anunci&oacute; sino en qu&eacute; periodo se registr&oacute; el gasto: concentra 51.6% de
      todo en diciembre, y hay renglones con <code>mes = 12</code> cuya fecha cae en enero
      &mdash;incluso de enero del a&ntilde;o siguiente&mdash;. La proporci&oacute;n de diciembre
      salta de 14.9% a 83.8% seg&uacute;n el a&ntilde;o, o sea que refleja c&oacute;mo se
      compil&oacute; cada archivo. La fecha de contrato tampoco: pasa de 56.8% del gasto en
      abril&ndash;junio en 2024 a 1.3% en 2025. <b>Por eso la comparaci&oacute;n es anual.</b>
    </p>
  </section>

  <section>
    <h2>Explora el gasto a pantalla completa</h2>
    <p class="sub">Tres treemaps interactivos: cada caja se abre al darle clic. El color sigue
      al tipo de entidad &mdash; <b style="color:var(--r3)">instituciones</b>,
      <b style="color:var(--a3)">empresas</b>, <b style="color:var(--c4)">productos</b>.</p>
    <div class="portadas">
      <a class="portada" href="quien-paga-a-quien.html">
        <span class="mini" aria-hidden="true">
          <i style="grid-area:1/1/3/3;background:var(--r4)"></i>
          <i style="grid-area:1/3/2/5;background:var(--r3)"></i>
          <i style="grid-area:2/3/3/4;background:var(--r2)"></i>
          <i style="grid-area:2/4/3/5;background:var(--r1)"></i>
          <i style="grid-area:3/1/4/3;background:var(--a3)"></i>
          <i style="grid-area:3/3/4/5;background:var(--a2)"></i>
        </span>
        <b>&iquest;Qui&eacute;n le paga a qui&eacute;n?</b>
        <span>Cada caja es una instituci&oacute;n. Da clic y se abren las empresas que
          recibieron su dinero &mdash; el IMSS le pag&oacute; a 705 distintas.</span>
        <span class="ir">Abrir &rarr;</span>
      </a>
      <a class="portada" href="empresas.html">
        <span class="mini" aria-hidden="true">
          <i style="grid-area:1/1/3/3;background:var(--a4)"></i>
          <i style="grid-area:1/3/2/5;background:var(--a3)"></i>
          <i style="grid-area:2/3/3/4;background:var(--a2)"></i>
          <i style="grid-area:2/4/3/5;background:var(--a1)"></i>
          <i style="grid-area:3/1/4/3;background:var(--r3)"></i>
          <i style="grid-area:3/3/4/5;background:var(--r2)"></i>
        </span>
        <b>&iquest;Qui&eacute;n le cobra a qui&eacute;n?</b>
        <span>El mismo dinero al rev&eacute;s. Cada caja es una empresa; da clic y se abren
          las instituciones que le pagaron.</span>
        <span class="ir">Abrir &rarr;</span>
      </a>
      <a class="portada" href="medios.html">
        <span class="mini" aria-hidden="true">
          <i style="grid-area:1/1/4/3;background:var(--a4)"></i>
          <i style="grid-area:1/3/3/5;background:var(--a3)"></i>
          <i style="grid-area:3/3/4/4;background:var(--c3)"></i>
          <i style="grid-area:3/4/4/5;background:var(--c2)"></i>
        </span>
        <b>&iquest;En qu&eacute; medios?</b>
        <span>Tambi&eacute;n por empresa, pero al abrirla se ve <b>qu&eacute; producto</b>
          vendi&oacute;: televisi&oacute;n, radio, internet, mobiliario urbano.</span>
        <span class="ir">Abrir &rarr;</span>
      </a>
    </div>
  </section>

  <section>
    <h2>En qu&eacute; medios se gasta, a lo largo del tiempo</h2>
    <p class="sub">Las nueve familias de medios en el mismo plano. Pasa el cursor por la
      gr&aacute;fica para ver todos los valores de ese a&ntilde;o; la l&iacute;nea m&aacute;s
      cercana se resalta.</p>
    <div class="card">
      <div class="filtros">
        <select id="mMedida" aria-label="Medida">
          <option value="pct">Como % del gasto del a&ntilde;o</option>
          <option value="abs">En millones de pesos de 2020</option>
        </select>
      </div>
      <div class="chart-scroll">
        <svg id="mLineas" viewBox="0 0 1000 430" role="img"
             aria-label="Gasto por familia de medio, __RANGO__"></svg>
      </div>
      <p class="nota-pie" id="mNota"></p>
      <details>
        <summary>Ver los datos</summary>
        <div class="tbl-scroll"><table id="tblMedios"></table></div>
      </details>
    </div>
  </section>

  <section>
    <h2>En qu&eacute; campa&ntilde;as</h2>
    <p class="sub">Cada cuadro es una campa&ntilde;a y su tama&ntilde;o es lo que cost&oacute;.</p>
    <p class="aviso">
      <b>Solo hay nombres de campa&ntilde;a desde 2024.</b> Antes, la fuente publica una clave
      opaca como <code>091/22-2001-TC18-00625</code> que no dice qu&eacute; se anunci&oacute;.
      Por eso esta secci&oacute;n empieza en 2024 y no cubre la serie completa.
    </p>
    <div class="card">
      <div class="filtros">
        <select id="kAnio" aria-label="A&ntilde;o de la campa&ntilde;a"></select>
      </div>
      <p class="cuenta" id="kCuenta"></p>
      <svg id="mapCamp" viewBox="0 0 1000 470" role="img"
           aria-label="Treemap de campa&ntilde;as"></svg>
    </div>
  </section>

  <section>
    <h2>Qui&eacute;n gan&oacute; y qui&eacute;n perdi&oacute; con el cambio de sexenio</h2>
    <p class="sub">Participaci&oacute;n promedio de cada empresa en el gasto federal, comparada
      entre dos sexenios.</p>
    <p class="aviso">
      <b>Se compara participaci&oacute;n, no pesos, y sexenios, no a&ntilde;os.</b> En 2019 el
      gasto real cay&oacute; 67%: medido en pesos absolutos perdieron todos, as&iacute; que el
      monto no distingue a quien perdi&oacute; terreno de quien solo vivi&oacute; el recorte.
      Y el cambio de participaci&oacute;n de un a&ntilde;o al siguiente tiene una mediana de
      0.021 pp &mdash;casi todo ruido&mdash;, por eso se promedian los a&ntilde;os de cada lado.
      <b>La columna de millones est&aacute; al lado a prop&oacute;sito:</b> hay quien gan&oacute;
      participaci&oacute;n cobrando menos.
    </p>
    <div class="card">
      <div class="filtros">
        <select id="gPar" aria-label="Sexenios a comparar"></select>
        <select id="gVista" aria-label="Qu&eacute; mostrar">
          <option value="ambos">Presentes en los dos periodos</option>
          <option value="salieron">Dejaron de recibir dinero</option>
          <option value="entraron">Aparecieron en el segundo</option>
        </select>
      </div>
      <p class="aviso corto" id="gAviso" hidden></p>
      <p class="cuenta" id="gCuenta"></p>
      <div class="gp-cab" id="gCab"></div>
      <div class="conc-scroll" id="gLista"></div>
    </div>
  </section>

  <section>
    <h2>Qu&eacute; tan concentrado est&aacute; el gasto de cada instituci&oacute;n</h2>
    <p class="sub">Qu&eacute; porcentaje del dinero de cada instituci&oacute;n se lo llev&oacute;
      su proveedor m&aacute;s grande, de la m&aacute;s concentrada a la menos.
      El <b>largo de la barra</b> es esa concentraci&oacute;n; el <b>color</b> es cu&aacute;nto
      gasta la instituci&oacute;n, para distinguir a las grandes de las peque&ntilde;as.</p>
    <p class="aviso">
      <b>Concentrarse no siempre significa lo mismo.</b> Una instituci&oacute;n que solo le
      compr&oacute; a un proveedor sale con 100% y encabeza la lista, aunque haya gastado muy
      poco. Fíjate en la columna de <b>proveedores</b> y en el color: una barra larga y clara,
      con dos o tres proveedores, es una instituci&oacute;n chica, no una capturada.
    </p>
    <div class="card">
      <div class="filtros">
        <select id="cMetrica" aria-label="Medida de concentraci&oacute;n">
          <option value="3">Proveedor m&aacute;s grande</option>
          <option value="4">Tres proveedores m&aacute;s grandes</option>
          <option value="5">Cinco proveedores m&aacute;s grandes</option>
        </select>
        <select id="cUmbral" aria-label="Gasto m&iacute;nimo">
          <option value="1">Con m&aacute;s de 1 MDP</option>
          <option value="10">Con m&aacute;s de 10 MDP</option>
          <option value="50">Con m&aacute;s de 50 MDP</option>
          <option value="100">Con m&aacute;s de 100 MDP</option>
        </select>
        <select id="cAnio" aria-label="A&ntilde;o"></select>
      </div>
      <p class="cuenta" id="cCuenta"></p>
      <div class="legend" style="margin:0 0 12px">
        <span class="lbl">Gasta menos</span>
        <span class="ramp">
          <i style="background:var(--r1)"></i><i style="background:var(--r2)"></i>
          <i style="background:var(--r3)"></i><i style="background:var(--r4)"></i>
        </span>
        <span class="lbl">Gasta m&aacute;s</span>
      </div>
      <div class="conc-cab">
        <span>Instituci&oacute;n</span><span>Concentraci&oacute;n</span>
        <span class="der">%</span><span class="der">Proveed.</span><span class="der">MDP 2020</span>
      </div>
      <div class="conc-scroll" id="cLista"></div>
    </div>
  </section>

  <section>
    <h2>Busca cualquier instituci&oacute;n o empresa</h2>
    <p class="sub">Toda la serie, a&ntilde;o por a&ntilde;o: __FILAS__ registros de
      __ENTIDADES__ instituciones y empresas distintas. Escribe un nombre &mdash;o unas siglas,
      como <i>IMSS</i> o <i>Condusef</i>&mdash;, filtra por a&ntilde;o o tipo, y ordena por
      cualquier columna.</p>
    <p class="aviso">
      <b>El monto significa cosas distintas seg&uacute;n el tipo de rengl&oacute;n:</b> en los de
      <span class="pill inst">Instit.</span> es dinero <b>erogado</b>, lo que esa instituci&oacute;n
      pag&oacute;; en los de <span class="pill emp">Empresa</span> es dinero <b>recibido</b>, lo que
      esa empresa cobr&oacute;. Son las dos caras del mismo peso, no dos gastos:
      <b>no sumes entre tipos</b> o contar&aacute;s doble.
    </p>
    <div class="card">
      <div class="filtros">
        <label class="busca">
          <svg class="lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>
          <input id="q" type="search" autocomplete="off" placeholder="Televisa, IMSS, Jornada, Lotenal&hellip;"
                 aria-label="Buscar instituci&oacute;n o empresa">
        </label>
        <select id="fTipo" aria-label="Filtrar por tipo">
          <option value="">Instituciones y empresas</option>
          <option value="0">Solo instituciones</option>
          <option value="1">Solo empresas</option>
        </select>
        <select id="fAnio" aria-label="Filtrar por a&ntilde;o"></select>
      </div>
      <p class="cuenta" id="cuenta"></p>
      <div class="tbl-scroll"><table id="tblBusca"></table></div>
      <div class="pag" id="pag"></div>
    </div>
  </section>

  <section>
    <h2>Ll&eacute;vate los datos</h2>
    <p class="sub">Todo lo que hay detr&aacute;s de este reporte, para que puedas revisarlo,
      rehacerlo o contradecirlo.</p>
    <div class="card">
      <div class="bajar">
        <a class="bj primario" href="datos/comsoc_polizas_csv.zip" download>
          <b>Dataset completo &middot; CSV</b>
          <span>ZIP de __PESO_CSV__ MB &middot; __RENGLONES__ renglones &times; __COLUMNAS__ columnas</span>
          <span class="q">Doble clic para abrirlo; adentro va el CSV</span>
        </a>
        <a class="bj" href="datos/comsoc_polizas.parquet" download>
          <b>Dataset completo &middot; Parquet</b>
          <span>__PESO_PARQUET__ MB &middot; mismos datos, con tipos</span>
          <span class="q">Para analizarlo en Python o R</span>
        </a>
        <button class="bj" id="bajaAgregado" type="button">
          <b>Resumen por entidad y a&ntilde;o &middot; CSV</b>
          <span>__FILAS__ renglones &middot; se genera al instante</span>
          <span class="q">Lo mismo que muestra el buscador</span>
        </button>
      </div>
      <details>
        <summary>Qu&eacute; trae cada columna</summary>
        <div class="tbl-scroll"><table id="tblDicc"></table></div>
      </details>
    </div>
  </section>

  <div class="notes">
    <h2>C&oacute;mo leer estas cifras</h2>
    <ul>
      <li class="flag"><b>Es solo gasto federal.</b> Cubre las dependencias y entidades de la
        Administraci&oacute;n P&uacute;blica Federal que reportan al sistema COMSOC. No incluye
        gasto de gobiernos estatales ni municipales.</li>
      <li class="flag"><b>La cifra de Imagen est&aacute; inflada hasta 39%.</b> La regla de
        homologaci&oacute;n heredada agrupa 58 razones sociales y 50 RFC distintos; solo unos
        2,408 de sus 3,936 MDP son inequ&iacute;vocamente Grupo Imagen. Dos empresas que valen
        1,401 MDP siguen sin verificar.</li>
      __AVISO_CORTO__
      <li><b>Los dos &uacute;ltimos a&ntilde;os usan un deflactor estimado.</b> La serie del
        deflactor impl&iacute;cito del PIB (base 2020=100) marca 2025 y 2026 como estimados;
        esas cifras reales pueden moverse.</li>
      <li><b>Partidas incluidas:</b> 36101 y 36201 (difusi&oacute;n de mensajes gubernamentales y
        comerciales) m&aacute;s 33605 (informaci&oacute;n en medios masivos por operaci&oacute;n).
        33605 es gasto operativo y pesa poco: entre 0.9% y 2.2% del total anual.</li>
      <li><b>Se excluye la publicidad pagada en especie</b> (intercambios) y la edici&oacute;n
        preliminar de 2023, que reportaba 43% menos registros que la definitiva.</li>
      <li><b>El a&ntilde;o es el del ejercicio fiscal que reporta la fuente</b>, no el de la fecha
        de pago.</li>
    </ul>
    <p class="src">
      <b style="color:var(--accent-deep)">An&aacute;lisis, procesamiento y elaboraci&oacute;n:
      __AUTOR__.</b> Se agradece la cita de la autor&iacute;a al reproducir estas
      gr&aacute;ficas o cifras.<br><br>
      Fuente: Sistema de Gastos de Comunicaci&oacute;n Social (COMSOC), Secretar&iacute;a
      Anticorrupci&oacute;n y Buen Gobierno (antes Secretar&iacute;a de la Funci&oacute;n
      P&uacute;blica).<br>
      <a href="__URL_COMSOC__" rel="noopener">__URL_COMSOC__</a><br><br>
      Deflactor impl&iacute;cito del PIB base 2020=100, FUNDAR, Nota Metodol&oacute;gica 2025.
      Las cifras de 2025 usan el factor estimado de esa serie.
    </p>
  </div>
</div>

<div id="tip" role="status" aria-live="polite"></div>
"""

GUION = r"""
const DATA = __DATOS__;
const AUTOR = '__AUTOR__';
/* Alias de los bloques de datos, TODOS aquí arriba. `const` no se puede leer antes
   de su línea, así que declararlos junto a la sección que los estrena hace que
   agregar una sección nueva más arriba rompa la página entera en silencio: eso ya
   pasó dos veces con `T`. */
const T = DATA.tabla;
const CONC = DATA.conc;
const MED = DATA.medios;
const CAMP = DATA.campanas;
const GP = DATA.ganperd;
const fmt  = n => n.toLocaleString('es-MX',{maximumFractionDigits:0});
const fmt1 = n => n.toLocaleString('es-MX',{minimumFractionDigits:1,maximumFractionDigits:1});

/* Los montos llegan en millones. Redondear a un decimal deja en "0.0" a 7,278 de
   los 46,548 pares institución×empresa×año —el 15.6%—, que así parecen valer cero
   cuando el menor de todos son 78 pesos. Por eso la unidad se adapta al tamaño en
   vez de forzar millones. */
function fmtM(v, compacto){
  const a = Math.abs(v);
  if(a >= 1)      return fmt1(v) + (compacto ? '' : ' MDP');
  if(a >= 0.001)  return fmt(v*1e3) + (compacto ? ' mil' : ' mil pesos');
  if(a > 0)       return fmt(v*1e6) + (compacto ? ' $' : ' pesos');
  return compacto ? '—' : 'sin gasto';
}
/* Mismo problema con los porcentajes: 78 pesos sobre 12,735 millones es 0.0000006%,
   y "0.00%" se lee como "nada" cuando es "muy poco pero existe". */
function fmtPct(p){
  if(p === 0)     return '—';
  if(p < 0.01)    return '<0.01%';
  return p.toFixed(2) + '%';
}
const css  = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const S='http://www.w3.org/2000/svg';
const el=(t,a={})=>{const e=document.createElementNS(S,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const serie = DATA.serie;
const META  = DATA.meta;

/* Años incompletos. `parciales` viene de layouts.yaml: {"2026":{meses:5,hasta:"mayo"}}.
   Ningún año va escrito en el guion; cuando el corte se mueva a agosto, esto sigue bien. */
const PARC     = META.parciales || {};
const esParcial= a => !!PARC[String(a)];
const mesesDe  = a => (PARC[String(a)]||{}).hasta || '';
/* Con asterisco en los ejes y los selectores, donde no cabe la explicación. */
const etqAnio  = a => esParcial(a) ? a+'*' : String(a);
/* Donde sí cabe: los <select>, que es donde el usuario elige a ciegas. */
const etqAnioLargo = a => esParcial(a) ? a+' (enero–'+mesesDe(a)+')' : String(a);
const notaParc = a => esParcial(a)
  ? '<br><span class="tip-parc">solo enero–'+mesesDe(a)+'; no comparable con un año completo</span>' : '';
const RANGO    = META.anio_ini+'–'+META.anio_fin;

/* El año por omisión es el último COMPLETO: abrir en un año de cinco meses invita
   a leerlo como si fuera uno entero. El de 2026 sigue a un clic, marcado. */
let anioSel = META.anio_fin_completo;

(function(){
  const y18=serie.find(d=>d.anio===2018).real, y19=serie.find(d=>d.anio===2019).real;
  const y23=serie.find(d=>d.anio===2023).real;
  const yUlt=serie.find(d=>d.anio===META.anio_fin_completo);
  const items=[
    {k:fmt(META.total_real), l:'Gasto federal acumulado '+RANGO, u:'millones de pesos de 2020'},
    {k:((y19/y18-1)*100).toFixed(1)+'%', l:'Cayó el gasto de 2018 a 2019', u:'medido en pesos de 2020'},
    {k:'+'+((yUlt.real/y23-1)*100).toFixed(1)+'%',
     l:'Subió el gasto de 2023 a '+META.anio_fin_completo, u:'medido en pesos de 2020'},
    {k:fmt(META.polizas), l:'Pólizas analizadas', u:fmt(META.renglones)+' renglones'}];
  document.getElementById('stats').innerHTML = items.map(d=>
    '<div class="tile"><div class="k">'+d.k+'</div><div class="l">'+d.l+'</div><div class="u">'+d.u+'</div></div>').join('');
})();

const tip=document.getElementById('tip');
function showTip(e,html){
  tip.innerHTML=html; tip.style.opacity=1;
  const r=tip.getBoundingClientRect();
  let x=e.clientX+14, y=e.clientY+14;
  if(x+r.width>innerWidth-8) x=e.clientX-r.width-14;
  if(y+r.height>innerHeight-8) y=e.clientY-r.height-14;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
const hideTip=()=>tip.style.opacity=0;

/* Rayado diagonal para el año incompleto. Va como <pattern> y no como opacidad
   porque la opacidad se lee como "menos gasto", que es justo el malentendido. */
function defsRayado(){
  const d=el('defs');
  [['rayado',css('--accent')],['rayado-sel',css('--accent-deep')]].forEach(([id,color])=>{
    const p=el('pattern',{id:id,width:7,height:7,patternUnits:'userSpaceOnUse',
                          patternTransform:'rotate(45)'});
    p.appendChild(el('rect',{width:7,height:7,fill:css('--bg')}));
    p.appendChild(el('rect',{width:3.6,height:7,fill:color}));
    d.appendChild(p);
  });
  return d;
}

const W=1000,H=400,ML=64,MR=16,MT=54,MB=52;
function drawBars(){
  const svg=document.getElementById('bars'); svg.textContent='';
  svg.appendChild(defsRayado());
  const iw=W-ML-MR, ih=H-MT-MB;
  const max=Math.max.apply(null,serie.map(d=>d.real))*1.12;
  const bw=iw/serie.length, x=i=>ML+i*bw, y=v=>MT+ih-(v/max)*ih;
  for(let i=0;i<=4;i++){
    const v=max*i/4, yy=y(v);
    svg.appendChild(el('line',{x1:ML,x2:W-MR,y1:yy,y2:yy,class:'grid-line'}));
    const t=el('text',{x:ML-10,y:yy+4,class:'axis-txt','text-anchor':'end'});
    t.textContent=fmt(v); svg.appendChild(t);
  }
  [{n:'Peña Nieto',a:2012,b:2018},{n:'López Obrador',a:2019,b:2024},
   {n:'Sheinbaum',a:2025,b:META.anio_fin}].forEach(er=>{
    const i0=serie.findIndex(d=>d.anio===er.a), i1=serie.findIndex(d=>d.anio===er.b);
    if(i0<0||i1<0) return;
    const x0=x(i0)+4, x1=x(i1)+bw-4;
    svg.appendChild(el('line',{x1:x0,x2:x1,y1:26,y2:26,class:'era-rule'}));
    const t=el('text',{x:(x0+x1)/2,y:19,class:'era-txt','text-anchor':'middle'});
    t.textContent=er.n; svg.appendChild(t);
  });
  serie.forEach((d,i)=>{
    const h=(d.real/max)*ih, yy=y(d.real);
    const r=el('rect',{x:x(i)+3,y:yy,width:bw-6,height:Math.max(h,1),rx:4,
      class:'bar'+(d.anio===anioSel?' sel':'')+(esParcial(d.anio)?' parcial':''),
      tabindex:0,role:'button',
      'aria-label':d.anio+(esParcial(d.anio)?', solo de enero a '+mesesDe(d.anio):'')+
        ': '+fmt1(d.real)+' millones de pesos de 2020'});
    const info=e=>showTip(e,'<b>'+d.anio+' · '+d.sexenio+'</b><span class="n">'+fmt1(d.real)+
      '</span> MDP de 2020<br><span class="n">'+fmt1(d.nominal)+'</span> MDP nominales<br><span class="n">'+
      fmt(d.polizas)+'</span> pólizas · <span class="n">'+fmt(d.obs)+'</span> renglones'+notaParc(d.anio));
    r.addEventListener('mousemove',info);
    r.addEventListener('mouseleave',hideTip);
    r.addEventListener('click',()=>selAnio(d.anio));
    r.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();selAnio(d.anio);}});
    svg.appendChild(r);
    const v=el('text',{x:x(i)+bw/2,y:yy-8,class:'bar-val'}); v.textContent=fmt(d.real); svg.appendChild(v);
    const a=el('text',{x:x(i)+bw/2,y:H-MB+22,
      class:'axis-yr'+(esParcial(d.anio)?' parcial':''),'text-anchor':'middle'});
    a.textContent="'"+String(d.anio).slice(2)+(esParcial(d.anio)?'*':''); svg.appendChild(a);
    if(esParcial(d.anio)){
      const n=el('text',{x:x(i)+bw/2,y:H-MB+36,class:'axis-yr parcial','text-anchor':'middle',
                         'font-size':10});
      n.textContent='ene–'+mesesDe(d.anio).slice(0,3); svg.appendChild(n);
    }
  });
  const yl=el('text',{x:ML-10,y:MT-14,class:'axis-txt','text-anchor':'end'});
  yl.textContent='MDP 2020'; svg.appendChild(yl);
  credito(svg, W-MR, H-6, 'end');
}

/* El crédito va DENTRO del SVG: cualquier captura o recorte de la gráfica lo lleva. */
function credito(svg,x,y,anchor){
  const t=el('text',{x:x,y:y,class:'credito','text-anchor':anchor||'start'});
  t.textContent=AUTOR+' · Fuente: Sistema COMSOC · gob.mx/buengobierno';
  svg.appendChild(t);
}

function squarify(items,x0,y0,w,h){
  const total=items.reduce((s,d)=>s+d.v,0); if(!total) return [];
  const k=(w*h)/total, nodes=items.map(d=>Object.assign({},d,{area:d.v*k}));
  const out=[], rect={x:x0,y:y0,w:w,h:h}; let row=[];
  const worst=(rw,ln)=>{ if(!rw.length) return Infinity;
    const s=rw.reduce((a,b)=>a+b.area,0);
    const mx=Math.max.apply(null,rw.map(d=>d.area)), mn=Math.min.apply(null,rw.map(d=>d.area));
    return Math.max((ln*ln*mx)/(s*s),(s*s)/(ln*ln*mn)); };
  const flush=()=>{ const s=row.reduce((a,b)=>a+b.area,0);
    if(rect.w>=rect.h){ const rw=s/rect.h; let yy=rect.y;
      row.forEach(d=>{const dh=d.area/rw; out.push(Object.assign({},d,{x:rect.x,y:yy,w:rw,h:dh})); yy+=dh;});
      rect.x+=rw; rect.w-=rw;
    } else { const rh=s/rect.w; let xx=rect.x;
      row.forEach(d=>{const dw=d.area/rh; out.push(Object.assign({},d,{x:xx,y:rect.y,w:dw,h:rh})); xx+=dw;});
      rect.y+=rh; rect.h-=rh; }
    row=[]; };
  let i=0;
  while(i<nodes.length){
    const ln=Math.min(rect.w,rect.h); if(ln<=0) break;
    const cand=row.concat([nodes[i]]);
    if(!row.length||worst(cand,ln)<=worst(row,ln)){ row=cand; i++; } else flush();
  }
  if(row.length) flush();
  return out;
}
const tono=(v,max)=>{const r=v/max; return r>=0.50?4:r>=0.22?3:r>=0.08?2:1;};

function drawMap(svgId,bloque,etiqueta){
  const svg=document.getElementById(svgId); svg.textContent='';
  const d=bloque[String(anioSel)]; if(!d) return;
  const items=d.items.filter(t=>t.v>0);
  const max=Math.max.apply(null,items.map(t=>t.v));
  const G=2;
  /* Trama diagonal para los tramos agrupados: el color sigue codificando el monto,
     y la trama avisa que ese cuadro no es una sola entidad. */
  const defs=el('defs'), pat=el('pattern',{id:svgId+'-trama',width:6,height:6,
    patternUnits:'userSpaceOnUse',patternTransform:'rotate(45)'});
  pat.appendChild(el('rect',{width:6,height:6,fill:'none'}));
  pat.appendChild(el('line',{x1:0,y1:0,x2:0,y2:6,stroke:css('--bg'),'stroke-width':2.4,opacity:.55}));
  defs.appendChild(pat); svg.appendChild(defs);

  squarify(items,0,0,1000,452).forEach(c=>{   /* 18 unidades abajo para el crédito */
    const g=el('g',{class:'cell'});
    const esGrupo=!!c.grupo, paso=tono(c.v,max);
    const fill=css('--r'+paso), ink=css('--on-r'+paso);
    const w=Math.max(c.w-G,0), h=Math.max(c.h-G,0);
    g.appendChild(el('rect',{x:c.x+G/2,y:c.y+G/2,width:w,height:h,rx:3,fill:fill}));
    if(esGrupo) g.appendChild(el('rect',{x:c.x+G/2,y:c.y+G/2,width:w,height:h,rx:3,
      fill:'url(#'+svgId+'-trama)'}));
    if(w>46&&h>17){
      const etq=esGrupo?'Puestos '+c.n:c.n;
      const lim=Math.floor(w/5.1);
      const nombre=etq.length>lim?etq.slice(0,lim-1)+'…':etq;
      const t1=el('text',{x:c.x+6,y:c.y+16,class:'cell-name',fill:ink});
      t1.textContent=nombre; g.appendChild(t1);
      if(h>30){ const t2=el('text',{x:c.x+6,y:c.y+29,class:'cell-val',fill:ink,opacity:.85});
        t2.textContent=fmtM(c.v,true); g.appendChild(t2); }
    }
    const pct=fmtPct(100*c.v/d.total);
    const titulo=esGrupo?'Puestos '+c.n+' del ranking':c.n;
    const detalle=esGrupo?'<br>suma de '+fmt(c.grupo)+' '+etiqueta:'';
    const info=e=>showTip(e,'<b>'+titulo+'</b><span class="n">'+fmtM(c.v)+
      '</span> de 2020<br><span class="n">'+pct+'</span> del gasto de '+anioSel+detalle);
    g.addEventListener('mousemove',info);
    g.addEventListener('mouseleave',hideTip);
    svg.appendChild(g);
  });
  credito(svg,998,466,'end');
  document.getElementById(svgId==='mapInst'?'totInst':'totBen').textContent =
    fmt1(d.total)+' MDP · '+fmt(d.n_total)+' '+etiqueta;
}

function drawYears(){
  const c=document.getElementById('years');
  c.innerHTML=serie.map(d=>'<button class="yr'+(esParcial(d.anio)?' parcial':'')+
    '" data-a="'+d.anio+'" aria-pressed="'+(d.anio===anioSel)+'" title="'+
    (esParcial(d.anio)?'Solo enero–'+mesesDe(d.anio)+' de '+d.anio:d.anio)+'">'+
    d.anio+'</button>').join('');
  Array.prototype.forEach.call(c.querySelectorAll('.yr'),b=>
    b.addEventListener('click',()=>selAnio(+b.dataset.a)));
}

function tablaAnio(){
  const inst=DATA.instituciones[String(anioSel)], ben=DATA.beneficiarios[String(anioSel)];
  const n=Math.max(inst.items.length,ben.items.length); let rows='';
  for(let i=0;i<n;i++){
    const a=inst.items[i], b=ben.items[i];
    rows+='<tr><td>'+(a?a.n:'')+'</td><td>'+(a?fmt1(a.v):'')+'</td><td>'+
      (b?b.n:'')+'</td><td>'+(b?fmt1(b.v):'')+'</td></tr>';
  }
  document.getElementById('tblAnio').innerHTML=
    '<caption class="sub" style="text-align:left;margin-bottom:8px">Año '+anioSel+
    ', millones de pesos de 2020. Las dos mitades son el mismo dinero visto desde cada lado: '+
    'lo que las instituciones erogaron y lo que las empresas recibieron.</caption>'+
    '<thead><tr><th>Institución</th><th>Erogó</th>'+
    '<th>Empresa</th><th>Recibió</th></tr></thead><tbody>'+rows+'</tbody>';
}

function selAnio(a){
  anioSel=a;
  Array.prototype.forEach.call(document.querySelectorAll('.yr'),b=>
    b.setAttribute('aria-pressed',+b.dataset.a===a));
  Array.prototype.forEach.call(document.querySelectorAll('.bar'),(r,i)=>
    r.classList.toggle('sel',serie[i].anio===a));
  drawMap('mapInst',DATA.instituciones,'instituciones');
  drawMap('mapBen',DATA.beneficiarios,'empresas');
  tablaAnio();
}

(function(){
  const rows=serie.map(d=>'<tr><td>'+etqAnioLargo(d.anio)+'</td><td>'+fmt1(d.real)+'</td><td>'+fmt1(d.nominal)+
    '</td><td>'+fmt(d.polizas)+'</td><td>'+fmt(d.obs)+'</td><td style="text-align:left">'+
    d.sexenio+'</td></tr>').join('');
  document.getElementById('tblSerie').innerHTML=
    '<thead><tr><th>Año</th><th>MDP 2020</th><th>MDP nominales</th><th>Pólizas</th>'+
    '<th>Renglones</th><th style="text-align:left">Sexenio</th></tr></thead><tbody>'+rows+'</tbody>';
})();

/* ── ciclo electoral ─────────────────────────────────────────────────── */
(function(){
  const C = DATA.ciclo.filter(d=>d.vs !== null);
  const W=1000,H=300,ML=54,MR=16,MT=34,MB=44;
  const svg=document.getElementById('cCiclo');
  const max=Math.max(...C.map(d=>Math.abs(d.vs)))*1.15;
  const bw=(W-ML-MR)/C.length;
  const y=v=>MT+(H-MT-MB)*(1-(v+max)/(2*max));

  for(let k=-1;k<=1;k+=0.5){
    const v=max*k, yy=y(v);
    svg.appendChild(el('line',{x1:ML,x2:W-MR,y1:yy,y2:yy,
      class: k===0 ? 'eje-cero' : 'grid-line'}));
    const t=el('text',{x:ML-9,y:yy+4,class:'axis-txt','text-anchor':'end'});
    t.textContent=(v>0?'+':'')+v.toFixed(0)+'%'; svg.appendChild(t);
  }

  C.forEach((d,i)=>{
    const x0=ML+i*bw, yy0=y(Math.max(d.vs,0)), h=Math.abs(y(d.vs)-y(0));
    const esElec=!!d.tipo;
    const r=el('rect',{x:x0+4,y:yy0,width:bw-8,height:Math.max(h,1),rx:3,
      class:'barra-ciclo',
      fill: esElec ? 'var(--accent)' : (d.vs>=0 ? 'var(--r1)' : 'var(--otros)')});
    r.addEventListener('mousemove',e=>showTip(e,'<b>'+d.anio+
      (esElec?' · elección '+d.tipo:'')+'</b>'+
      '<span class="n">'+(d.vs>0?'+':'')+d.vs.toFixed(1)+'%</span> contra el promedio de '+
      (d.anio-1)+' y '+(d.anio+1)+'<br><span class="n">'+fmt1(d.mdp)+'</span> MDP de 2020'));
    r.addEventListener('mouseleave',hideTip);
    svg.appendChild(r);
    if(esElec){
      const v=el('text',{x:x0+bw/2,y:MT-16,class:'voto'});
      v.textContent = d.tipo==='presidencial' ? 'PRESIDENCIAL' : 'INTERMEDIA';
      v.setAttribute('font-size', d.tipo==='presidencial' ? 9 : 10);
      svg.appendChild(v);
    }
    const a=el('text',{x:x0+bw/2,y:H-MB+20,class:'axis-yr','text-anchor':'middle'});
    a.textContent="'"+String(d.anio).slice(2); svg.appendChild(a);
  });
  credito(svg,W-MR,H-6,'end');

  const el_=C.filter(d=>d.tipo), no=C.filter(d=>!d.tipo);
  const prom=a=>a.reduce((s,d)=>s+d.vs,0)/a.length;
  const pres=C.filter(d=>d.tipo==='presidencial'), inter=C.filter(d=>d.tipo==='intermedia');
  document.getElementById('cNota').textContent =
    'Los '+el_.length+' años electorales del periodo están por encima de sus vecinos. '+
    'Sin años vecinos completos, '+DATA.ciclo[0].anio+' y '+
    DATA.ciclo[DATA.ciclo.length-1].anio+' no se pueden comparar.';
  document.getElementById('cResumen').innerHTML = [
    ['+'+prom(el_).toFixed(1)+'%','Promedio de los años <b>electorales</b> contra sus vecinos'],
    [prom(no).toFixed(1)+'%','Promedio de los años <b>sin elección</b>'],
    ['+'+prom(pres).toFixed(1)+'%','Solo <b>presidenciales</b> ('+pres.map(d=>d.anio).join(' y ')+')'],
    ['+'+prom(inter).toFixed(1)+'%','Solo <b>intermedias</b> ('+inter.map(d=>d.anio).join(' y ')+')'],
  ].map(([k,v])=>'<div class="rc"><b>'+k+'</b><span>'+v+'</span></div>').join('');
})();

/* ── medios en el tiempo: nueve líneas en el mismo plano ─────────────── */
/* Nueve series no caben como nueve colores: se probó una paleta de nueve y el par
   #F62477 / #2E9E8B cae a 5.3 de ΔE bajo daltonismo, bajo el piso de 6. Así que el
   color NO carga la identidad: la cargan las etiquetas al final de cada línea, y
   el color solo marca cuál estás señalando. */
const ANIOS = serie.map(d=>d.anio);
const LW=1000, LH=430, LML=56, LMR=196, LMT=16, LMB=42;
let mDatos=[], mEsc=null;

function valoresMedio(f, modo, tot){
  return MED.serie[f].map((v,i)=> modo==='pct' ? (tot[ANIOS[i]] ? 100*v/tot[ANIOS[i]] : 0) : v);
}

function pintaMedios(){
  const modo = document.getElementById('mMedida').value;
  const tot = {}; serie.forEach(d=>tot[d.anio]=d.real);
  mDatos = MED.familias.map(f=>({f:f, v:valoresMedio(f,modo,tot)}));
  const max = Math.max.apply(null, mDatos.map(d=>Math.max.apply(null,d.v))) * 1.06;
  const x = i => LML + (LW-LML-LMR) * i/(ANIOS.length-1);
  const y = v => LMT + (LH-LMT-LMB) * (1 - (max ? v/max : 0));
  mEsc = {x:x, y:y, max:max, modo:modo};

  const svg = document.getElementById('mLineas');
  svg.textContent = '';

  for(let k=0;k<=4;k++){
    const v = max*k/4, yy = y(v);
    svg.appendChild(el('line',{x1:LML,x2:LW-LMR,y1:yy,y2:yy,class:'grid-line'}));
    const t = el('text',{x:LML-9,y:yy+4,class:'axis-txt','text-anchor':'end'});
    t.textContent = modo==='pct' ? v.toFixed(0)+'%' : fmt(v);
    svg.appendChild(t);
  }
  /* Banda sobre el año incompleto. En modo "%" la cifra es legítima —es la
     repartición de los cinco meses—; en MDP todas las líneas se desploman por el
     recorte, no por el mercado. La banda avisa en los dos casos. */
  ANIOS.forEach((a,i)=>{
    if(!esParcial(a)) return;
    const x0 = i ? (x(i-1)+x(i))/2 : x(i);
    svg.appendChild(el('rect',{x:x0,y:LMT,width:x(i)-x0+10,height:LH-LMT-LMB,
                               class:'banda-parcial'}));
  });
  ANIOS.forEach((a,i)=>{
    if(i%2 && i!==ANIOS.length-1) return;
    const t = el('text',{x:x(i),y:LH-LMB+20,
      class:'axis-yr'+(esParcial(a)?' parcial':''),'text-anchor':'middle'});
    t.textContent = "'"+String(a).slice(2)+(esParcial(a)?'*':''); svg.appendChild(t);
  });

  const gCross = el('g',{id:'mCross'}); svg.appendChild(gCross);

  mDatos.forEach((d,k)=>{
    const pts = d.v.map((v,i)=>x(i).toFixed(1)+','+y(v).toFixed(1)).join(' ');
    svg.appendChild(el('polyline',{points:pts,class:'linea',id:'ln'+k}));
  });

  /* Etiquetas al final, separadas para que no se encimen. */
  const fin = mDatos.map((d,k)=>({k:k, f:d.f, v:d.v[d.v.length-1], y:y(d.v[d.v.length-1])}))
                    .sort((a,b)=>a.y-b.y);
  const MIN=15;
  for(let i=1;i<fin.length;i++) if(fin[i].y - fin[i-1].y < MIN) fin[i].y = fin[i-1].y + MIN;
  const desborde = fin[fin.length-1].y - (LH-LMB);
  if(desborde>0) fin.forEach(o=>o.y -= desborde);

  fin.forEach(o=>{
    const yl = y(o.v);
    svg.appendChild(el('path',{d:'M'+(LW-LMR+4)+','+yl.toFixed(1)+' L'+(LW-LMR+14)+','+o.y.toFixed(1),
      class:'guia', id:'gu'+o.k}));
    const t = el('text',{x:LW-LMR+18,y:o.y+4,class:'etq-linea',id:'et'+o.k});
    t.textContent = o.f; svg.appendChild(t);
    const val = el('text',{x:LW-6,y:o.y+4,class:'etq-val','text-anchor':'end',id:'ev'+o.k});
    val.textContent = mEsc.modo==='pct' ? o.v.toFixed(1)+'%' : fmt(o.v);
    svg.appendChild(val);
  });

  const cap = el('rect',{x:LML,y:LMT,width:LW-LML-LMR,height:LH-LMT-LMB,
    fill:'transparent',id:'mCaptura'});
  svg.appendChild(cap);
  cap.addEventListener('mousemove',mueveMedios);
  cap.addEventListener('mouseleave',()=>{limpiaMedios();hideTip();});

  document.getElementById('mNota').textContent = modo==='pct'
    ? 'Nueve familias, misma escala de 0 a '+max.toFixed(0)+'% del gasto del año.'
    : 'Nueve familias, misma escala de 0 a '+fmt(max)+' millones de pesos de 2020.';
  tablaMedios(modo, tot);
}

function limpiaMedios(){
  mDatos.forEach((d,k)=>{
    const l=document.getElementById('ln'+k); if(l) l.classList.remove('act');
    const e=document.getElementById('et'+k); if(e) e.classList.remove('act');
    const g=document.getElementById('gu'+k); if(g) g.classList.remove('act');
  });
  const c=document.getElementById('mCross'); if(c) c.textContent='';
}

function mueveMedios(ev){
  if(!mEsc) return;
  const svg=document.getElementById('mLineas');
  const caja=svg.getBoundingClientRect();
  const esc=LW/caja.width;
  const px=(ev.clientX-caja.left)*esc, py=(ev.clientY-caja.top)*esc;
  const paso=(LW-LML-LMR)/(ANIOS.length-1);
  let i=Math.round((px-LML)/paso);
  i=Math.max(0,Math.min(ANIOS.length-1,i));

  let cerca=0, dmin=Infinity;
  mDatos.forEach((d,k)=>{ const dd=Math.abs(mEsc.y(d.v[i])-py); if(dd<dmin){dmin=dd;cerca=k;} });

  limpiaMedios();
  const l=document.getElementById('ln'+cerca); if(l) l.classList.add('act');
  const e=document.getElementById('et'+cerca); if(e) e.classList.add('act');
  const g=document.getElementById('gu'+cerca); if(g) g.classList.add('act');

  const gc=document.getElementById('mCross');
  gc.appendChild(el('line',{x1:mEsc.x(i),x2:mEsc.x(i),y1:LMT,y2:LH-LMB,class:'cross'}));
  mDatos.forEach((d,k)=>gc.appendChild(el('circle',{cx:mEsc.x(i),cy:mEsc.y(d.v[i]),
    r:k===cerca?4.5:2.5,class:'punto'+(k===cerca?' act':'')})));

  const orden=mDatos.map((d,k)=>({f:d.f,v:d.v[i],k:k})).sort((a,b)=>b.v-a.v);
  const fmtv = v => mEsc.modo==='pct' ? v.toFixed(1)+'%' : fmt1(v)+' MDP';
  showTip(ev,'<b>'+ANIOS[i]+'</b>'+notaParc(ANIOS[i])+orden.map(o=>
    '<div class="fl'+(o.k===cerca?' act':'')+'"><span>'+o.f+'</span><span class="n">'+
    fmtv(o.v)+'</span></div>').join(''));
}

function tablaMedios(modo, tot){
  const enc='<thead><tr><th style="text-align:left">Familia</th>'+
    ANIOS.map(a=>'<th>'+etqAnio(a)+'</th>').join('')+'</tr></thead>';
  const filas=MED.familias.map(f=>{
    const v=valoresMedio(f,modo,tot);
    return '<tr><td>'+f+'</td>'+v.map(x=>'<td>'+(modo==='pct'?x.toFixed(1):fmt1(x))+'</td>').join('')+'</tr>';
  }).join('');
  document.getElementById('tblMedios').innerHTML=enc+'<tbody>'+filas+'</tbody>';
}

document.getElementById('mMedida').addEventListener('change',pintaMedios);
pintaMedios();

/* ── treemap de campañas ────────────────────────────────────────────── */
const aniosCamp = Object.keys(CAMP).sort();
function pintaCamp(){
  const an = document.getElementById('kAnio').value;
  const d = CAMP[an]; const svg = document.getElementById('mapCamp');
  svg.textContent='';
  if(!d){ return; }
  const items = d.items, max = items[0].v, G = 2;
  document.getElementById('kCuenta').innerHTML =
    '<b>'+fmt(items.length)+'</b> campañas · <b>'+fmt1(d.total)+'</b> MDP de 2020 en '+an;
  const tonoC = v => { const r=v/max; return r>=0.50?4:r>=0.22?3:r>=0.08?2:1; };
  squarify(items,0,0,1000,452).forEach(c=>{
    const paso=tonoC(c.v);
    const g=el('g',{class:'cell'});
    const w=Math.max(c.w-G,0), h=Math.max(c.h-G,0);
    g.appendChild(el('rect',{x:c.x+G/2,y:c.y+G/2,width:w,height:h,rx:3,fill:css('--c'+paso)}));
    if(w>46&&h>17){
      const ink=css('--on-c'+paso), lim=Math.floor(w/5.1);
      const t1=el('text',{x:c.x+6,y:c.y+16,class:'cell-name',fill:ink});
      t1.textContent = c.n.length>lim ? c.n.slice(0,lim-1)+'…' : c.n;
      g.appendChild(t1);
      if(h>30){ const t2=el('text',{x:c.x+6,y:c.y+29,class:'cell-val',fill:ink,opacity:.85});
        t2.textContent=fmtM(c.v,true); g.appendChild(t2); }
    }
    const pct=fmtPct(100*c.v/d.total);
    g.addEventListener('mousemove',e=>showTip(e,'<b>'+c.n+'</b><span class="n">'+fmtM(c.v)+
      '</span> de 2020<br><span class="n">'+pct+'</span> de las campañas de '+an));
    g.addEventListener('mouseleave',hideTip);
    svg.appendChild(g);
  });
  credito(svg,998,466,'end');
}
(function initCamp(){
  document.getElementById('kAnio').innerHTML =
    aniosCamp.map(a=>'<option value="'+a+'">'+etqAnioLargo(a)+'</option>').join('');
  /* Igual que los treemaps: abre en el último año COMPLETO. En 2026 hay 8 campañas
     contra 300 de un año entero, y el cuadro se ve roto sin estarlo. */
  const ultCamp = aniosCamp.filter(a=>!esParcial(a)).pop() || aniosCamp[aniosCamp.length-1];
  document.getElementById('kAnio').value = ultCamp;
  document.getElementById('kAnio').addEventListener('change',pintaCamp);
  pintaCamp();
})();

/* ── ganadores y perdedores ─────────────────────────────────────────── */
/* GP.emp: [idxNombre, sh de cada periodo..., mdp de cada periodo...]
   Los pares se arman en el navegador para no triplicar los datos embebidos. */
const NP = GP.periodos.length;
const shDe = (f,i) => f[1+i];
const mdpDe = (f,i) => f[1+NP+i];

(function initGP(){
  const opts = [];
  for(let i=0;i<NP;i++) for(let j=i+1;j<NP;j++)
    opts.push('<option value="'+i+','+j+'">'+GP.periodos[i].etq+' vs '+GP.periodos[j].etq+'</option>');
  const sel = document.getElementById('gPar');
  sel.innerHTML = opts.join('');
  sel.value = NP>2 ? '0,1' : '0,1';
  sel.addEventListener('change',pintaGP);
  document.getElementById('gVista').addEventListener('change',pintaGP);
  pintaGP();
})();

function pintaGP(){
  const [ia,ib] = document.getElementById('gPar').value.split(',').map(Number);
  const A = GP.periodos[ia], B = GP.periodos[ib];
  const vista = document.getElementById('gVista').value;
  const esAmbos = vista === 'ambos';

  /* Un año suelto contra un promedio de seis no es comparable sin decirlo. */
  const av = document.getElementById('gAviso');
  const corto = [A,B].filter(p=>p.n < 3);
  if(corto.length){
    av.hidden = false;
    av.innerHTML = '<b>Ojo con la asimetría.</b> ' +
      corto.map(p=>p.etq+' solo tiene '+p.n+' año'+(p.n>1?'s':'')+' en los datos ('+
        (p.anios[0]===p.anios[1]?p.anios[0]:p.anios.join('–'))+')').join(' y ') +
      ', contra ' + [A,B].filter(p=>p.n>=3).map(p=>p.n+' de '+p.etq).join(' y ') +
      '. Un año suelto recoge lo que haya pasado ese año, sin promediarse con nada.';
  } else { av.hidden = true; }

  const enA = f => shDe(f,ia) > 0, enB = f => shDe(f,ib) > 0;
  const U = GP.umbral;
  let filas;
  if(esAmbos)          filas = GP.emp.filter(f=>enA(f) && enB(f) &&
                                (shDe(f,ia)>=U || shDe(f,ib)>=U));
  else if(vista==='salieron') filas = GP.emp.filter(f=>enA(f) && !enB(f));
  else                 filas = GP.emp.filter(f=>!enA(f) && enB(f));

  const dif = f => shDe(f,ib) - shDe(f,ia);
  const clave = esAmbos ? dif : (vista==='salieron' ? f=>shDe(f,ia) : f=>shDe(f,ib));
  filas = filas.slice().sort((x,y)=>clave(y)-clave(x));

  const maxDif = Math.max(0.01, ...filas.map(f=>Math.abs(dif(f))));
  const maxSh  = Math.max(0.01, ...filas.map(f=>Math.max(shDe(f,ia),shDe(f,ib))));

  const cab = esAmbos
    ? ['Empresa','Cambio de participación','pp','Millones '+A.etq,'Millones '+B.etq]
    : ['Empresa', vista==='salieron' ? 'Participación que tenía' : 'Participación que alcanzó',
       '%','Millones '+A.etq,'Millones '+B.etq];
  document.getElementById('gCab').innerHTML =
    cab.map((c,i)=>'<span'+(i>=2?' class="der"':'')+'>'+c+'</span>').join('');

  const nGana = filas.filter(f=>dif(f)>0).length;
  document.getElementById('gCuenta').innerHTML = esAmbos
    ? '<b>'+fmt(filas.length)+'</b> empresas con al menos '+U+'% de participación en alguno · <b>'+
      nGana+'</b> ganaron terreno con '+B.etq+', <b>'+(filas.length-nGana)+'</b> lo perdieron'
    : '<b>'+fmt(filas.length)+'</b> empresas presentes en '+
      (vista==='salieron' ? A.etq+' que desaparecen en '+B.etq
                          : B.etq+' que no aparecían en '+A.etq);

  document.getElementById('gLista').innerHTML = filas.map(f=>{
    const nom = T.nombres[f[0]];
    const sa = shDe(f,ia), sb = shDe(f,ib), ma = mdpDe(f,ia), mb = mdpDe(f,ib);
    let barra;
    if(esAmbos){
      const d = sb - sa, w = 50*Math.abs(d)/maxDif;
      const lado = d>=0 ? 'mas' : 'menos';
      const posx = d>=0 ? 'left:calc(50% + '+(w+1.5)+'%)' : 'right:calc(50% + '+(w+1.5)+'%)';
      barra = '<span class="dv"><i class="'+lado+'" style="width:'+w.toFixed(1)+'%"></i>'+
        '<b class="'+lado+'" style="'+posx+'">'+(d>=0?'+':'−')+Math.abs(d).toFixed(2)+'</b></span>';
    } else {
      const v = vista==='salieron' ? sa : sb;
      const w = 96*v/maxSh;
      barra = '<span class="dv" style="background:none"><i class="mas" style="left:0;width:'+
        w.toFixed(1)+'%;background:'+(vista==='salieron'?'var(--c3)':'var(--accent)')+'"></i>'+
        '<b class="mas" style="left:calc('+w.toFixed(1)+'% + 6px)">'+v.toFixed(2)+'</b></span>';
    }
    const pp = esAmbos ? ((sb-sa)>=0?'+':'−')+Math.abs(sb-sa).toFixed(2)
                       : (vista==='salieron'?sa:sb).toFixed(2);
    const tit = nom+' — '+A.etq+': '+sa.toFixed(3)+'% y '+fmtM(ma)+' al año · '+
      B.etq+': '+sb.toFixed(3)+'% y '+fmtM(mb)+' al año';
    return '<div class="gp-fila" title="'+tit.replace(/"/g,'&quot;')+'">'+
      '<span class="nombre">'+nom+'</span>'+barra+
      '<span class="num der">'+pp+'</span>'+
      '<span class="num der mdp">'+fmtM(ma,true)+'</span>'+
      '<span class="num der mdp">'+fmtM(mb,true)+'</span></div>';
  }).join('');
}

/* ── concentración de proveedores ───────────────────────────────────── */
/* Fila de CONC: [idxNombre, totalMDP, nProveedores, cr1, cr3, cr5, hhi] */
function pintaConc(){
  const met = +document.getElementById('cMetrica').value;
  const umb = +document.getElementById('cUmbral').value;
  const an  = document.getElementById('cAnio').value;
  const filas = (CONC[an]||[]).filter(f=>f[1] > umb).slice().sort((a,b)=>b[met]-a[met]);

  const maxGasto = filas.reduce((m,f)=>Math.max(m,f[1]),0);
  const cuantos = met===3?'su proveedor más grande':met===4?'sus 3 proveedores más grandes':'sus 5 proveedores más grandes';
  const mediana = filas.length ? filas[Math.floor(filas.length/2)][met] : 0;
  document.getElementById('cCuenta').innerHTML =
    filas.length
      ? '<b>'+fmt(filas.length)+'</b> instituciones · la mediana le da <b>'+
        mediana.toFixed(1)+'%</b> de su dinero a '+cuantos
      : 'Ninguna institución supera ese umbral en ese año';

  document.getElementById('cLista').innerHTML = filas.map(f=>{
    const paso = tono(f[1], maxGasto);
    const nom = T.nombres[f[0]];
    const tit = nom+' — '+f[3].toFixed(1)+'% al mayor, '+f[4].toFixed(1)+'% a los 3 mayores, '+
      f[5].toFixed(1)+'% a los 5 mayores · '+fmt(f[2])+' proveedores · '+
      fmt1(f[1])+' MDP · HHI '+fmt(f[6]);
    return '<div class="conc-fila" title="'+tit.replace(/"/g,'&quot;')+'">'+
      '<span class="nombre">'+nom+'</span>'+
      '<span class="pista"><i style="width:'+f[met].toFixed(1)+'%;background:var(--r'+paso+')"></i></span>'+
      '<span class="num fuerte der">'+f[met].toFixed(1)+'</span>'+
      '<span class="num der">'+fmt(f[2])+'</span>'+
      '<span class="num der mdp">'+fmtM(f[1],true)+'</span></div>';
  }).join('');
}

(function initConc(){
  document.getElementById('cAnio').innerHTML =
    '<option value="">Todos los años ('+RANGO+')</option>'+
    serie.map(d=>'<option value="'+d.anio+'">'+etqAnioLargo(d.anio)+'</option>').join('');
  ['cMetrica','cUmbral','cAnio'].forEach(id=>
    document.getElementById(id).addEventListener('change',pintaConc));
  pintaConc();
})();

/* ── buscador ───────────────────────────────────────────────────────── */
/* ̀-ͯ = marcas combinantes: "México" y "mexico" deben coincidir. */
const pliega = s => s.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
/* Índice de búsqueda = nombre + siglas. Se calcula una sola vez. */
const NOM_PLEGADO = T.nombres.map((n,i)=>pliega(n+' '+(T.alias[i]||'')));
const TOT_ANIO = {}; serie.forEach(d=>TOT_ANIO[d.anio]=d.real);
const POR_PAG = 50;
let orden = {col:3, dir:-1}, pagina = 0, filtradas = T.filas;

const COLS = [
  {k:'Año',   i:0, t:''},
  {k:'Tipo',  i:1, t:'Institución = erogó · Empresa = recibió'},
  {k:'Nombre',i:2, t:''},
  {k:'Erogado / recibido (MDP 2020)', i:3,
   t:'Lo que la institución pagó, o lo que la empresa cobró, en pesos constantes de 2020'},
  {k:'% del año',  i:-1, t:'Proporción del gasto federal de ese año'},
  {k:'Nominal',    i:4,  t:'El mismo monto en pesos corrientes del año'},
  {k:'Pólizas',    i:5,  t:''},
  {k:'Renglones',  i:6,  t:''},
  {k:'De la 33605',i:7,  t:'Parte del monto que corresponde a la partida 33605 (gasto operativo)'},
];

function filtrar(){
  const q = pliega(document.getElementById('q').value.trim());
  const tp = document.getElementById('fTipo').value;
  const an = document.getElementById('fAnio').value;
  filtradas = T.filas.filter(f=>{
    if(tp!=='' && f[1]!==+tp) return false;
    if(an!=='' && f[0]!==+an) return false;
    if(q && NOM_PLEGADO[f[2]].indexOf(q)<0) return false;
    return true;
  });
  const s = orden.col, d = orden.dir;
  filtradas = filtradas.slice().sort((a,b)=>{
    let va, vb;
    if(s===2){ va=NOM_PLEGADO[a[2]]; vb=NOM_PLEGADO[b[2]];
      return va<vb?-d:va>vb?d:0; }
    if(s===-1){ va=a[3]/TOT_ANIO[a[0]]; vb=b[3]/TOT_ANIO[b[0]]; }
    else { va=a[s]; vb=b[s]; }
    return (va-vb)*d;
  });
  pagina = 0;
  pintar();
}

function pintar(){
  const n = filtradas.length;
  const ini = pagina*POR_PAG, fin = Math.min(ini+POR_PAG, n);
  /* Los dos tipos son las dos caras del mismo peso: se suman por separado,
     nunca juntos, o el total sale al doble. */
  const sInst = filtradas.reduce((s,f)=>s+(f[1]===0?f[3]:0),0);
  const sEmp  = filtradas.reduce((s,f)=>s+(f[1]===1?f[3]:0),0);
  const partes = [];
  if(sInst>0) partes.push('instituciones erogaron <b>'+fmt1(sInst)+'</b> MDP');
  if(sEmp>0)  partes.push('empresas recibieron <b>'+fmt1(sEmp)+'</b> MDP');
  document.getElementById('cuenta').innerHTML =
    n ? '<b>'+fmt(n)+'</b> registros · '+partes.join(' · ')+' <span style="opacity:.7">(pesos de 2020)</span>'
      : 'Ningún resultado';

  const th = COLS.map((c,j)=>'<th data-j="'+j+'"'+(c.t?' title="'+c.t+'"':'')+
    (COLS[j].i===orden.col||(orden.col===-1&&COLS[j].i===-1)?' data-dir="'+(orden.dir>0?'asc':'desc')+'"':'')+
    '>'+c.k+'</th>').join('');
  let tb='';
  for(let i=ini;i<fin;i++){
    const f=filtradas[i];
    const pct = TOT_ANIO[f[0]] ? (100*f[3]/TOT_ANIO[f[0]]) : 0;
    tb += '<tr><td>'+f[0]+'</td><td><span class="pill '+(f[1]?'emp':'inst')+'" title="'+
      (f[1]?'Monto recibido por la empresa':'Monto erogado por la institución')+'">'+
      (f[1]?'Empresa':'Instit.')+'</span></td><td>'+T.nombres[f[2]]+'</td><td>'+
      fmtM(f[3],true)+'</td><td>'+fmtPct(pct)+'</td><td>'+fmtM(f[4],true)+'</td><td>'+
      fmt(f[5])+'</td><td>'+fmt(f[6])+'</td><td>'+(f[7]?fmtM(f[7],true):'—')+'</td></tr>';
  }
  document.getElementById('tblBusca').innerHTML = n
    ? '<thead><tr>'+th+'</tr></thead><tbody>'+tb+'</tbody>'
    : '<tbody><tr><td colspan="9" class="vacio">Prueba con otro nombre, o quita los filtros.</td></tr></tbody>';

  Array.prototype.forEach.call(document.querySelectorAll('#tblBusca th'),h=>
    h.addEventListener('click',()=>{
      const c = COLS[+h.dataset.j].i;
      if(orden.col===c) orden.dir*=-1; else { orden.col=c; orden.dir=(c===2?1:-1); }
      filtrar();
    }));

  const pags = Math.ceil(n/POR_PAG);
  document.getElementById('pag').innerHTML = pags>1
    ? '<button id="ant"'+(pagina===0?' disabled':'')+'>Anteriores</button>'+
      '<span class="idx">'+(ini+1)+'–'+fin+' de '+fmt(n)+'</span>'+
      '<button id="sig"'+(pagina>=pags-1?' disabled':'')+'>Siguientes</button>' : '';
  const a=document.getElementById('ant'), s=document.getElementById('sig');
  if(a) a.addEventListener('click',()=>{pagina--;pintar();window.scrollTo({top:document.getElementById('tblBusca').getBoundingClientRect().top+scrollY-90,behavior:'smooth'});});
  if(s) s.addEventListener('click',()=>{pagina++;pintar();window.scrollTo({top:document.getElementById('tblBusca').getBoundingClientRect().top+scrollY-90,behavior:'smooth'});});
}

(function initBusca(){
  document.getElementById('fAnio').innerHTML =
    '<option value="">Todos los años</option>'+
    serie.map(d=>'<option value="'+d.anio+'">'+etqAnioLargo(d.anio)+'</option>').join('');
  let t;
  document.getElementById('q').addEventListener('input',()=>{clearTimeout(t);t=setTimeout(filtrar,140);});
  document.getElementById('fTipo').addEventListener('change',filtrar);
  document.getElementById('fAnio').addEventListener('change',filtrar);
  filtrar();
})();

/* ── descargas ──────────────────────────────────────────────────────── */
const DICC = __DICCIONARIO__;
(function(){
  let grupo='', filas='';
  DICC.forEach(d=>{
    if(d[0]!==grupo){
      grupo=d[0];
      filas+='<tr class="grupo"><td colspan="2">'+grupo+'</td></tr>';
    }
    filas+='<tr><td><code>'+d[1]+'</code></td><td style="text-align:left">'+d[2]+'</td></tr>';
  });
  document.getElementById('tblDicc').innerHTML =
    '<thead><tr><th>Columna</th><th style="text-align:left">Qué es</th></tr></thead><tbody>'+
    filas+'</tbody>';
})();

/* Comillas dobles duplicadas y campo entrecomillado: así un nombre con coma
   —"DEMOS, DESARROLLO DE MEDIOS"— no parte la columna al abrirlo en Excel. */
const csvCampo = v => {
  const s = (v===null||v===undefined) ? '' : String(v);
  return /[",\n;]/.test(s) ? '"'+s.replace(/"/g,'""')+'"' : s;
};
function bajaCSV(nombre, cabeceras, filas){
  const txt = [cabeceras.join(',')].concat(filas.map(f=>f.map(csvCampo).join(','))).join('\r\n');
  /* BOM para que Excel en Windows reconozca el UTF-8 y no rompa los acentos. */
  const blob = new Blob(['﻿'+txt], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = nombre;
  document.body.appendChild(a); a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href); a.remove();}, 0);
}
document.getElementById('bajaAgregado').addEventListener('click',()=>{
  bajaCSV('comsoc_resumen_entidad_anio.csv',
    ['anio','tipo','nombre','erogado_o_recibido_mdp_2020','pct_del_anio',
     'mdp_nominales','polizas','renglones','de_la_partida_33605_mdp'],
    T.filas.map(f=>[f[0], f[1]?'empresa':'institucion', T.nombres[f[2]], f[3],
      TOT_ANIO[f[0]] ? (100*f[3]/TOT_ANIO[f[0]]).toFixed(3) : '', f[4], f[5], f[6], f[7]]));
});

drawBars(); drawYears(); selAnio(anioSel);
"""

DICCIONARIO = [
    # (grupo, columna, qué es)
    ("Cuándo", "anio_fuente",
     "Ejercicio fiscal que reporta el archivo. <b>Es el año que hay que usar</b> para agrupar la serie."),
    ("Cuándo", "fecha_gasto",
     "Fecha del gasto, normalizada desde los dos formatos de origen: serial de Excel en 2012–2023 y texto dd/mm/aaaa desde 2024."),
    ("Cuándo", "mes",
     "Mes que declara la fuente. No siempre coincide con el mes de <code>fecha_gasto</code>."),
    ("Cuándo", "anio · mes_gasto",
     "Derivados de <code>fecha_gasto</code>. Arrastran fechas mal capturadas por la fuente; <b>no agrupes con ellos</b>."),
    ("Cuándo", "fecha_fuera_de_rango",
     "La fecha no cae en su ejercicio. Marcada, no corregida: son 107 filas."),

    ("Quién paga", "clave_entidad · institucion",
     "Clave y nombre de la institución que pagó, tal como vienen en la fuente."),
    ("Quién paga", "institucion_canonica",
     "Institución homologada. <b>Úsala para agrupar</b>: la fuente escribe el mismo nombre de varias formas y desde 2024 dejó de poner el acrónimo."),
    ("Quién paga", "sector · tipo_institucion",
     "Sector presupuestal y tipo de ente. El sector cambió de códigos numéricos a nombres de ramo en 2024; <code>tipo_institucion</code> desapareció ese año."),

    ("Quién cobra", "beneficiario · beneficiario_canonico",
     "Proveedor que recibió el pago, crudo y homologado."),
    ("Quién cobra", "rfc_beneficiario",
     "RFC del proveedor. Solo existe en <b>2012–2016 y 2024–2025</b>; es la llave dura para resolver dudas de agrupación."),
    ("Quién cobra", "persona",
     "Si el proveedor es persona física o moral."),
    ("Quién cobra", "clase_beneficiario",
     "Código de clase del proveedor. Solo 2012–2023: en 2024 la columna con ese nombre pasó a traer el tipo de medio."),

    ("Qué se compró", "medio_familia",
     "Familia de medio: Televisión, Radio, Diarios, Internet, Exterior, Revistas, Cine, Producción y servicios, Otros. Derivada de <code>producto_clave</code> con <code>config/medios.csv</code>."),
    ("Qué se compró", "medio_producto",
     "Producto concreto dentro de la familia, con nombre limpio: «Televisión abierta nacional», «Mobiliario urbano», «Internet»…"),
    ("Qué se compró", "producto_clave",
     "Clave del catálogo de productos de la fuente, 37 valores. <b>Es el campo estable</b>: está completo en los 14 años."),
    ("Qué se compró", "producto_desc",
     "Descripción del producto tal como la escribió la fuente. Tiene ruido: la clave 21 aparece con 17 redacciones distintas."),
    ("Qué se compró", "clase_medio",
     "Tipo de medio según la fuente. <b>Solo 2024–2025</b>; para la serie completa usa <code>medio_familia</code>."),
    ("Qué se compró", "unidad · unidad_desc",
     "Unidad de medida de la inserción (plana, spot, millar de impresiones…)."),
    ("Qué se compró", "cantidad · costo_unitario",
     "Cuántas unidades y a qué precio unitario. Sirven para detectar precios atípicos."),

    ("Cuánto", "monto · iva",
     "Pago al proveedor sin IVA, y su IVA."),
    ("Cuánto", "monto_total",
     "<code>monto + iva</code>. El gasto nominal del renglón."),
    ("Cuánto", "monto_real",
     "<code>monto_total</code> deflactado a pesos de 2020. <b>Úsalo para comparar entre años.</b>"),
    ("Cuánto", "deflactor_pib_2020_100 · anio_base",
     "Factor aplicado y su año base. Deflactor implícito del PIB, FUNDAR."),
    ("Cuánto", "deflactor_estimado",
     "1 si el factor de ese año todavía es estimado: 2025 y 2026."),
    ("Cuánto", "importe_factura · iva_factura",
     "Vacías en esta descarga. Son el nivel factura, que se separó para reconciliar (ver «las dos filas por póliza»)."),

    ("Documento", "poliza · poliza_id",
     "Número de póliza de la fuente, y su identificador estable: hash de año + grupo de partida + entidad + póliza."),
    ("Documento", "renglon_id",
     "Identificador único de cada renglón en todo el dataset. <b>Es la llave al unir tablas.</b>"),
    ("Documento", "n_renglones",
     "Cuántos renglones tiene la póliza a la que pertenece esta fila."),
    ("Documento", "consecutivo · ocurrencia",
     "Número de renglón dentro de la póliza, y el desempate interno entre filas idénticas."),
    ("Documento", "tipo_poliza",
     "«Normal» o «Intercambio». Solo desde 2024."),
    ("Documento", "contrato · fecha_contrato",
     "Contrato o pedido que ampara el gasto, y su fecha."),
    ("Documento", "fila_num",
     "El «Núm.» del reporte de 2025. Es un índice de presentación: cambia con cada republicación, <b>no lo uses como identificador</b>."),

    ("Campaña", "campana_clave",
     "Clave de la campaña. Existe en toda la serie, pero es opaca: <code>091/22-2001-TC18-00625</code>."),
    ("Campaña", "campana_nombre",
     "Nombre de la campaña. <b>Solo desde 2024</b>: antes la fuente no lo publica."),

    ("Partida", "partida",
     "36101 y 36201 son difusión de campañas; 33605 es información en medios derivada de la operación."),
    ("Partida", "partida_grupo",
     "<code>36101-36201</code> o <code>33605</code>, la agrupación con la que la fuente organiza sus hojas. Repórtalas separadas: su naturaleza es distinta."),

    ("Banderas", "vintage",
     "<code>definitiva</code> o <code>preliminar</code>. 2023 tiene dos ediciones; <b>filtra a definitiva</b> salvo que quieras compararlas."),
    ("Banderas", "nivel_registro",
     "Siempre <code>renglon</code> en esta descarga."),
    ("Banderas", "es_reversa",
     "Contra-asiento con monto negativo. <b>Súmalo con signo</b>; excluirlo infla el total."),
    ("Banderas", "es_intercambio · intercambio",
     "Publicidad pagada en especie, no en dinero. Conviene reportarla aparte del gasto."),
    ("Banderas", "n_identicas",
     "Tamaño del grupo de filas idénticas. Hay 9,036 filas duplicadas en el histórico que <b>no</b> se eliminaron a ciegas."),

    ("Rastro", "archivo · hoja · generacion",
     "De qué Excel y qué pestaña salió cada fila, y con qué formato se leyó. Es el rastro de auditoría: permite volver al origen de cualquier cifra."),
    ("Rastro", "notas",
     "Notas aclaratorias de la fuente. Es donde a veces aparece el medio real de una compra hecha a través de una agencia. <b>Desaparece en 2024.</b>"),
]

AUTOR = "Manuel Toral"
URL_COMSOC = "https://www.gob.mx/buengobierno/documentos/estrategia-de-comunicacion-social"
TITULO = "Publicidad oficial federal &middot; COMSOC __RANGO__"
DESCRIPCION = ("Gasto del gobierno federal mexicano en publicidad oficial, __RANGO__, "
               "reconstruido desde el detalle de polizas del sistema COMSOC. "
               f"Elaborado por {AUTOR}.")

CARDINALES = {12: "Doce", 13: "Trece", 14: "Catorce", 15: "Quince", 16: "Dieciséis",
              17: "Diecisiete", 18: "Dieciocho", 19: "Diecinueve", 20: "Veinte"}


def _textos_cobertura(meta: dict) -> dict[str, str]:
    """Las frases que dependen de hasta dónde llegan los datos.

    Se arman aquí y no en el HTML porque el año más reciente casi siempre estará
    incompleto: la Secretaría publica cortes parciales durante el año y el
    definitivo hasta el siguiente. Escribirlo a mano garantiza que se quede viejo.
    """
    ini, fin = meta["anio_ini"], meta["anio_fin"]
    parc = meta["parciales"]
    n = meta["n_completos"]
    cardinal = CARDINALES.get(n, str(n))

    social = "de gasto federal en comunicaci&oacute;n social"
    if not parc:
        return {"__RANGO__": f"{ini}–{fin}",
                "__COBERTURA__": f"{cardinal} ejercicios fiscales {social},",
                "__AVISO__": "", "__AVISO_CORTO__": ""}

    hasta = parc[str(fin)]["hasta"]
    return {
        "__RANGO__": f"{ini}–{fin}",
        "__COBERTURA__": (f"{cardinal} ejercicios fiscales completos {social}, "
                          f"m&aacute;s el arranque de {fin},"),
        "__AVISO__": (
            f'<p class="aviso cobertura" role="note"><b>{fin} va s&oacute;lo de enero a {hasta}.</b> '
            f"El archivo de la Secretar&iacute;a corta el 15 de junio de {fin}, as&iacute; que "
            f"la barra de {fin} son cinco meses, no un a&ntilde;o. No la compares contra los "
            f"a&ntilde;os completos: el gasto se registra sobre todo al cierre del ejercicio "
            f"&mdash;entre 2012 y {meta['anio_fin_completo']}, enero&ndash;mayo signific&oacute; "
            f"entre 0.3% y 13.1% del a&ntilde;o&mdash;, de modo que un arranque bajo es lo normal "
            f"y no una ca&iacute;da. Por eso {fin} queda fuera del ciclo electoral y de la "
            f"comparaci&oacute;n entre sexenios, donde s&iacute; distorsionar&iacute;a la cuenta.</p>"),
        "__AVISO_CORTO__": (
            f'<li class="flag"><b>{fin} est&aacute; incompleto.</b> El archivo de la fuente '
            f"corta el 15 de junio y cubre solo enero&ndash;{hasta}. Aparece con "
            f"<b>trama diagonal</b> en la gr&aacute;fica de barras y con asterisco en los ejes "
            f"y los selectores, y queda fuera del ciclo electoral y de la comparaci&oacute;n "
            f"entre sexenios. Los treemaps y el buscador s&iacute; lo incluyen: ah&iacute; cada "
            f"a&ntilde;o se lee por separado.</li>"),
    }


def _fragmento(datos: dict) -> str:
    from .export import tamanos_descargas

    pesos = tamanos_descargas()
    cuerpo = (CUERPO
              .replace("__PESO_CSV__", str(pesos.get("comsoc_polizas_csv.zip", "~16")))
              .replace("__PESO_PARQUET__", str(pesos.get("comsoc_polizas.parquet", "~12")))
              .replace("__RENGLONES__", f"{datos['meta']['renglones']:,}")
              .replace("__COLUMNAS__", str(datos["meta"]["columnas"]))
              .replace("__POLIZAS__", f"{datos['meta']['polizas']:,}")
              .replace("__TOP__", str(PANELES["beneficiarios"]["top"]))
              .replace("__FILAS__", f"{len(datos['tabla']['filas']):,}")
              .replace("__ENTIDADES__", f"{len(datos['tabla']['nombres']):,}")
              .replace("__URL_COMSOC__", URL_COMSOC)
              .replace("__AUTOR__", AUTOR))
    for marca, texto in _textos_cobertura(datos["meta"]).items():
        cuerpo = cuerpo.replace(marca, texto)
    guion = (GUION
             .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
             .replace("__DICCIONARIO__",
                      json.dumps(DICCIONARIO, ensure_ascii=False, separators=(",", ":")))
             .replace("__AUTOR__", AUTOR))
    titulo = TITULO.replace("__RANGO__", _textos_cobertura(datos["meta"])["__RANGO__"])
    return f"<title>{titulo}</title>\n<style>{ESTILO}</style>\n{cuerpo}\n<script>{guion}</script>\n"


FAVICON = (
    "data:image/svg+xml,"
    "<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 32 32%22>"
    "<rect width=%2232%22 height=%2232%22 rx=%226%22 fill=%22%23FBF5E6%22/>"
    "<rect x=%225%22 y=%2216%22 width=%225%22 height=%2211%22 fill=%22%23F62477%22/>"
    "<rect x=%2213%22 y=%229%22 width=%225%22 height=%2218%22 fill=%22%2392003A%22/>"
    "<rect x=%2221%22 y=%2213%22 width=%225%22 height=%2214%22 fill=%22%23F62477%22/>"
    "</svg>"
)


def construir(destino: Path | None = None, fragmento: bool = False) -> Path:
    asegurar_directorios()
    df = pd.read_parquet(POLIZAS_PARQUET)
    datos = construir_datos(df)
    frag = _fragmento(datos)

    if fragmento:
        ruta = destino or (DOCS_DIR / "_fragmento.html")
        ruta.write_text(frag, encoding="utf-8")
    else:
        ruta = destino or (DOCS_DIR / "index.html")
        # <title>/<style> van en head; el marcado y el script, en body
        cabeza, _, resto = frag.partition("</style>")
        html = (
            "<!DOCTYPE html>\n"
            '<html lang="es">\n<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="description" content="'
            f'{DESCRIPCION.replace("__RANGO__", _textos_cobertura(datos["meta"])["__RANGO__"])}">\n'
            f'<meta name="author" content="{AUTOR}">\n'
            '<meta name="color-scheme" content="light">\n'
            f'<link rel="icon" href="{FAVICON}">\n'
            + cabeza + "</style>\n</head>\n<body>\n" + resto.lstrip() + "</body>\n</html>\n"
        )
        ruta.write_text(html, encoding="utf-8")

    print(f"  {ruta}  ({ruta.stat().st_size / 1024:.0f} KB)")
    return ruta


def main() -> None:
    p = argparse.ArgumentParser(description="Genera el reporte HTML autocontenido")
    p.add_argument("--fragmento", action="store_true",
                   help="emite solo el contenido, sin <html>/<head>/<body>")
    p.add_argument("--salida", type=Path, default=None)
    args = p.parse_args()
    construir(destino=args.salida, fragmento=args.fragmento)


if __name__ == "__main__":
    main()
