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

import pandas as pd

from .config import DOCS_DIR, POLIZAS_PARQUET, asegurar_directorios

# Entidades con cuadro propio por año, y cortes para partir la cola.
#
# El resto NO se agrupa en un solo bloque opaco: se parte en tramos de posición.
# La cola de empresas es larguísima —al cortar en 30, "Otros" vale entre 21% y 39%
# del año, hasta 449 empresas en 2025— y un cuadro de ese tamaño esconde
# justamente lo que interesa ver. La de instituciones es corta (2%–10%), así que
# le basta un corte.
PANELES = {
    "instituciones": {"campo": "institucion_canonica", "top": 30, "cortes": [60]},
    "beneficiarios": {"campo": "beneficiario_canonico", "top": 30, "cortes": [75, 150, 300]},
}


# ─────────────────────────────────────────────────────────────── datos

def construir_datos(df: pd.DataFrame) -> dict:
    b = df[(df.vintage == "definitiva") & (~df.es_intercambio)]

    def treemap(campo: str, top: int, cortes: list[int]) -> dict:
        out = {}
        for anio, g in b.groupby("anio_fuente"):
            s = (g.groupby(campo)["monto_real"].sum() / 1e6).sort_values(ascending=False)
            s = s[s > 0]
            items = [{"n": str(k), "v": round(float(v), 1)} for k, v in s.head(top).items()]

            # La cola se parte en tramos de posición en vez de un solo "Otros".
            for ini, fin in zip([top] + cortes, cortes + [len(s)]):
                tramo = s.iloc[ini:fin]
                if not len(tramo) or tramo.sum() <= 0:
                    continue
                items.append({
                    "n": f"{ini + 1}–{min(fin, len(s))}",
                    "v": round(float(tramo.sum()), 1),
                    "grupo": int(len(tramo)),
                })

            out[str(int(anio))] = {"items": items, "total": round(float(s.sum()), 1),
                                   "n_total": int(len(s))}
        return out

    a = b.groupby("anio_fuente").agg(real=("monto_real", "sum"), nominal=("monto_total", "sum"),
                                     obs=("renglon_id", "size"), polizas=("poliza_id", "nunique"))

    def sexenio(y):
        return "EPN" if y <= 2018 else ("AMLO" if y <= 2024 else "Sheinbaum")

    serie = [{"anio": int(y), "real": round(float(r.real / 1e6), 1),
              "nominal": round(float(r.nominal / 1e6), 1), "obs": int(r.obs),
              "polizas": int(r.polizas), "sexenio": sexenio(y)} for y, r in a.iterrows()]

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
            filas.append((int(r.anio_fuente), tipo, r[1], round(r.real / 1e6, 2),
                          round(r.nominal / 1e6, 2), int(r.pol), int(r.ren),
                          round(r.op / 1e6, 2)))
    nom = sorted(nombres)
    ind = {n: i for i, n in enumerate(nom)}

    # Siglas para el buscador. La homologación quita el acrónimo final —"(IMSS)"—
    # porque la fuente dejó de escribirlo en 2024 y partía 109 instituciones en dos.
    # Pero la gente busca por siglas, así que se conservan aparte: no se muestran,
    # solo se indexan.
    siglas: dict[str, set[str]] = {}
    for crudo, canon in zip(b["institucion"], b["institucion_canonica"]):
        if not isinstance(crudo, str):
            continue
        for m in re.findall(r"\(([^)]{2,14})\)", crudo):
            m = m.strip()
            if m and m.upper() == m and m not in canon:
                siglas.setdefault(canon, set()).add(m)
    alias = [" ".join(sorted(siglas.get(n, ()))) for n in nom]

    tabla = {"nombres": nom, "alias": alias,
             "filas": [[f[0], f[1], ind[f[2]], f[3], f[4], f[5], f[6], f[7]] for f in filas]}

    return {"serie": serie,
            "instituciones": treemap(**PANELES["instituciones"]),
            "beneficiarios": treemap(**PANELES["beneficiarios"]),
            "tabla": tabla,
            "meta": {"renglones": int(len(b)), "polizas": int(b.poliza_id.nunique()),
                     "total_real": round(float(b.monto_real.sum() / 1e6), 1)}}


# ─────────────────────────────────────────────────────────────── plantilla

