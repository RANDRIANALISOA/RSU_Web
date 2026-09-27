# -*- coding: utf-8 -*-
"""Table de passage RGPH-3 2018 -> referentiel RSU, niveau COMMUNE."""
import sys, csv, difflib; sys.path.insert(0, ".")
from collections import Counter
from norm2 import decoupe, cles, cles_syn, _tokens
from exceptions import EXCEPTIONS

ARRDT = {"11101":"110701","11102":"110801","11103":"110901",
         "11104":"111001","11105":"111101","11106":"111201"}
DIS_OVERRIDE = {"211":"3303","425":"4407","523":"6103","531":"6203","111":None}

rgph = list(csv.DictReader(open("rgph_geo.csv", encoding="utf-8")))
rsu  = list(csv.DictReader(open("rsu_geo.csv",  encoding="utf-8")))
by_cc = {r["cc_rsu"]: r for r in rsu}

rg_d, rs_d = {}, {}
for r in rgph: rg_d.setdefault(r["cd_rgph"], r["district"])
for r in rsu:  rs_d.setdefault(r["cd_rsu"], (r["district"], r["cr_rsu"]))
dex, dva = {}, {}
for c, v in rs_d.items():
    it = {"code": c, "nom": v[0]}
    dex.setdefault(decoupe(v[0]), []).append(it)
    for k in cles(v[0]): dva.setdefault(k, []).append(it)
dmap = {k: v for k, v in DIS_OVERRIDE.items() if v}
for c, n in rg_d.items():
    if c in DIS_OVERRIDE: continue
    h = dex.get(decoupe(n), []) or list({id(x):x for k in cles(n) for x in dva.get(k,[])}.values())
    if len(h) == 1: dmap[c] = h[0]["code"]
par_dis, par_reg = {}, {}
for r in rsu:
    par_dis.setdefault(r["cd_rsu"], []).append(r)
    par_reg.setdefault(r["cr_rsu"], []).append(r)
reg_of = {c: rs_d[t][1] for c, t in dmap.items()}

assigne, meth, pris = {}, {}, set()
def poser(cc, tgt, m): assigne[cc] = tgt; meth[cc] = m; pris.add(tgt["cc_rsu"])
def libre(pool): return [i for i in pool if i["cc_rsu"] not in pris]
def uniq(h): return h[0] if len(h) == 1 else None
def tset(s): return frozenset(t for t in _tokens(s) if t not in ("CU","ARR"))

for cc, (target, _) in EXCEPTIONS.items(): poser(cc, by_cc[target], "exception")
for r in rgph:
    if r["cc_rgph"] in ARRDT and r["cc_rgph"] not in assigne:
        poser(r["cc_rgph"], by_cc[ARRDT[r["cc_rgph"]]], "arrondissement")

def passe(nom, fn):
    for r in rgph:
        if r["cc_rgph"] in assigne: continue
        t = fn(r)
        if t: poser(r["cc_rgph"], t, nom)

def pool_of(r, large=False):
    return libre(par_reg.get(reg_of.get(r["cd_rgph"]), []) if large
                 else par_dis.get(dmap.get(r["cd_rgph"]), []))

passe("exact/district",    lambda r: uniq([i for i in pool_of(r) if decoupe(i["commune"])==decoupe(r["commune"])]))
passe("variante/district", lambda r: uniq([i for i in pool_of(r) if cles_syn(i["commune"]) & cles_syn(r["commune"])]))
passe("variante2/district", lambda r: uniq([i for i in pool_of(r) if cles(i["commune"]) & cles(r["commune"])]))
def flou(r, large=False, seuil=0.85):
    pool = pool_of(r, large); rad, rang = decoupe(r["commune"])
    meme = [i for i in pool if decoupe(i["commune"])[1] == rang]
    near = difflib.get_close_matches(rad, [decoupe(i["commune"])[0] for i in meme], n=1, cutoff=seuil)
    return uniq([i for i in meme if decoupe(i["commune"])[0] == near[0]]) if near else None
