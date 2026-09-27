# -*- coding: utf-8 -*-
"""
ajouter_colonne.py — Ajoute a la base les colonnes qu'un export .dta apporte EN
PLUS, SANS transcrire la moindre ligne de donnees.

A quoi ca sert : le questionnaire du denombrement evolue (celui de septembre 2026
ajoute `nbr_max_men` a DEN_MENAGE). `maj_db.maj_table` sait desormais reconcilier
la structure tout seul au moment de la transcription ; ce script fait la MEME
chose a l'avance, pour preparer la base avant que l'Expert survey ne televerse —
ou simplement pour aligner le schema sur un nouveau questionnaire sans toucher
aux donnees. Les lignes deja en base restent a NULL sur la nouvelle colonne :
on n'invente pas de valeur pour une question qui n'etait pas posee.

Chaque colonne va dans LA table de son fichier (`db_source.FICHIERS`) :
DEN_MENAGE.dta -> den_menage, segment_roster.dta -> segment_roster,
interview__diagnostics.dta -> interview__diagnostics.

Difference avec `maj_db` : l'ordre enregistre dans `_schema` devient celui du
.dta — la colonne se place a SA place dans le questionnaire, au lieu d'etre
ajoutee en fin de liste. Les colonnes que la base garde et que ce questionnaire
ne collecte plus sont conservees, a la suite. Cet ordre ne sert qu'a lister les
colonnes (`DbDataset.varnames`) : tout le code lit par NOM.

Usage :
    python ajouter_colonne.py <dossier_dta>              # applique (commit)
    python ajouter_colonne.py <dossier_dta> --dry-run    # dit seulement ce qu'il ferait
"""
import os
import sys

import db_source
import maj_db
from lire_dta import lire_dta


def colonnes_en_plus(conn, dta_path, table):
    """(colonnes du .dta absentes de la base, ordre final de `_schema`, dataset).

    Renvoie ([], [], None) si la table n'a pas encore ete transcrite : il n'y a
    alors rien a completer, la transcription la creera entiere.
    """
    connues = maj_db._colonnes_connues(conn, table)
    if not connues:
        return [], [], None
    d = lire_dta(dta_path)
    cols = list(d.varnames)
    nouvelles = [c for c in cols if c not in connues]
    # Ordre final : celui du .dta, puis ce que la base garde en plus.
    ordre = cols + [c for c in connues if c not in cols]
    return nouvelles, ordre, d


def ajouter(conn, dta_path, table, log=print):
    """Ajoute a `table` les colonnes que son .dta apporte en plus. Renvoie la liste."""
    nouvelles, ordre, d = colonnes_en_plus(conn, dta_path, table)
    if d is None:
        log(f'   [ignore] "{table}" : pas encore transcrite (aucun schema).')
        return []
    if not nouvelles:
        log(f'   "{table}" : rien a ajouter ({len(ordre)} colonnes).')
        return []
    avant = len(ordre) - len(nouvelles)
    ajoutees = maj_db._ajouter_colonnes(conn, d, table, nouvelles)
    maj_db._ecrire_meta(conn, d, table, ordre)
    log(f'   "{table}" : +{len(ajoutees)} colonne(s) -> {", ".join(ajoutees)} '
        f'({avant} -> {len(ordre)} colonnes ; lignes existantes a NULL).')
    return ajoutees


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv[1:]
    if not args:
        raise SystemExit("Usage : python ajouter_colonne.py <dossier_dta> [--dry-run]")
    dossier = args[0]
    if not os.path.isdir(dossier):
        raise SystemExit(f"Dossier introuvable : {dossier}")

    conn = db_source.connect()
    try:
        total = []
        for _k, (fname, table) in db_source.FICHIERS.items():
            chemin = os.path.join(dossier, fname)
            if not os.path.isfile(chemin):
                print(f"   [ignore] {fname} absent du dossier.")
                continue
            if dry:
                # On n'execute RIEN : un ALTER TABLE passe en autocommit cote
                # sqlite3, un rollback ne l'annulerait pas (cf. maj_db._colonnes_sql).
                nouvelles, _ordre, d = colonnes_en_plus(conn, chemin, table)
                print(f'   [DRY-RUN] "{table}" : '
                      + (", ".join(nouvelles) if nouvelles else "rien a ajouter"))
                total += nouvelles
            else:
                total += ajouter(conn, chemin, table)
        if dry:
            print(f"[DRY-RUN] {len(total)} colonne(s) seraient ajoutee(s). Rien ecrit.")
        else:
            conn.commit()
            print(f"Termine (commit) : {len(total)} colonne(s) ajoutee(s).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
