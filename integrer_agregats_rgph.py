# -*- coding: utf-8 -*-
"""Insere les agregats RGPH-3 2018 dans la base RSU (idempotent, reversible).

    python integrer_agregats_rgph.py            # -> rsu_local.sqlite
    RSU_DB_URL=postgresql://... python integrer_agregats_rgph.py

Pour annuler :  DROP TABLE rgph_commune;  DROP TABLE rgph_pyramide;
Les deux tables se joignent a commune.code_commune / district.code_district.
"""
import csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_source import connect, _placeholder

TABLES = {"rgph_commune": "rgph_commune.csv", "rgph_pyramide": "rgph_pyramide.csv"}

def charger(conn, table, chemin):
    cur = conn.cursor()
    with open(chemin, encoding="utf-8") as f:
        lignes = list(csv.reader(f))
    entete, corps = lignes[0], lignes[1:]
    cur.execute('DROP TABLE IF EXISTS "%s"' % table)
    typ = lambda c: "TEXT" if c.startswith("libelle") else "REAL"
    cur.execute('CREATE TABLE "%s" (%s)' % (table, ", ".join('"%s" %s' % (c, typ(c)) for c in entete)))
    ph = ", ".join([_placeholder(conn)] * len(entete))
    cur.executemany('INSERT INTO "%s" VALUES (%s)' % (table, ph),
                    [[None if v == "" else v for v in r] for r in corps])
    print("  %-16s %d lignes" % (table, len(corps)))

if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    conn = connect()
    for t, f in TABLES.items():
        charger(conn, t, os.path.join(base, f))
    cur = conn.cursor()
    cur.execute('CREATE INDEX IF NOT EXISTS ix_rgph_commune ON rgph_commune("code_commune")')
    cur.execute('CREATE INDEX IF NOT EXISTS ix_rgph_pyr ON rgph_pyramide("code_district")')
    conn.commit()
    print("Termine.")
