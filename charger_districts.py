# -*- coding: utf-8 -*-
"""
charger_districts.py — Charge les données de dénombrement de PLUSIEURS districts
dans la base (SQLite par défaut, PostgreSQL si RSU_DB_URL est défini).

Réunit dans les mêmes tables (den_menage, segment_roster, interview__diagnostics)
les .dta de tous les dossiers listés dans DOSSIERS ci-dessous. Les value labels
sont unionnés ; les tables sont reconstruites à partir de l'ensemble des sources
(donc relancer ce script = repartir de cette liste complète).

    # SQLite (défaut) :
    python charger_districts.py

    # PostgreSQL :
    set RSU_DB_URL=postgresql://postgres:...@localhost:5432/rsu
    python charger_districts.py
"""

import os

import config
import db_source

BASE = config.BASE

# Dossiers sources (chacun contient DEN_MENAGE.dta / segment_roster.dta /
# interview__diagnostics.dta). Ajouter ici les futurs districts.
DOSSIERS = [
    config.DATA_DIR,                                       # MAMPIKONY (existant)
    os.path.join(BASE, "Antsirabe"),                      # ANTSIRABE I
    os.path.join(BASE, "BeloSurTsiribihana", "DATA"),     # BELO SUR TSIRIBIHINA
    os.path.join(BASE, "Ikalamavony", "DATA"),            # IKALAMAVONY
    os.path.join(BASE, "Miandrivazo", "DATA"),            # MIANDRIVAZO
]


def main():
    conn = db_source.connect()
    moteur = ("PostgreSQL"
              if os.environ.get("RSU_DB_URL", "").startswith("postgres")
              else "SQLite (local)")
    print(f"Base cible : {moteur}")
    for d in DOSSIERS:
        print(f"  source : {d}  {'OK' if os.path.isdir(d) else 'ABSENT !'}")

    db_source.charger_dta_multi_vers_db(DOSSIERS, conn, print)

    # Récapitulatif par district (nombre de segments DEN par district).
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM "den_menage"')
    print(f"\nden_menage : {cur.fetchone()[0]} segments au total")
    cur.execute('SELECT COUNT(*) FROM "segment_roster"')
    print(f"segment_roster : {cur.fetchone()[0]} ménages au total")
    den = db_source.DbDataset(conn, "den_menage")
    par_district = {}
    for d in den.col_decoded("district"):
        cle = d if d is not None else "(sans district)"
        par_district[cle] = par_district.get(cle, 0) + 1
    print("Segments par district :")
    for nom, n in sorted(par_district.items()):
        print(f"   {nom}: {n}")
    conn.close()


if __name__ == "__main__":
    main()
