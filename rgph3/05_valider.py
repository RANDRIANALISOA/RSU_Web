import sqlite3
import pyreadstat, pandas as pd
mp = pd.read_csv("map_commune.csv", dtype=str)
df,_ = pyreadstat.read_sav("/home/rse/rsu-web/INSTAT_BD_SPSS_MENAGES_10pc_RGPH-3_2018.sav", usecols=["IDMEN"])
rg = df.IDMEN.str[:5].value_counts().rename("men_rgph")
con = sqlite3.connect("/home/rse/rsu-web/rsu_local.sqlite")
rs = pd.DataFrame(con.execute("select code_commune,nombreMenage from commune").fetchall(),
                  columns=["cc_rsu","men_rsu"]).astype({"cc_rsu":str})
j = mp.join(rg, on="cc_rgph").merge(rs, on="cc_rsu", how="left")
a = j.groupby("cc_rsu").agg(rgph=("men_rgph","sum"), rsu=("men_rsu","first"),
                            nom=("commune_rsu","first"), dis=("district_rsu","first")).dropna()
a["rgph"] *= 10
a = a[a.rsu > 0]
print("communes comparees : %d" % len(a))
print("Pearson  : %.4f" % a.rgph.corr(a.rsu))
print("Spearman : %.4f" % a.rgph.rank().corr(a.rsu.rank()))
a["ratio"] = a.rsu / a.rgph
print("ratio RSU2025 / RGPH2018 : median %.2f | q1 %.2f | q3 %.2f" %
      (a.ratio.median(), a.ratio.quantile(.25), a.ratio.quantile(.75)))
ab = a[(a.ratio < 0.4) | (a.ratio > 4)].sort_values("ratio")
print("\ncommunes au ratio aberrant : %d / %d (%.1f %%)" % (len(ab), len(a), len(ab)/len(a)*100))
print(ab[["nom","dis","rgph","rsu","ratio"]].head(12).to_string())