ESTILO = """
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

.maps{display:grid;grid-template-columns:1fr;gap:22px}
.map-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:12px}
.map-head h3{font-family:var(--font-display);font-size:19px;font-weight:700;margin:0}
.map-head .tot{font-family:var(--font-mono);font-size:12.5px;color:var(--ink-2);
  font-variant-numeric:tabular-nums}
.cell{transition:opacity .12s ease}
.cell:hover{opacity:.84}
.cell-name{font-family:var(--font-body);font-size:10.5px;font-weight:600;pointer-events:none}
.cell-val{font-family:var(--font-mono);font-size:9.5px;pointer-events:none;font-variant-numeric:tabular-nums}

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
  <h1>Publicidad oficial,<br><em>2012&ndash;2025</em></h1>
  <p class="lede">
    Catorce ejercicios fiscales de gasto federal en comunicaci&oacute;n social, reconstruidos
    desde el detalle de p&oacute;lizas: __RENGLONES__ renglones de __POLIZAS__ p&oacute;lizas.
    Todas las cifras en <b>millones de pesos constantes de 2020</b>.
  </p>
  <p class="byline">An&aacute;lisis y elaboraci&oacute;n de <b>__AUTOR__</b></p>

  <div class="stats" id="stats"></div>

  <section>
    <h2>El gasto total por a&ntilde;o</h2>
    <p class="sub">Cada barra es el gasto federal del ejercicio, deflactado.
      Da clic en una barra para cambiar el a&ntilde;o de los treemaps de abajo.</p>
    <div class="card">
      <div class="chart-scroll"><svg id="bars" viewBox="0 0 1000 400" role="img"
        aria-label="Gasto federal en publicidad oficial por a&ntilde;o, 2012 a 2025, en millones de pesos de 2020"></svg></div>
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
      <li><b>2025 usa un deflactor estimado.</b> La serie del deflactor impl&iacute;cito del PIB
        (base 2020=100) marca 2025 y 2026 como estimados; la cifra real de 2025 puede moverse.</li>
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
const fmt  = n => n.toLocaleString('es-MX',{maximumFractionDigits:0});
const fmt1 = n => n.toLocaleString('es-MX',{minimumFractionDigits:1,maximumFractionDigits:1});
const css  = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const S='http://www.w3.org/2000/svg';
const el=(t,a={})=>{const e=document.createElementNS(S,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const serie = DATA.serie;
let anioSel = serie[serie.length-1].anio;

(function(){
  const y18=serie.find(d=>d.anio===2018).real, y19=serie.find(d=>d.anio===2019).real;
  const y23=serie.find(d=>d.anio===2023).real, y25=serie.find(d=>d.anio===2025).real;
  const items=[
    {k:fmt(DATA.meta.total_real), l:'Gasto federal acumulado 2012–2025', u:'millones de pesos de 2020'},
    {k:((y19/y18-1)*100).toFixed(1)+'%', l:'Cayó el gasto de 2018 a 2019', u:'medido en pesos de 2020'},
    {k:'+'+((y25/y23-1)*100).toFixed(1)+'%', l:'Subió el gasto de 2023 a 2025', u:'medido en pesos de 2020'},
    {k:fmt(DATA.meta.polizas), l:'Pólizas analizadas', u:fmt(DATA.meta.renglones)+' renglones'}];
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

const W=1000,H=400,ML=64,MR=16,MT=54,MB=52;
function drawBars(){
  const svg=document.getElementById('bars'); svg.textContent='';
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
   {n:'Sheinbaum',a:2025,b:2025}].forEach(er=>{
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
      class:'bar'+(d.anio===anioSel?' sel':''),tabindex:0,role:'button',
      'aria-label':d.anio+': '+fmt1(d.real)+' millones de pesos de 2020'});
    const info=e=>showTip(e,'<b>'+d.anio+' · '+d.sexenio+'</b><span class="n">'+fmt1(d.real)+
      '</span> MDP de 2020<br><span class="n">'+fmt1(d.nominal)+'</span> MDP nominales<br><span class="n">'+
      fmt(d.polizas)+'</span> pólizas · <span class="n">'+fmt(d.obs)+'</span> renglones');
    r.addEventListener('mousemove',info);
    r.addEventListener('mouseleave',hideTip);
    r.addEventListener('click',()=>selAnio(d.anio));
    r.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();selAnio(d.anio);}});
    svg.appendChild(r);
    const v=el('text',{x:x(i)+bw/2,y:yy-8,class:'bar-val'}); v.textContent=fmt(d.real); svg.appendChild(v);
    const a=el('text',{x:x(i)+bw/2,y:H-MB+22,class:'axis-yr','text-anchor':'middle'});
    a.textContent="'"+String(d.anio).slice(2); svg.appendChild(a);
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
        t2.textContent=fmt1(c.v); g.appendChild(t2); }
    }
    const pct=(100*c.v/d.total).toFixed(1);
    const titulo=esGrupo?'Puestos '+c.n+' del ranking':c.n;
    const detalle=esGrupo?'<br>suma de '+fmt(c.grupo)+' '+etiqueta:'';
    const info=e=>showTip(e,'<b>'+titulo+'</b><span class="n">'+fmt1(c.v)+
      '</span> MDP de 2020<br><span class="n">'+pct+'%</span> del gasto de '+anioSel+detalle);
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
  c.innerHTML=serie.map(d=>'<button class="yr" data-a="'+d.anio+'" aria-pressed="'+
    (d.anio===anioSel)+'">'+d.anio+'</button>').join('');
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
  const rows=serie.map(d=>'<tr><td>'+d.anio+'</td><td>'+fmt1(d.real)+'</td><td>'+fmt1(d.nominal)+
    '</td><td>'+fmt(d.polizas)+'</td><td>'+fmt(d.obs)+'</td><td style="text-align:left">'+
    d.sexenio+'</td></tr>').join('');
  document.getElementById('tblSerie').innerHTML=
    '<thead><tr><th>Año</th><th>MDP 2020</th><th>MDP nominales</th><th>Pólizas</th>'+
    '<th>Renglones</th><th style="text-align:left">Sexenio</th></tr></thead><tbody>'+rows+'</tbody>';
})();

/* ── buscador ───────────────────────────────────────────────────────── */
const T = DATA.tabla;
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
      fmt1(f[3])+'</td><td>'+pct.toFixed(2)+'%</td><td>'+fmt1(f[4])+'</td><td>'+
      fmt(f[5])+'</td><td>'+fmt(f[6])+'</td><td>'+(f[7]?fmt1(f[7]):'—')+'</td></tr>';
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
    '<option value="">Todos los años</option>'+serie.map(d=>'<option value="'+d.anio+'">'+d.anio+'</option>').join('');
  let t;
  document.getElementById('q').addEventListener('input',()=>{clearTimeout(t);t=setTimeout(filtrar,140);});
  document.getElementById('fTipo').addEventListener('change',filtrar);
  document.getElementById('fAnio').addEventListener('change',filtrar);
  filtrar();
})();

drawBars(); drawYears(); selAnio(anioSel);
"""

