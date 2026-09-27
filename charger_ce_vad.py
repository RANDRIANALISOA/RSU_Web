# -*- coding: utf-8 -*-
"""Charge le CHEF D'ÉQUIPE (CE) de chaque interview VAD dans `vad_ce`.

Le dofile INSTAT obtient le CE en fusionnant `interview__actions` filtré sur
`action == 0` (création de l'interview), dont `responsible__name` porte le login
du CE — CQ2 dans le dofile, puis `CE` après decode. Ce fichier ne fait pas
partie de l'ingestion VAD courante (`vad_db`), d'où ce chargeur séparé.

    python charger_ce_vad.py [dossier_export]

Idempotent. Réversible : DROP TABLE vad_ce;
"""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_source import connect, _placeholder

NOM = "interview__actions.dta"
ACTION_CREATION = 0


def trouver(dossier=None):
    """Chemin du fichier actions : dossier donné, sinon recherche sous BASE."""
    base = os.path.dirname(os.path.abspath(__file__))
    if dossier:
        c = os.path.join(dossier, NOM)
        return c if os.path.exists(c) else None
    trouves = glob.glob(os.path.join(base, "**", NOM), recursive=True)
    return trouves[0] if trouves else None


def charger(conn, chemin):
    import pyreadstat
    df, _ = pyreadstat.read_dta(chemin)
    if "action" not in df.columns or "responsible__name" not in df.columns:
        raise SystemExit(f"{chemin} : colonnes attendues absentes")
    d = df[df["action"] == ACTION_CREATION][["interview__key", "responsible__name"]]
    d = d.dropna().drop_duplicates("interview__key")
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS "vad_ce"')
    cur.execute('CREATE TABLE "vad_ce" ("interview__key" TEXT, "CE" TEXT)')
    ph = _placeholder(conn)
    cur.executemany(f'INSERT INTO "vad_ce" VALUES ({ph}, {ph})',
                    d.itertuples(index=False, name=None))
    cur.execute('CREATE INDEX IF NOT EXISTS ix_vad_ce ON "vad_ce"("interview__key")')
    conn.commit()
    return len(d)


if __name__ == "__main__":
    chemin = trouver(sys.argv[1] if len(sys.argv) > 1 else None)
    if not chemin:
        raise SystemExit(f"{NOM} introuvable — préciser le dossier d'export en argument")
    print(f"source : {chemin}")
    print(f"  vad_ce : {charger(connect(), chemin)} interviews")
