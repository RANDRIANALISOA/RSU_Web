import sys, csv, sqlite3
import pyreadstat
df, m = pyreadstat.read_sav("/home/rse/rsu-web/INSTAT_BD_SPSS_MENAGES_10pc_RGPH-3_2018.sav", metadataonly=True)
lab = lambda v: m.value_labels[m.variable_to_label[v]]
reg, dis, com = lab("REGION"), lab("DISTRICT"), lab("COMMUNES")
with open("rgph_geo.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["cc_rgph","commune","cd_rgph","district","cr_rgph","region"])
    for k,v in sorted(com.items()):
        k=int(k); d=int(str(k)[:3]); r=int(str(k)[:2])
        w.writerow([k,v,d,dis.get(float(d),""),r,reg.get(float(r),"")])
print("RGPH : %d communes, %d districts, %d regions" % (len(com),len(dis),len(reg)))

con=sqlite3.connect("/home/rse/rsu-web/rsu_local.sqlite")
q="""select c.code_commune, c.nom, d.code_district, d.nom, r.code_region, r.nom, p.code_province, p.nom
     from commune c join district d on d.code_district=c.code_district
     join region r on r.code_region=d.code_region join province p on p.code_province=r.code_province"""
rows=con.execute(q).fetchall()
with open("rsu_geo.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["cc_rsu","commune","cd_rsu","district","cr_rsu","region","cp_rsu","province"])
    w.writerows(rows)
print("RSU  : %d communes, %d districts, %d regions" % (len(rows), len({r[2] for r in rows}), len({r[4] for r in rows})))
