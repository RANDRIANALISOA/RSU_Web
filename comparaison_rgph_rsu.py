# -*- coding: utf-8 -*-
"""Tables de comparaison RGPH-3 2018 <-> RSU, pour affichage cote a cote.

  comp_taille_menage : taille moyenne des menages, par district ET par commune
  comp_pyramide      : pyramide des ages, par district, en effectifs et en %

Sources RSU :
  * taille : segment_roster.taille_menD (denombrement, 12 districts)
  * ages   : vad_membre M3 (sexe 48=M/49=F) + M4 (age revolu), via vad_menage
Idempotent. Reversible : DROP TABLE comp_taille_menage; DROP TABLE comp_pyramide;
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_source import connect

SQL_TAILLE = """
DROP TABLE IF EXISTS comp_taille_menage;
CREATE TABLE comp_taille_menage AS
WITH rgph_d AS (
  SELECT cd_rsu code, COUNT(DISTINCT IDMEN) men, COUNT(*) pop
  FROM rgph_individu GROUP BY 1),
rgph_c AS (
  SELECT cc_rsu code, cd_rsu parent, COUNT(DISTINCT IDMEN) men, COUNT(*) pop
  FROM rgph_individu GROUP BY 1,2),
rsu_d AS (
  SELECT d.district code, COUNT(*) men, SUM(s.taille_menD) pop
  FROM segment_roster s JOIN den_menage d ON d.interview__key = s.interview__key
  WHERE s.taille_menD > 0 GROUP BY 1),
rsu_c AS (
  SELECT d.commune code, d.district parent, COUNT(*) men, SUM(s.taille_menD) pop
  FROM segment_roster s JOIN den_menage d ON d.interview__key = s.interview__key
  WHERE s.taille_menD > 0 GROUP BY 1,2)
SELECT 'district' niveau, r.code, di.nom, NULL code_district,
       r.men menages_rgph, ROUND(1.0*r.pop/r.men, 2) taille_rgph,
       s.men menages_rsu,  ROUND(1.0*s.pop/s.men, 2) taille_rsu,
       ROUND(1.0*s.pop/s.men - 1.0*r.pop/r.men, 2) ecart
FROM rgph_d r LEFT JOIN rsu_d s ON s.code = r.code
LEFT JOIN district di ON di.code_district = r.code
UNION ALL
SELECT 'commune', r.code, cm.nom, r.parent,
       r.men, ROUND(1.0*r.pop/r.men, 2),
       s.men, ROUND(1.0*s.pop/s.men, 2),
       ROUND(1.0*s.pop/s.men - 1.0*r.pop/r.men, 2)
FROM rgph_c r LEFT JOIN rsu_c s ON s.code = r.code
LEFT JOIN commune cm ON cm.code_commune = r.code;
CREATE INDEX ix_ctm ON comp_taille_menage(niveau, code);
CREATE INDEX ix_ctm_d ON comp_taille_menage(code_district);
"""

SQL_PYR = """
DROP TABLE IF EXISTS comp_pyramide;
CREATE TABLE comp_pyramide AS
WITH rg AS (
  SELECT cd_rsu code, MIN(CAST(P08/5 AS INT),16) tr, CAST(P05 AS INT) sexe, COUNT(*)*10 n
  FROM rgph_individu WHERE P08 IS NOT NULL AND P05 IS NOT NULL GROUP BY 1,2,3),
rg_t AS (SELECT code, SUM(n) tot FROM rg GROUP BY 1),
rs AS (
  SELECT CAST(v."CQ7" AS INT) code, MIN(CAST(m.M4/5 AS INT),16) tr,
         CASE m.M3 WHEN 48 THEN 1 WHEN 49 THEN 2 END sexe, COUNT(*) n
  FROM vad_membre m JOIN vad_menage v ON v.interview__key = m.interview__key
  WHERE m.M4 IS NOT NULL AND m.M3 IN (48,49)
    AND v."CQ7" IS NOT NULL GROUP BY 1,2,3),
rs_t AS (SELECT code, SUM(n) tot FROM rs GROUP BY 1)
SELECT COALESCE(rg.code, rs.code) code_district, di.nom district,
       COALESCE(rg.tr, rs.tr) tranche,
       CASE WHEN COALESCE(rg.tr, rs.tr)=16 THEN '80+'
            ELSE CAST(COALESCE(rg.tr,rs.tr)*5 AS TEXT)||'-'||CAST(COALESCE(rg.tr,rs.tr)*5+4 AS TEXT) END libelle_tranche,
       COALESCE(rg.sexe, rs.sexe) sexe,
       rg.n effectif_rgph, ROUND(100.0*rg.n/rg_t.tot, 3) pct_rgph,
       rs.n effectif_rsu,  ROUND(100.0*rs.n/rs_t.tot, 3) pct_rsu
FROM rg LEFT JOIN rg_t ON rg_t.code = rg.code
LEFT JOIN rs ON rs.code = rg.code AND rs.tr = rg.tr AND rs.sexe = rg.sexe
LEFT JOIN rs_t ON rs_t.code = rs.code
LEFT JOIN district di ON di.code_district = rg.code;
CREATE INDEX ix_cp ON comp_pyramide(code_district);
"""

if __name__ == "__main__":
    conn = connect()
    cur = conn.cursor()
    for bloc in (SQL_TAILLE, SQL_PYR):
        for stmt in [s.strip() for s in bloc.split(";") if s.strip()]:
            cur.execute(stmt)
    conn.commit()
    for t in ("comp_taille_menage", "comp_pyramide"):
        print("  %-20s %d lignes" % (t, cur.execute('SELECT count(*) FROM "%s"' % t).fetchone()[0]))
