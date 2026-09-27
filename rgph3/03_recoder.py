# -*- coding: utf-8 -*-
"""Applique la table de passage aux deux fichiers .sav -> SQLite en codes RSU."""
import os, sqlite3, time
import pyreadstat, pandas as pd

MAP = pd.read_csv("map_commune.csv", dtype=str)
CLE = MAP.set_index("cc_rgph")[["cc_rsu","cd_rsu","cr_rsu","cp_rsu"]]
DB  = "/home/rse/rsu-web/rgph3_2018.sqlite"
if os.path.exists(DB): os.remove(DB)
con = sqlite3.connect(DB)

def recode(df):
    df.insert(0, "cc_rgph", df["IDMEN"].str[:5])
    j = df.join(CLE, on="cc_rgph")
    for c in ["cc_rsu","cd_rsu","cr_rsu","cp_rsu"]:
        j[c] = pd.to_numeric(j[c], errors="coerce").astype("Int64")
    manquants = int(j["cc_rsu"].isna().sum())
    # les anciens codes RGPH sont conserves, prefixes, pour tracabilite
    j = j.rename(columns={"PROVINCE":"province_rgph2018","REGION":"region_rgph2018",
                          "DISTRICT":"district_rgph2018","COMMUNES":"commune_rgph2018"})
    return j, manquants

t0 = time.time()
men, _ = pyreadstat.read_sav("/home/rse/rsu-web/INSTAT_BD_SPSS_MENAGES_10pc_RGPH-3_2018.sav")
men, m1 = recode(men)
men.columns = [c.replace("$1","") for c in men.columns]
men.to_sql("rgph_menage", con, index=False, chunksize=100000)
print("rgph_menage   : %d lignes | codes RSU manquants : %d" % (len(men), m1))

ind, _ = pyreadstat.read_sav("/home/rse/rsu-web/INSTAT_BD_SPSS_RESIDENTS_10pc_RGPH-3_2018.sav", encoding="LATIN1")
ind, m2 = recode(ind)
ind.to_sql("rgph_individu", con, index=False, chunksize=100000)
print("rgph_individu : %d lignes | codes RSU manquants : %d" % (len(ind), m2))

MAP.to_sql("rgph_passage_commune", con, index=False)
for t, c in [("rgph_menage","cc_rsu"),("rgph_menage","cd_rsu"),
             ("rgph_individu","cc_rsu"),("rgph_individu","cd_rsu"),
             ("rgph_individu","IDMEN"),("rgph_menage","IDMEN")]:
    con.execute('CREATE INDEX IF NOT EXISTS ix_%s_%s ON %s("%s")' % (t, c.lower(), t, c))
con.commit()
print("\nbase : %s  (%.0f Mo)  en %.0f s" % (DB, os.path.getsize(DB)/1e6, time.time()-t0))
