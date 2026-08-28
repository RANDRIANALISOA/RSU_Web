# -*- coding: utf-8 -*-
"""
simuler_db.py — Scénario « données en base de données » (projet web).

Simule l'architecture de production (données dans PostgreSQL au lieu de .dta) :

    1. Transcrit les .dta -> base SQL locale (SQLite par défaut, PostgreSQL si
       RSU_DB_URL est défini — voir db_source.connect()).
    2. Génère le rapport DEPUIS LA BASE (source=source_db(conn)).
    3. Génère aussi le rapport depuis les .dta (méthode actuelle).
    4. Compare les deux HTML octet à octet -> PREUVE que lire une base ou lire
       les .dta produit exactement le même rapport.

Les chemins (DATA, contours) viennent de config.py (référencés dans le projet
.exe voisin par défaut ; surchargables par variables d'environnement).

Lancement :
    python simuler_db.py                      (SQLite, zéro installation)
    set RSU_DB_URL=postgresql://...           (puis) python simuler_db.py
"""

import os
import tempfile

import rapport_core
import db_source
import config


def _generer(chemins, source, titre):
    print(f"\n=== Génération {titre} ===")
    return rapport_core.generer_rapport(chemins, log=print, source=source)


def main():
    # 1. Base SQL locale + transcription depuis les .dta référencés par config.
    conn = db_source.connect()
    moteur = "PostgreSQL" if os.environ.get("RSU_DB_URL", "").startswith("postgres") \
        else "SQLite (local, stdlib)"
    print(f"Base de données cible : {moteur}")
    print(f"Données .dta          : {config.DATA_DIR}")
    print(f"Contours              : {config.LIMITES_DIR}")
    db_source.charger_dta_vers_db(config.DATA_DIR, conn, print)

    # 2. Rapport depuis la BASE.
    dir_db = tempfile.mkdtemp(prefix="rsu_db_")
    rep_db = _generer(
        {"rapport": dir_db, "limites": config.LIMITES_DIR,
         "templates": config.TEMPLATES_DIR},
        db_source.source_db(conn), "DEPUIS LA BASE SQL")

    # 3. Rapport depuis les .dta (référence).
    dir_dta = tempfile.mkdtemp(prefix="rsu_dta_")
    rep_dta = _generer(
        {"data": config.DATA_DIR, "rapport": dir_dta,
         "limites": config.LIMITES_DIR, "templates": config.TEMPLATES_DIR},
        None, "DEPUIS LES .dta (référence)")

    # 4. Comparaison octet à octet.
    with open(rep_db, "rb") as f:
        a = f.read()
    with open(rep_dta, "rb") as f:
        b = f.read()

    print("\n" + "=" * 60)
    print(f"Rapport (base) : {len(a):>10} octets  -> {rep_db}")
    print(f"Rapport (.dta) : {len(b):>10} octets  -> {rep_dta}")
    if a == b:
        print("RESULTAT : [OK] IDENTIQUES -- lire la base SQL produit exactement")
        print("           le meme rapport que lire les .dta.")
    else:
        n = min(len(a), len(b))
        i = next((k for k in range(n) if a[k] != b[k]), n)
        print("RESULTAT : [DIFF] DIFFERENTS")
        print(f"           1re divergence a l'octet {i}")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
