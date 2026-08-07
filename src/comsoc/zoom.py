"""Treemap jerárquico con zoom: instituciones -> empresas que les cobraron.

    python -m comsoc.zoom      -> docs/quien-paga-a-quien.html

Página independiente del reporte completo. Ocupa la pantalla: cada caja es una
institución, y al darle clic las empresas que recibieron su dinero crecen desde
esa misma caja hasta llenar el lienzo.

La animación interpola las coordenadas de cada celda —no un `transform` sobre el
grupo— para que el texto no se deforme al escalar y para no depender de cómo cada
navegador resuelve `transform-box` en SVG.

Se embarca el cruce completo institución x empresa x año, 46,548 tripletas, sin
recortar la cola: 902 KB que GitHub Pages sirve como ~248 KB con gzip. Truncar
habría escondido justo lo que hace interesante el zoom (el IMSS le pagó a 717
empresas distintas).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .config import DOCS_DIR, POLIZAS_PARQUET, asegurar_directorios
from .reporte import AUTOR, FAVICON, TOKENS, URL_COMSOC, alias_busqueda

TITULO = "¿Qui&eacute;n le paga a qui&eacute;n? &middot; Publicidad oficial federal"
DESCRIPCION = ("Treemap interactivo del gasto federal mexicano en publicidad oficial: "
               "cada caja es una institucion; al darle clic se abren las empresas que "
               "recibieron su dinero. Elaborado por " + AUTOR + ".")


def construir_datos(df: pd.DataFrame) -> dict:
    b = df[(df.vintage == "definitiva") & (~df.es_intercambio)]

    par = (b.groupby(["anio_fuente", "institucion_canonica", "beneficiario_canonico"],
                     observed=True)["monto_real"].sum().reset_index())
    # 2 decimales de MDP = 10 mil pesos. Más precisión no cambia ningún cuadro y sí
    # engorda el archivo. Se redondea ANTES de filtrar: al revés, los montos menores
    # a 5 mil pesos quedan en 0.00 y meten celdas de área cero, que hacen dividir
    # entre cero al squarify.
    par = par.assign(mdp=(par.monto_real / 1e6).round(2))
    descartados = int((par.mdp <= 0).sum())
    par = par[par.mdp > 0]

    nombres = sorted(set(par.institucion_canonica) | set(par.beneficiario_canonico))
    ix = {v: i for i, v in enumerate(nombres)}

    # [anio, idxInstitucion, idxEmpresa, monto en MDP]
    filas = [[int(r.anio_fuente), ix[r.institucion_canonica], ix[r.beneficiario_canonico],
              float(r.mdp)] for r in par.itertuples(index=False)]
    if descartados:
        print(f"  [nota] {descartados:,} pares por debajo de 10 mil pesos: no se dibujan")

    # Palabras extra para el buscador: sin esto, `imss` y `lotería` no encuentran
    # nada, porque la homologación quita el acrónimo y renombra a LOTENAL.
    siglas = alias_busqueda(b, "institucion", "institucion_canonica")
    alias = [siglas.get(n, "") for n in nombres]

    anios = sorted(par.anio_fuente.unique().astype(int).tolist())
    return {"nombres": nombres, "alias": alias, "filas": filas, "anios": anios,
            "meta": {"instituciones": int(b.institucion_canonica.nunique()),
                     "empresas": int(b.beneficiario_canonico.nunique()),
                     "total": round(float(b.monto_real.sum() / 1e6), 1)}}


ESTILO = TOKENS + """
/* Segunda rampa, ámbar, para el nivel de empresas: al bajar cambia el color y se
   nota que cambiaste de nivel, no solo de cajas.
   Elegida sobre verde azulado y ciruela porque es la única que pasa el criterio
   ordinal sobre el fondo crema (ΔL 0.088/0.091/0.081, paso claro a 2.38 de
   contraste) y a la vez es la más separable de la rampa rosa: ΔE 14.9 en visión
   normal y 5.5 bajo daltonismo, contra 9.7 de la ciruela.
   El verde azulado quedaba en 1.80 de contraste, por debajo del piso de 2.0. */