AUTOR = "Manuel Toral"
URL_COMSOC = "https://www.gob.mx/buengobierno/documentos/estrategia-de-comunicacion-social"
TITULO = "Publicidad oficial federal &middot; COMSOC 2012–2025"
DESCRIPCION = ("Gasto del gobierno federal mexicano en publicidad oficial, 2012-2025, "
               "reconstruido desde el detalle de polizas del sistema COMSOC. "
               f"Elaborado por {AUTOR}.")


def _fragmento(datos: dict) -> str:
    cuerpo = (CUERPO
              .replace("__RENGLONES__", f"{datos['meta']['renglones']:,}")
              .replace("__POLIZAS__", f"{datos['meta']['polizas']:,}")
              .replace("__TOP__", str(PANELES["beneficiarios"]["top"]))
              .replace("__FILAS__", f"{len(datos['tabla']['filas']):,}")
              .replace("__ENTIDADES__", f"{len(datos['tabla']['nombres']):,}")
              .replace("__URL_COMSOC__", URL_COMSOC)
              .replace("__AUTOR__", AUTOR))
    guion = (GUION
             .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
             .replace("__AUTOR__", AUTOR))
    return f"<title>{TITULO}</title>\n<style>{ESTILO}</style>\n{cuerpo}\n<script>{guion}</script>\n"


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
            f'<meta name="description" content="{DESCRIPCION}">\n'
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
