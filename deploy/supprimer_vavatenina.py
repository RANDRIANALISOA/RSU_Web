# -*- coding: utf-8 -*-
"""Supprime les donnees de collecte du district 5206 (VAVATENINA).

Perimetre EXACT (decide avec l'utilisateur) :
  • denombrement : den_menage / segment_roster / interview__diagnostics, par
    interview__key — celles du district EN BASE *et* celles du dossier televerse
    mais jamais transcrit (12 diagnostics orphelins, cf. CLAUDE.md 2026-09-21) ;
  • VAD : rien (aucun menage CQ7=5206 en base) ;
  • agent : les codes de 5206 qui n'ont plus aucune donnee ailleurs.
CONSERVES : comptes, journaux (connexion, bord, transcriptions), zones, RGPH.
"""
import os
import sys

sys.path.insert(0, "/home/rse/rsu-web")
import db_source
from lire_dta import lire_dta

CODE = 5206
DOSSIER = "/home/rse/rsu-web/DATA_serveur/5206"


def cles(conn):
    cur = conn.cursor()
    cur.execute("SELECT interview__key FROM den_menage WHERE district=?", (CODE,))
    k = {r[0] for r in cur.fetchall()}
    p = os.path.join(DOSSIER, "DEN_MENAGE.dta")
    if os.path.isfile(p):                 # dossier televerse, pas encore transcrit
        k |= {v for v in lire_dta(p).col("interview__key") if v}
    return sorted(k)


def main():
    dry = "--dry-run" in sys.argv[1:]
    conn = db_source.connect()
    cur = conn.cursor()
    k = cles(conn)
    q = ",".join("?" * len(k))
    print(f"{len(k)} interview__key du district {CODE}")

    # Agents devenus sans donnees APRES suppression (calcule AVANT d'effacer).
    cur.execute(f'SELECT DISTINCT responsible FROM interview__diagnostics '
                f'WHERE interview__key IN ({q}) AND responsible IS NOT NULL', k)
    ag = sorted({r[0] for r in cur.fetchall()})
    qa = ",".join("?" * len(ag))
    cur.execute(f'SELECT DISTINCT responsible FROM interview__diagnostics '
                f'WHERE responsible IN ({qa}) AND interview__key NOT IN ({q})', ag + k)
    garde = {r[0] for r in cur.fetchall()}
    orphelins = [a for a in ag if a not in garde]
    print(f"{len(ag)} agents, dont {len(orphelins)} sans donnees ailleurs")

    for t in ("segment_roster", "interview__diagnostics", "den_menage"):
        cur.execute(f'SELECT COUNT(*) FROM "{t}" WHERE interview__key IN ({q})', k)
        n = cur.fetchone()[0]
        if not dry:
            cur.execute(f'DELETE FROM "{t}" WHERE interview__key IN ({q})', k)
        print(f'   {"[dry] " if dry else ""}{t:24s} -{n}')
    if orphelins:
        qo = ",".join("?" * len(orphelins))
        if not dry:
            cur.execute(f'DELETE FROM "agent" WHERE login_ae IN ({qo})', orphelins)
        print(f'   {"[dry] " if dry else ""}{"agent":24s} -{len(orphelins)}')

    if dry:
        conn.rollback()
        print("[DRY-RUN] rien ecrit.")
    else:
        conn.commit()
        print("Suppression validee (commit).")
    conn.close()


if __name__ == "__main__":
    main()