:root{
  --a1:#D8930F; --a2:#B8790A; --a3:#966006; --a4:#7A4A02;
  --on-a1:#331018; --on-a2:#331018; --on-a3:#FFFCF4; --on-a4:#FFFCF4;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font-body);
  -webkit-font-smoothing:antialiased;display:flex;flex-direction:column;overflow:hidden}
@media (max-width:720px){body{overflow:auto}}

header{padding:16px 22px 12px;border-bottom:1px solid var(--line-2);flex:0 0 auto;
  display:flex;flex-wrap:wrap;gap:14px 22px;align-items:flex-end;background:var(--surface)}
.tit{flex:1 1 320px;min-width:0}
h1{font-family:var(--font-display);font-weight:700;letter-spacing:-.015em;
  font-size:clamp(21px,2.6vw,31px);line-height:1.05;margin:0}
h1 em{font-style:normal;color:var(--accent-deep)}
.sub{margin:5px 0 0;font-size:13.5px;color:var(--ink-2);max-width:62ch}
.ctrl{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
select,button.btn{font-family:var(--font-body);font-size:14px;padding:8px 13px;border-radius:10px;
  border:1px solid var(--line-2);background:var(--surface);color:var(--ink);cursor:pointer}
select:focus,button.btn:focus-visible{border-color:var(--accent);outline:none}
button.btn:hover{border-color:var(--accent);color:var(--accent-deep)}
button.btn[hidden]{display:none}

.busca{position:relative;display:flex;align-items:center;min-width:238px}
.busca input{width:100%;font-family:var(--font-body);font-size:14px;padding:8px 12px 8px 34px;
  border-radius:10px;border:1px solid var(--line-2);background:var(--surface);color:var(--ink)}
.busca input::placeholder{color:var(--ink-3)}
.busca input:focus{border-color:var(--accent);outline:none;
  box-shadow:0 0 0 3px rgba(246,36,119,.14)}
.busca .lupa{position:absolute;left:11px;width:15px;height:15px;stroke:var(--ink-3);
  fill:none;stroke-width:2;pointer-events:none}
#sug{position:absolute;top:calc(100% + 5px);left:0;right:0;z-index:70;margin:0;padding:5px;
  list-style:none;background:var(--surface);border:1px solid var(--line-2);border-radius:11px;
  box-shadow:0 10px 30px rgba(51,16,24,.16);max-height:min(58vh,380px);overflow-y:auto}
#sug[hidden]{display:none}
#sug li{padding:8px 10px;border-radius:8px;cursor:pointer;font-size:13.5px;color:var(--ink-2);
  display:flex;justify-content:space-between;gap:10px;align-items:baseline}
#sug li .mdp{font-family:var(--font-mono);font-size:12px;color:var(--ink-3);
  font-variant-numeric:tabular-nums;white-space:nowrap}
#sug li[aria-selected="true"],#sug li:hover{background:var(--surface-2);color:var(--ink)}
#sug li.vacio{color:var(--ink-3);cursor:default;justify-content:flex-start}

.ruta{padding:9px 22px;border-bottom:1px solid var(--line);flex:0 0 auto;background:var(--surface-2);
  display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;min-height:40px}
.ruta .paso{font-family:var(--font-display);font-size:14px;font-weight:700;color:var(--ink)}
.ruta .sep{color:var(--ink-3)}
.ruta .cifra{font-family:var(--font-mono);font-size:13px;color:var(--ink-2);
  font-variant-numeric:tabular-nums}
.ruta .pista{font-size:13px;color:var(--ink-3)}
.ruta a{color:var(--accent-deep);cursor:pointer;text-decoration:none;border-bottom:1px solid var(--line-2)}
.ruta a:hover{border-color:var(--accent)}

#lienzo{flex:1 1 auto;min-height:0;position:relative}
@media (max-width:720px){#lienzo{height:78vh}}
svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.cel rect{stroke:var(--bg);stroke-width:2;transition:filter .12s ease}
.cel.click{cursor:pointer}
.cel.click:hover rect{filter:brightness(1.08)}
.cel text{pointer-events:none;font-weight:600}
.nom{font-family:var(--font-body)}
.val{font-family:var(--font-mono);font-variant-numeric:tabular-nums;opacity:.88}

footer{padding:9px 22px;border-top:1px solid var(--line);flex:0 0 auto;background:var(--surface);
  font-size:11.5px;color:var(--ink-3);display:flex;gap:16px;flex-wrap:wrap;justify-content:space-between}
footer b{color:var(--accent-deep)}
footer a{color:var(--ink-2)}

#tip{position:fixed;pointer-events:none;opacity:0;transition:opacity .1s ease;z-index:60;
  background:var(--ink);color:var(--surface);padding:9px 12px;border-radius:9px;
  font-size:12.5px;line-height:1.45;max-width:300px;box-shadow:0 6px 20px rgba(51,16,24,.26)}
