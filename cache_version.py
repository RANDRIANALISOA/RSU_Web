# -*- coding: utf-8 -*-
"""cache_version.py — un compteur partagé qui périme les caches de TOUS les
processus.

LE PROBLÈME
    `serveur_app._CACHE` (rapports fokontany/commune/district) et
    `vad_core._CACHE_AGREGE` vivent en mémoire. Tant qu'il n'y a qu'un
    processus, `_vider_cache()` suffit : il vide le seul cache existant.

    Avec plusieurs processus, chacun a le sien. Une transcription faite sur le
    processus A viderait le cache de A — et **pas** celui de B, qui continuerait
    à servir un rapport périmé. `_CACHE` n'a **aucune durée de vie** : il le
    servirait indéfiniment, sans rien pour le rattraper.

LA SOLUTION
    Un entier en base, incrémenté à chaque changement de données. Chaque
    processus retient la version qu'il connaît ; s'il voit un numéro plus récent,
    il vide ses propres caches. Pas de communication entre processus à organiser,
    pas de démon : la base est déjà le point commun.

    Une lecture est un `SELECT` sur une table d'UNE ligne — quelques dizaines de
    microsecondes. `serveur_app` l'espace quand même de quelques secondes, parce
    qu'une page légère coûte 1 ms et qu'on ne veut pas y ajouter une connexion.

POURQUOI PAS SIMPLEMENT UNE DURÉE DE VIE
    Une durée de vie laisse servir des données fausses pendant tout son délai, et
    fait recalculer même quand rien n'a changé. Le compteur ne périme que ce qui
    doit l'être, et au moment où il le faut.
"""
from __future__ import annotations

import db_source

TABLE = "cache_version"
_NOM = "donnees"


def creer_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(f'CREATE TABLE IF NOT EXISTS "{TABLE}" ('
                f'"nom" TEXT PRIMARY KEY, "version" INTEGER NOT NULL)')
    ph = db_source._placeholder(conn)
    cur.execute(f'INSERT INTO "{TABLE}" ("nom","version") VALUES ({ph},0) '
                f'ON CONFLICT("nom") DO NOTHING', (_NOM,))
    conn.commit()


def lire(conn) -> int:
    """Version courante. 0 si la table n'existe pas encore : un processus qui
    démarre ne doit pas échouer parce qu'un autre n'a pas fini son amorçage."""
    ph = db_source._placeholder(conn)
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT "version" FROM "{TABLE}" WHERE "nom"={ph}', (_NOM,))
        ligne = cur.fetchone()
        return int(ligne[0]) if ligne else 0
    except Exception:
        return 0


def incrementer(conn) -> int:
    """Signale aux AUTRES processus que leurs caches sont périmés.

    L'incrément se fait en SQL (`version = version + 1`) et non en Python :
    deux processus qui transcrivent en même temps ne doivent pas écraser
    l'incrément l'un de l'autre.
    """
    ph = db_source._placeholder(conn)
    for essai in (1, 2):
        try:
            cur = conn.cursor()
            cur.execute(f'UPDATE "{TABLE}" SET "version" = "version" + 1 '
                        f'WHERE "nom"={ph}', (_NOM,))
            if cur.rowcount == 0:
                cur.execute(f'INSERT INTO "{TABLE}" ("nom","version") '
                            f'VALUES ({ph},1)', (_NOM,))
            conn.commit()
            return lire(conn)
        except Exception:
            if essai == 1:
                creer_table(conn)
                continue
            return 0
    return 0
