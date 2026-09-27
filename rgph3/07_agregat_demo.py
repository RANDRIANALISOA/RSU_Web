# -*- coding: utf-8 -*-
"""Pré-agrégats démographiques RGPH, pour le tableau de bord VAD.

Sans eux, `vad_core._sec_rgph` balaie les 2,5 M de lignes de `rgph_individu` à
chaque page : 3,7 s en périmètre national, et ce pour TOUTES les sections, y
compris celles qui n'affichent aucun repère RGPH.

  rgph_age_commune : commune x age x sexe -> effectif   (~241 000 lignes)
  rgph_men_commune : commune -> ménages, chefs, chefs femmes  (1 704 lignes)

Les deux sont additifs : agréger sur un district ou une liste de communes est
une simple somme. Idempotent.
    DROP TABLE rgph_age_commune; DROP TABLE rgph_men_commune;
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_source import connect

SQL = [
    'DROP TABLE IF EXISTS rgph_age_commune',
    '''CREATE TABLE rgph_age_commune AS
       SELECT "cc_rsu", "cd_rsu", CAST("P08" AS INT) age, CAST("P05" AS INT) sexe,
              COUNT(*) n
       FROM rgph_individu
       WHERE "P08" IS NOT NULL AND "P05" IS NOT NULL
       GROUP BY 1,2,3,4''',
    'CREATE INDEX ix_rac_c ON rgph_age_commune("cc_rsu")',
    'CREATE INDEX ix_rac_d ON rgph_age_commune("cd_rsu")',
    'DROP TABLE IF EXISTS rgph_men_commune',
    '''CREATE TABLE rgph_men_commune AS
       SELECT m."cc_rsu", m."cd_rsu", COUNT(*) menages,
              SUM(CASE WHEN c.chef IS NOT NULL THEN 1 ELSE 0 END) chefs,
              SUM(CASE WHEN c.chef = 2 THEN 1 ELSE 0 END) chefs_femmes
       FROM rgph_menage m
       LEFT JOIN (SELECT "IDMEN", MIN("P05") chef FROM rgph_individu
                  WHERE "P03" = 0 GROUP BY "IDMEN") c ON c."IDMEN" = m."IDMEN"
       GROUP BY 1,2''',
    'CREATE INDEX ix_rmc_c ON rgph_men_commune("cc_rsu")',
    'CREATE INDEX ix_rmc_d ON rgph_men_commune("cd_rsu")',
]

if __name__ == "__main__":
    conn = connect(); cur = conn.cursor(); t0 = time.time()
    for s in SQL:
        cur.execute(s)
    conn.commit()
    for t in ("rgph_age_commune", "rgph_men_commune"):
        print("  %-20s %d lignes" % (t, cur.execute('SELECT count(*) FROM "%s"' % t).fetchone()[0]))
    print("  %.0f s" % (time.time() - t0))