#tip b{font-family:var(--font-display);font-size:13.5px;display:block;margin-bottom:2px}
#tip .n{font-family:var(--font-mono);font-variant-numeric:tabular-nums}

:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (prefers-reduced-motion:reduce){*{transition:none !important}}
"""

CUERPO = """
<header>
  <div class="tit">
    <h1>&iquest;Qui&eacute;n le paga <em>a qui&eacute;n</em>?</h1>
    <p class="sub">Gasto federal en publicidad oficial. Cada caja es una instituci&oacute;n y su
      tama&ntilde;o es lo que erog&oacute;. <b>Da clic</b> para ver a qui&eacute;n le pag&oacute;.</p>
  </div>
  <div class="ctrl">
    <div class="busca">
      <svg class="lupa" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>
      <input id="q" type="search" autocomplete="off" placeholder="Buscar instituci&oacute;n&hellip;"
             aria-label="Buscar instituci&oacute;n" role="combobox" aria-expanded="false"
             aria-controls="sug" aria-autocomplete="list">
      <ul id="sug" role="listbox" hidden></ul>
    </div>
    <select id="anio" aria-label="A&ntilde;o"></select>
    <button class="btn" id="volver" hidden>&larr; Todas las instituciones</button>
  </div>
</header>

<div class="ruta" id="ruta"></div>
<div id="lienzo"><svg id="mapa" role="img" aria-label="Treemap de gasto"></svg></div>

<footer>
  <span>An&aacute;lisis y elaboraci&oacute;n: <b>__AUTOR__</b> &middot; Millones de pesos
    constantes de 2020 &middot; Solo gasto federal</span>
  <span>Fuente: Sistema COMSOC &middot;
    <a href="__URL_COMSOC__" rel="noopener">gob.mx/buengobierno</a> &middot;
    <a href="index.html">Reporte completo</a></span>
</footer>

<div id="tip" role="status" aria-live="polite"></div>
"""

GUION = r"""
const D = __DATOS__, AUTOR = '__AUTOR__';
const NOM = D.nombres;
const fmt  = n => n.toLocaleString('es-MX',{maximumFractionDigits:0});
const fmt1 = n => n.toLocaleString('es-MX',{minimumFractionDigits:1,maximumFractionDigits:1});
const css  = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const S='http://www.w3.org/2000/svg';
const el=(t,a={})=>{const e=document.createElementNS(S,t);for(const k in a)e.setAttribute(k,a[k]);return e;};

const svg=document.getElementById('mapa'), tip=document.getElementById('tip');
let W=0,H=0, anioSel='', inst=null, animando=false;

