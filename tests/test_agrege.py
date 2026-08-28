# -*- coding: utf-8 -*-
"""
test_agrege.py — Preuve d'équivalence des AGRÉGATS serveur.

Le dashboard multi-pages allège les pages district/commune en calculant les
agrégats CÔTÉ SERVEUR (rapport_core.agrege) au lieu d'embarquer les ménages bruts.
Ce test garantit que ces agrégats sont IDENTIQUES à ceux que le gabarit
(template_tail.html) calcule côté navigateur — même esprit que simuler_db.py.

Méthode : pour un district, on récupère les MENAGES bruts, on calcule les agrégats
(1) en Python via rapport_core.agrege et (2) en JavaScript via test_agrege_oracle.js
(formules COPIÉES du gabarit, exécutées par Node), puis on compare champ par champ.

Prérequis : Node.js (node) installé ; base peuplée (zones + .dta / simuler_db).
Lancer (depuis la racine du projet) :
    python tests/test_agrege.py            (district par défaut : 4405 = MAMPIKONY)
    python tests/test_agrege.py 4405
"""
import json
import os
import re
import subprocess
import sys
import tempfile

# Ce test vit dans tests/ ; on ajoute la RACINE du projet au chemin d'import pour
# retrouver config / db_source / rapport_core, quel que soit le dossier de lancement.
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RACINE not in sys.path:
    sys.path.insert(0, _RACINE)

import config
import db_source
import rapport_core

ICI = os.path.dirname(os.path.abspath(__file__))
ORACLE = os.path.join(ICI, "test_agrege_oracle.js")
SECTIONS = ("general", "gpscap", "qualite", "historique", "agents")


def _menages_du_district(code_district: int) -> list:
    """Génère une page district BRUTE (alleger=False) et en extrait MENAGES.

    On appelle rapport_core directement — et non la route allégée — pour disposer
    des ménages bruts, référence contre laquelle on compare les agrégats."""
    conn = db_source.connect()
    try:
        tmp = tempfile.mkdtemp(prefix="rsu_test_agg_")
        chemins = {"rapport": tmp, "limites": config.LIMITES_DIR,
                   "templates": config.TEMPLATES_DIR, "limites_mode": "integrees"}
        out = rapport_core.generer_rapport(
            chemins, source=db_source.source_db(conn, district=code_district),
            autoriser_vide=True)   # alleger=False par défaut -> MENAGES embarqué
    finally:
        conn.close()
    with open(out, "r", encoding="utf-8") as f:
        page = f.read()
    m = re.search(r"const MENAGES = (\[.*?\]);\nconst SEGMENTS_DEN", page, re.S)
    if not m:
        raise SystemExit("MENAGES introuvable dans la page brute.")
    return json.loads(m.group(1))


def _norm(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def main() -> int:
    code = int(sys.argv[1]) if len(sys.argv) > 1 else 4405
    menages = _menages_du_district(code)
    print(f"District {code} : {len(menages)} ménages")

    py = rapport_core.agrege(menages)["summary"]

    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="rsu_menages_")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(menages, f, ensure_ascii=False)
    try:
        out = subprocess.check_output(["node", ORACLE, tmp])
    finally:
        os.remove(tmp)
    js = json.loads(out)

    tout_ok = True
    for sec in SECTIONS:
        ok = _norm(py[sec]) == _norm(js[sec])
        tout_ok = tout_ok and ok
        print(f"  {sec:12} : {'IDENTIQUE' if ok else '### DIFFÉRENT ###'}")
        if not ok and isinstance(py[sec], dict):
            for k in py[sec]:
                if _norm(py[sec][k]) != _norm(js[sec].get(k)):
                    print(f"     1er écart : {k}\n       py={py[sec][k]!r:.120}"
                          f"\n       js={js[sec].get(k)!r:.120}")
                    break

    if tout_ok:
        g = py["general"]
        print("RESULTAT : TOUT IDENTIQUE")
        print(f"  (controle : total={g['total']} presents={g['nbPresents']} "
              f"carnet={g['nbCarnet']} segments={g['nbSegments']} agents={g['nAgents']})")
        return 0
    print("RESULTAT : DIVERGENCE")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
