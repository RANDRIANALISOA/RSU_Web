# -*- coding: utf-8 -*-
"""Integre les microdonnees RGPH-3 2018 (recodees en codes RSU) dans la base RSU.

    python integrer_rgph_complet.py          # -> rsu_local.sqlite
    RSU_DB_URL=postgresql://... python integrer_rgph_complet.py

Cree/remplace : rgph_menage (608 235), rgph_individu (2 568 303),
                rgph_passage_commune (1 727).
Idempotent. Reversible :
    DROP TABLE rgph_individu; DROP TABLE rgph_menage;
    DROP TABLE rgph_passage_commune; VACUUM;

ATTENTION : ajoute ~1 Go a la base. Une sauvegarde est faite au prealable.
"""
import os, shutil, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_source import connect

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "rgph3_2018.sqlite")
TABLES = ["rgph_menage", "rgph_individu", "rgph_passage_commune"]
INDEX = {"rgph_menage": ["cc_rsu", "cd_rsu", "cr_rsu", "IDMEN"],
         "rgph_individu": ["cc_rsu", "cd_rsu", "cr_rsu", "IDMEN"],
         "rgph_passage_commune": ["cc_rgph", "cc_rsu"]}

def sauvegarder(conn):
    if type(conn).__module__.split(".")[0] != "sqlite3": return None
    cible = conn.execute("PRAGMA database_list").fetchall()[0][2]
    if not cible or not os.path.exists(cible): return None
    bak = cible + ".avant_rgph.bak"
    shutil.copy2(cible, bak)
    print("sauvegarde : %s (%.0f Mo)" % (bak, os.path.getsize(bak) / 1e6))
    return cible

def main():
    if not os.path.exists(SRC):
        sys.exit("Introuvable : %s — lancer d'abord rgph3/03_recoder.py" % SRC)
    conn = connect()
    est_sqlite = type(conn).__module__.split(".")[0] == "sqlite3"
    cible = sauvegarder(conn)
    t0 = time.time()
    cur = conn.cursor()
    for t in reversed(TABLES):
        cur.execute('DROP TABLE IF EXISTS "%s"' % t)
    conn.commit()

    if est_sqlite:
        cur.execute("ATTACH DATABASE ? AS rgph", (SRC,))
        for t in TABLES:
            cur.execute('CREATE TABLE main."%s" AS SELECT * FROM rgph."%s"' % (t, t))
            print("  %-22s %d lignes" % (t, cur.execute('SELECT count(*) FROM main."%s"' % t).fetchone()[0]))
        conn.commit()
        cur.execute("DETACH DATABASE rgph")
    else:
        import pandas as pd
        src = sqlite3.connect(SRC)
        for t in TABLES:
            n = 0
            for morceau in pd.read_sql('SELECT * FROM "%s"' % t, src, chunksize=100000):
                morceau.to_sql(t, conn, if_exists="append", index=False)
                n += len(morceau)
            print("  %-22s %d lignes" % (t, n))
        conn.commit()

    for t, cols in INDEX.items():
        for c in cols:
            cur.execute('CREATE INDEX IF NOT EXISTS "ix_%s_%s" ON "%s"("%s")' % (t, c.lower(), t, c))
    conn.commit()
    print("termine en %.0f s" % (time.time() - t0))
    if cible: print("base : %.0f Mo" % (os.path.getsize(cible) / 1e6))

if __name__ == "__main__":
    main()