/* ── squarify ── */
function squarify(items,w,h){
  const total=items.reduce((s,d)=>s+d.v,0); if(!total||w<=0||h<=0) return [];
  const k=(w*h)/total, nodes=items.map(d=>Object.assign({},d,{area:d.v*k}));
  const out=[], rect={x:0,y:0,w:w,h:h}; let row=[];
  const worst=(rw,ln)=>{ if(!rw.length) return Infinity;
    const s=rw.reduce((a,b)=>a+b.area,0);
    const mx=Math.max.apply(null,rw.map(d=>d.area)), mn=Math.min.apply(null,rw.map(d=>d.area));
    if(s<=0||mn<=0||ln<=0) return Infinity;   /* nunca dividir entre cero */
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

/* ── agregados ── */
function filasAnio(){
  return anioSel==='' ? D.filas : D.filas.filter(f=>f[0]===+anioSel);
}
function nivelInstituciones(){
  const m=new Map();
  filasAnio().forEach(f=>m.set(f[1],(m.get(f[1])||0)+f[3]));
  return [...m].map(([i,v])=>({i:i,n:NOM[i],v:v})).sort((a,b)=>b.v-a.v);
}
function nivelEmpresas(idInst){
  const m=new Map();
  filasAnio().forEach(f=>{ if(f[1]===idInst) m.set(f[2],(m.get(f[2])||0)+f[3]); });
  return [...m].map(([i,v])=>({i:i,n:NOM[i],v:v})).sort((a,b)=>b.v-a.v);
}
/* Cuántas empresas tiene cada institución, para el tooltip. Se calcula UNA vez por
   cambio de año: hacerlo dentro del handler recorría las 46 mil filas en cada
   movimiento del ratón. */
let CUENTA_EMP=new Map();
function recuentaEmpresas(){
  const m=new Map();
  filasAnio().forEach(f=>{
    let s=m.get(f[1]); if(!s){ s=new Set(); m.set(f[1],s); }
    s.add(f[2]);
  });
  CUENTA_EMP=new Map([...m].map(([k,s])=>[k,s.size]));
}

/* ── tooltip ── */
function verTip(e,html){
  tip.innerHTML=html; tip.style.opacity=1;
  const r=tip.getBoundingClientRect();
  let x=e.clientX+15, y=e.clientY+15;
  if(x+r.width>innerWidth-8) x=e.clientX-r.width-15;
  if(y+r.height>innerHeight-8) y=e.clientY-r.height-15;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
const ocultarTip=()=>tip.style.opacity=0;

/* ── dibujo ── */
function dibuja(cells,total,esInstitucion,desde){
  svg.textContent='';
  const max=cells.length?cells[0].v:1;
  const nodos=[];
  const fam = esInstitucion ? 'r' : 'a';   /* rosa: instituciones · ámbar: empresas */
  cells.forEach(c=>{
    const paso=tono(c.v,max);
    const g=el('g',{class:'cel'+(esInstitucion?' click':'')});
    const r=el('rect',{rx:3,fill:css('--'+fam+paso)});
    g.appendChild(r);
    const t1=el('text',{class:'nom',fill:css('--on-'+fam+paso)});
    const t2=el('text',{class:'val',fill:css('--on-'+fam+paso)});
    g.appendChild(t1); g.appendChild(t2);

    const pct=(100*c.v/total).toFixed(1);
    const extra=esInstitucion
      ? '<br>' + fmt(CUENTA_EMP.get(c.i)||0) + ' empresas · clic para abrir'
      : '';
    g.addEventListener('mousemove',e=>verTip(e,
      '<b>'+c.n+'</b><span class="n">'+fmt1(c.v)+'</span> MDP de 2020<br><span class="n">'+
      pct+'%</span> '+(esInstitucion?'del gasto federal':'de esta institución')+extra));
    g.addEventListener('mouseleave',ocultarTip);
    if(esInstitucion){
      g.setAttribute('tabindex','0');
      g.setAttribute('role','button');
      g.setAttribute('aria-label',c.n+', '+fmt1(c.v)+' millones, abrir empresas');
      g.addEventListener('click',()=>entrar(c));
      g.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();entrar(c);}});
    }
    svg.appendChild(g);
    nodos.push({g:g,r:r,t1:t1,t2:t2,c:c});
  });

  /* `desde` mapea el lienzo completo dentro de una caja: las celdas nacen ahí
     y crecen hasta su lugar definitivo. */
  const pos=(c,f)=>{
    if(!f) return c;
    return {x:f.x+c.x*f.w/W, y:f.y+c.y*f.h/H, w:c.w*f.w/W, h:c.h*f.h/H};
  };
  const pinta=(p)=>{
    nodos.forEach(nd=>{
      const a=pos(nd.c,desde), b=nd.c;
      const x=a.x+(b.x-a.x)*p, y=a.y+(b.y-a.y)*p;
      const w=Math.max(a.w+(b.w-a.w)*p,0), h=Math.max(a.h+(b.h-a.h)*p,0);
      nd.r.setAttribute('x',x); nd.r.setAttribute('y',y);
      nd.r.setAttribute('width',w); nd.r.setAttribute('height',h);
      const ver = p>0.98 && w>54 && h>22;
      nd.t1.setAttribute('opacity',ver?1:0);
      nd.t2.setAttribute('opacity',ver&&h>36?1:0);
      if(ver){
        const lim=Math.floor(w/6.1);
        nd.t1.textContent = nd.c.n.length>lim ? nd.c.n.slice(0,lim-1)+'…' : nd.c.n;
        nd.t1.setAttribute('x',x+7); nd.t1.setAttribute('y',y+17);
        nd.t1.setAttribute('font-size',12);
        nd.t2.textContent = fmt1(nd.c.v);
        nd.t2.setAttribute('x',x+7); nd.t2.setAttribute('y',y+31);
        nd.t2.setAttribute('font-size',11);
      }
    });
  };
  if(!desde){ pinta(1); return; }
  animando=true;
  const t0=performance.now(), dur=460;
  const suave=t=>t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;
  (function paso(t){
    const p=Math.min((t-t0)/dur,1);
    pinta(suave(p));
    if(p<1) requestAnimationFrame(paso); else { animando=false; pinta(1); }
  })(t0);
}

