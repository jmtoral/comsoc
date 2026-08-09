"""Qué pares uniría un fuzzy join. NO se aplica: solo se listan para revisión."""
import sys

import pandas as pd
from rapidfuzz import fuzz, process

sys.path.insert(0, r"D:\Descargas\Publicidad Oficial\src")
from comsoc.entities import clave_dura, plegar  # noqa: E402

pd.set_option("display.width", 240)
d = pd.read_parquet(r"D:\Descargas\Publicidad Oficial\data\processed\comsoc_polizas.parquet")
b = d[(d.vintage == "definitiva") & (~d.es_intercambio)]

# Un renglón por grupo ya consolidado, con su peso y sus años
g = (b.groupby("beneficiario_consolidado")
     .agg(mdp=("monto_real", lambda s: s.sum() / 1e6),
          ini=("anio_fuente", "min"), fin=("anio_fuente", "max"),
          rfc=("rfc_beneficiario", lambda s: set(s.dropna()))).reset_index())
g["cd"] = g.beneficiario_consolidado.map(clave_dura)

# Solo vale la pena revisar lo que pesa algo
rel = g[g.mdp >= 1].reset_index(drop=True)
print(f"grupos consolidados: {len(g):,}   con ≥1 MDP: {len(rel):,}")

claves = rel.cd.tolist()
pares = []
for i, c in enumerate(claves):
    for _, s, k in process.extract(c, claves, scorer=fuzz.ratio, limit=6):
        if k <= i or s < 88:
            continue
        a, bb = rel.iloc[i], rel.iloc[k]
        # Si comparten RFC ya estarían unidos; si tienen RFC DISTINTO, son empresas distintas
        if a.rfc and bb.rfc and not (a.rfc & bb.rfc):
            continue
        pares.append({"score": s, "a": a.beneficiario_consolidado, "b": bb.beneficiario_consolidado,
                      "mdp_a": round(a.mdp, 1), "mdp_b": round(bb.mdp, 1),
                      "años_a": f"{a.ini}–{a.fin}", "años_b": f"{bb.ini}–{bb.fin}",
                      "rfc_a": bool(a.rfc), "rfc_b": bool(bb.rfc)})

p = pd.DataFrame(pares).drop_duplicates(subset=["a", "b"]).sort_values(
    ["score", "mdp_a"], ascending=False)
print(f"pares candidatos (score ≥88, sin RFC contradictorio): {len(p)}\n")
print("=== los que más dinero moverían ===")
p["juntos"] = p.mdp_a + p.mdp_b
for _, r in p.nlargest(10, "juntos").iterrows():
    print(f"\n  score {r.score:.0f}  ·  {r.juntos:,.1f} MDP en juego")
    print(f"    {r.mdp_a:>8,.1f}  {r.a[:64]:<64} {r['años_a']}")
    print(f"    {r.mdp_b:>8,.1f}  {r.b[:64]:<64} {r['años_b']}")
