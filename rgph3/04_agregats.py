# -*- coding: utf-8 -*-
"""Tables d'agregats RGPH-3 2018 en codes RSU, pretes pour le tableau de bord.

  rgph_commune  : 1 ligne par commune RSU, indicateurs de privation (%)
  rgph_pyramide : district x tranche d'age quinquennale x sexe
Les effectifs sont RE-DRESSES x10 (echantillon au 10 %).
"""
import os, sys, sqlite3, time
import pandas as pd

SRC = "/home/rse/rsu-web/rgph3_2018.sqlite"
OUT = "agregats_rgph3.sqlite"
con = sqlite3.connect(SRC)
t0 = time.time()

men = pd.read_sql("""select cc_rsu, cd_rsu, cr_rsu, cp_rsu, IDMEN,
    H02, H05, H06, H07, H09, H11, H12, H15, H16, H17A, H17N, H17H,
    F1, F2, F3 from rgph_menage""", con)
print("menages lus : %d" % len(men))

def pct(cond, grp):
    """% de menages verifiant cond, par groupe (NaN exclus du denominateur)."""
    return cond.groupby(grp).mean().mul(100).round(2)

g = men.cc_rsu
ind = pd.DataFrame({"menages_2018": men.groupby(g).size().mul(10)})
ind["murs_precaires"]      = pct(men.H05.isin([2,3,6,7]),            g)
ind["toit_precaire"]       = pct(men.H06.isin([4,5,6]),              g)
ind["sol_precaire"]        = pct(men.H07.isin([1,2,3]),              g)
ind["eau_amelioree"]       = pct(men.H09.isin([1,2,3,4,5,6,7,9,12,15]), g)
ind["eau_sur_place"]       = pct(men.H09.eq(1),                      g)
ind["defecation_air_libre"]= pct(men.H11.eq(1),                      g)
ind["assainis_ameliore"]   = pct(men.H11.isin([2,4]) & men.H12.eq(2),g)
ind["electricite"]         = pct(men.H15.eq(1),                      g)
ind["cuisson_polluante"]   = pct(men.H16.isin([1,2,6]),              g)
ind["proprietaire"]        = pct(men.H02.eq(1),                      g)
ind["radio"]               = pct(men.H17A.eq(1),                     g)
ind["telephone_portable"]  = pct(men.H17N.eq(1),                     g)
ind["ordinateur"]          = pct(men.H17H.eq(1),                     g)
ind["agriculture"]         = pct(men.F1.eq(1),                       g)
ind["elevage"]             = pct(men.F2.eq(1),                       g)
ind["peche"]               = pct(men.F3.eq(1),                       g)

# --- indicateurs individus, rattaches a la commune via IDMEN ---
ccm = men.set_index("IDMEN").cc_rsu
ind_i = pd.read_sql("""select IDMEN, P03, P05, P08, P20MG, P21, P22N
                       from rgph_individu""", con)
ind_i["cc"] = ind_i.IDMEN.map(ccm)
gi = ind_i.cc
ind["population_2018"]  = ind_i.groupby(gi).size().mul(10)
ind["taille_menage"]    = (ind["population_2018"] / ind["menages_2018"]).round(2)
ind["pct_moins_15ans"]  = pct(ind_i.P08.lt(15), gi)
ind["pct_65ans_plus"]   = pct(ind_i.P08.ge(65), gi)
a = ind_i[ind_i.P08.ge(15)]
ind["alphabetisation"]  = pct(a.P20MG.eq(1), a.cc)
s = ind_i[ind_i.P08.between(6, 14)]
ind["scolarisation_6_14"] = pct(s.P21.eq(2), s.cc)
cm = ind_i[ind_i.P03.eq(0)]
ind["cm_femme"]         = pct(cm.P05.eq(2), cm.cc)
ind["cm_sans_instruction"] = pct(cm.P22N.isna(), cm.cc)
ind = ind.reset_index().rename(columns={"index": "cc_rsu", "cc_rsu": "code_commune"})
ind.insert(1, "code_district", men.groupby("cc_rsu").cd_rsu.first().values)
ind.insert(2, "code_region",   men.groupby("cc_rsu").cr_rsu.first().values)

# --- pyramide ---
pyr = pd.read_sql("""select cd_rsu, cast(min(P08/5,16) as int) tr, P05, count(*)*10 n
    from rgph_individu where P08 is not null and P05 is not null
    group by 1,2,3""", con)
pyr.columns = ["code_district", "tranche", "sexe", "effectif"]
pyr["libelle_tranche"] = pyr.tranche.map(lambda t: "80+" if t == 16 else "%d-%d" % (t*5, t*5+4))

if os.path.exists(OUT): os.remove(OUT)
d = sqlite3.connect(OUT)
ind.to_sql("rgph_commune", d, index=False)
pyr.to_sql("rgph_pyramide", d, index=False)
d.execute("CREATE INDEX ix_c ON rgph_commune(code_commune)")
d.execute("CREATE INDEX ix_p ON rgph_pyramide(code_district)")
d.commit()
ind.to_csv("../rgph_commune.csv", index=False)
pyr.to_csv("../rgph_pyramide.csv", index=False)
print("\nrgph_commune  : %d lignes, %d colonnes" % ind.shape)
print("rgph_pyramide : %d lignes" % len(pyr))
print("taille : %.2f Mo | %.0f s" % (os.path.getsize(OUT)/1e6, time.time()-t0))