passe("flou/district",     flou)
passe("tokens/district",   lambda r: uniq([i for i in pool_of(r) if tset(i["commune"])==tset(r["commune"])]))
passe("exact/region",      lambda r: uniq([i for i in pool_of(r,True) if decoupe(i["commune"])==decoupe(r["commune"])]))
passe("variante/region",   lambda r: uniq([i for i in pool_of(r,True) if cles_syn(i["commune"]) & cles_syn(r["commune"])]))
def prefixe(r):
    pool = pool_of(r); ta = _tokens(r["commune"])
    if not ta or len(ta[0]) < 5: return None
    hits = []
    for i in pool:
        tb = _tokens(i["commune"])
        if not tb or decoupe(i["commune"])[1] != decoupe(r["commune"])[1] or len(ta) == len(tb): continue
        if ta[0] == tb[0]: hits.append(i)
    return uniq(hits)
passe("prefixe/district",  prefixe)
passe("flou-large/district", lambda r: flou(r, False, 0.80))

def arrondissement_ville(r):
    """RSU « CU <ville> arr. <QUARTIER> » : apparie sur le QUARTIER seul."""
    hits = []
    for i in pool_of(r):
        t = _tokens(i["commune"])
        if "ARR" not in t: continue
        reste = " ".join(t[t.index("ARR") + 1:])
        if reste and decoupe(reste) == decoupe(r["commune"]): hits.append(i)
    return uniq(hits)
passe("arrondissement_ville", arrondissement_ville)

# fusion urbaine : plusieurs quartiers RGPH -> UNE commune urbaine RSU
def fusion(r):
    cd = dmap.get(r["cd_rgph"])
    pool = par_dis.get(cd, [])
    if len(pool) == 1: return pool[0]
    cu = [i for i in pool if _tokens(i["commune"])[:1] == ["CU"] and len(_tokens(i["commune"])) <= 3]
    return cu[0] if len(cu) == 1 else None
for r in rgph:
    if r["cc_rgph"] in assigne: continue
    t = fusion(r)
    if t: assigne[r["cc_rgph"]] = t; meth[r["cc_rgph"]] = "fusion_urbaine"; pris.add(t["cc_rsu"])

res = []
for r in rgph:
    t = assigne.get(r["cc_rgph"])
    res.append({"cc_rgph": r["cc_rgph"], "commune_rgph": r["commune"], "cd_rgph": r["cd_rgph"],
                "district_rgph": r["district"], "region_rgph": r["region"],
                "cc_rsu": t["cc_rsu"] if t else "", "commune_rsu": t["commune"] if t else "",
                "cd_rsu": t["cd_rsu"] if t else "", "district_rsu": t["district"] if t else "",
                "cr_rsu": t["cr_rsu"] if t else "", "region_rsu": t["region"] if t else "",
                "cp_rsu": t["cp_rsu"] if t else "", "province_rsu": t["province"] if t else "",
                "methode": meth.get(r["cc_rgph"], "A_ARBITRER"),
                "justification": EXCEPTIONS.get(r["cc_rgph"], ("",""))[1]})
ok = [r for r in res if r["cc_rsu"]]
print("COMMUNES : %d / %d  (%.2f %%)\n" % (len(ok), len(res), len(ok)/len(res)*100))
for k, v in sorted(Counter(r["methode"] for r in res).items(), key=lambda x: -x[1]):
    print("    %-22s %4d" % (k, v))
nm = [c for c, n in Counter(r["cc_rsu"] for r in ok).items() if n > 1]
print("\n    communes RSU recevant plusieurs communes RGPH : %d (fusions urbaines)" % len(nm))
print("    RESTE A ARBITRER : %d" % len([r for r in res if not r["cc_rsu"]]))
for r in res:
    if not r["cc_rsu"]: print("        %-28s [%s]" % (r["commune_rgph"], r["district_rgph"]))
with open("map_commune.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
