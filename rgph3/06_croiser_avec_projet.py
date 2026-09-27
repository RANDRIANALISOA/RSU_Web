import csv
import pandas as pd
from norm2 import decoupe
x = pd.read_excel("/home/rse/rsu-web/MENAGES_PAR_COMMUNE_2025.xlsx", dtype={"code_commune":str})
mp = pd.read_csv("map_commune.csv", dtype=str)
# cote projet : code RSU -> nom de la commune dans la source POPULATION (= INSTAT/RGPH)
proj = x[["code_commune","commune_FKT","commune_POP","source_appariement"]].rename(columns={"code_commune":"cc_rsu"})
g = mp.groupby("cc_rsu").agg(mes_noms=("commune_rgph", lambda s: sorted(s)), ma_meth=("methode","first")).reset_index()
j = proj.merge(g, on="cc_rsu", how="left")
print("communes du fichier projet :", len(proj), "| retrouvees dans ma table :", j.mes_noms.notna().sum())
def accord(r):
    if not isinstance(r.mes_noms, list): return "absent"
    cible = decoupe(r.commune_POP)[0]
    return "IDENTIQUE" if any(decoupe(n)[0]==cible for n in r.mes_noms) else "DIFFERENT"
j["accord"] = j.apply(accord, axis=1)
print()
print(j.accord.value_counts().to_string())
print()
print("taux d'accord : %.2f %%" % (j.accord.eq("IDENTIQUE").mean()*100))
print()
d = j[j.accord=="DIFFERENT"]
print("=== les %d DESACCORDS ===" % len(d))
for _,r in d.iterrows():
    print("  %s %-26s | projet: %-26s | moi: %-30s [%s]" %
          (r.cc_rsu, r.commune_FKT, r.commune_POP, ", ".join(r.mes_noms)[:30], r.ma_meth))