/* ── navegación ── */
let ultimaCaja=null;   /* la caja desde la que se entró, para animar el regreso */
function entrar(c){
  if(animando) return;
  ultimaCaja={x:+c.x,y:+c.y,w:+c.w,h:+c.h};
  inst=c.i;
  render(ultimaCaja);
}
function salir(){
  if(animando) return;
  inst=null;
  render(ultimaCaja);   /* las instituciones se despliegan desde donde estabas */
  ultimaCaja=null;
}

function render(desde){
  const rect=document.getElementById('lienzo').getBoundingClientRect();
  W=Math.max(rect.width,1); H=Math.max(rect.height,1);
  svg.setAttribute('viewBox','0 0 '+W+' '+H);

  const esInst = inst===null;
  const datos = esInst ? nivelInstituciones() : nivelEmpresas(inst);
  const total = datos.reduce((s,d)=>s+d.v,0);
  const cells = squarify(datos,W,H);

  document.getElementById('volver').hidden = esInst;
  const etqAnio = anioSel==='' ? '2012–2025' : anioSel;
  document.getElementById('ruta').innerHTML = esInst
    ? '<span class="paso">Todas las instituciones</span><span class="sep">·</span>'+
      '<span class="cifra">'+fmt(datos.length)+' instituciones · '+fmt1(total)+' MDP · '+etqAnio+'</span>'+
      '<span class="sep">·</span><span class="pista">Da clic en una caja para ver a quién le pagó</span>'
    : '<a id="raiz">Todas las instituciones</a><span class="sep">›</span>'+
      '<span class="paso">'+NOM[inst]+'</span><span class="sep">·</span>'+
      '<span class="cifra">'+fmt(datos.length)+' empresas · '+fmt1(total)+' MDP · '+etqAnio+'</span>';
  const raiz=document.getElementById('raiz');
  if(raiz) raiz.addEventListener('click',salir);

  dibuja(cells,total,esInst,desde);
}

/* ── buscador de instituciones ── */
/* ̀-ͯ = marcas combinantes: "México" y "mexico" deben coincidir. */
const pliega = s => s.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const NOM_PLEGADO = NOM.map((n,i)=>pliega(n+' '+(D.alias[i]||'')));
const cajaQ=document.getElementById('q'), lista=document.getElementById('sug');
let sugs=[], marcada=-1;

/* La caja de una institución en el nivel raíz, para animar el zoom desde ella
   aunque llegues por el buscador y no por un clic. */
function cajaDe(id){
  const datos=nivelInstituciones();
  const cells=squarify(datos,W,H);
  for(let i=0;i<datos.length;i++) if(datos[i].i===id) return cells[i];
  return null;
}
function irA(id){
  cierraSug(); cajaQ.value=''; cajaQ.blur();
  if(animando) return;
  const caja = inst===null ? cajaDe(id) : null;   /* si ya estás dentro, salta sin animar */
  ultimaCaja = caja;
  inst = id;
  render(caja);
}
function cierraSug(){
  lista.hidden=true; marcada=-1;
  cajaQ.setAttribute('aria-expanded','false');
}
function pintaSug(){
  const q=pliega(cajaQ.value.trim());
  if(!q){ cierraSug(); return; }
  sugs=nivelInstituciones().filter(d=>NOM_PLEGADO[d.i].indexOf(q)>=0).slice(0,40);
  lista.innerHTML = sugs.length
    ? sugs.map((d,k)=>'<li role="option" data-k="'+k+'" aria-selected="'+(k===marcada)+'">'+
        '<span>'+d.n+'</span><span class="mdp">'+fmt1(d.v)+' MDP</span></li>').join('')
    : '<li class="vacio">Ninguna institución con ese nombre en '+
      (anioSel===''?'la serie':anioSel)+'</li>';
  lista.hidden=false;
  cajaQ.setAttribute('aria-expanded','true');
  Array.prototype.forEach.call(lista.querySelectorAll('li[data-k]'),li=>{
    li.addEventListener('mousedown',e=>{e.preventDefault(); irA(sugs[+li.dataset.k].i);});
  });
}
function mueve(paso){
  if(lista.hidden||!sugs.length) return;
  marcada=(marcada+paso+sugs.length)%sugs.length;
  Array.prototype.forEach.call(lista.querySelectorAll('li[data-k]'),(li,k)=>{
    li.setAttribute('aria-selected',k===marcada);
    if(k===marcada) li.scrollIntoView({block:'nearest'});
  });
}
let tq;
cajaQ.addEventListener('input',()=>{clearTimeout(tq);marcada=-1;tq=setTimeout(pintaSug,110);});
cajaQ.addEventListener('focus',()=>{ if(cajaQ.value.trim()) pintaSug(); });
cajaQ.addEventListener('blur',()=>setTimeout(cierraSug,120));
cajaQ.addEventListener('keydown',e=>{
  if(e.key==='ArrowDown'){e.preventDefault();mueve(1);}
  else if(e.key==='ArrowUp'){e.preventDefault();mueve(-1);}
  else if(e.key==='Enter'){
    e.preventDefault();
    if(sugs.length) irA(sugs[marcada>=0?marcada:0].i);
  } else if(e.key==='Escape'){ cajaQ.value=''; cierraSug(); }
});

/* ── controles ── */
document.getElementById('anio').innerHTML =
  '<option value="">Todos los años (2012–2025)</option>'+
  D.anios.map(a=>'<option value="'+a+'">'+a+'</option>').join('');
document.getElementById('anio').addEventListener('change',e=>{
  anioSel=e.target.value;
  recuentaEmpresas();
  /* Si la institución abierta no gastó ese año, se vuelve a la raíz. */
  if(inst!==null && !nivelEmpresas(inst).length){ inst=null; ultimaCaja=null; }
  render(null);
});
document.getElementById('volver').addEventListener('click',salir);
addEventListener('keydown',e=>{
  if(e.key==='Escape' && inst!==null && document.activeElement!==cajaQ) salir();
});

let t;
addEventListener('resize',()=>{clearTimeout(t);t=setTimeout(()=>render(null),160);});
recuentaEmpresas();
render(null);
"""


def _pagina(datos: dict) -> str:
    cuerpo = CUERPO.replace("__AUTOR__", AUTOR).replace("__URL_COMSOC__", URL_COMSOC)
    guion = (GUION
             .replace("__DATOS__", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
             .replace("__AUTOR__", AUTOR))
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="description" content="{DESCRIPCION}">\n'
        f'<meta name="author" content="{AUTOR}">\n'
        '<meta name="color-scheme" content="light">\n'
        f'<link rel="icon" href="{FAVICON}">\n'
        f"<title>{TITULO}</title>\n<style>{ESTILO}</style>\n</head>\n<body>\n"
        f"{cuerpo}\n<script>{guion}</script>\n</body>\n</html>\n"
    )


def construir(destino: Path | None = None) -> Path:
    asegurar_directorios()
    datos = construir_datos(pd.read_parquet(POLIZAS_PARQUET))
    ruta = destino or (DOCS_DIR / "quien-paga-a-quien.html")
    ruta.write_text(_pagina(datos), encoding="utf-8")
    print(f"  {ruta}  ({ruta.stat().st_size / 1024:,.0f} KB)  "
          f"{len(datos['filas']):,} tripletas, {datos['meta']['instituciones']} instituciones")
    return ruta


def main() -> None:
    p = argparse.ArgumentParser(description="Treemap con zoom institución → empresas")
    p.add_argument("--salida", type=Path, default=None)
    construir(destino=p.parse_args().salida)


if __name__ == "__main__":
    main()
