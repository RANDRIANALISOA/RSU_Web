# -*- coding: utf-8 -*-
"""
tests/test_synchro_agents.py — `synchroniser_agents` pose le DISTRICT à la création.

Avant le 2026-09-28, chaque code agent trouvé dans les données de collecte
créait une fiche SANS district : 613 fiches invisibles de tout responsable ont
dû être supprimées à la main. Ces tests fixent la nouvelle règle.

Base SQLite EN MÉMOIRE, schéma minimal : la vraie base n'est jamais ouverte.

    venv/bin/python -m unittest tests.test_synchro_agents -v
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import equipes   # noqa: E402
import vad_db    # noqa: E402


def _base():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute('CREATE TABLE "district" ("code_district" INTEGER PRIMARY KEY, '
                '"nom" TEXT)')
    cur.executemany('INSERT INTO "district" VALUES (?,?)',
                    [(5201, "FENERIVE EST"), (5206, "VAVATENINA"),
                     (3307, "LALANGINA")])
    cur.execute('CREATE TABLE "chef_equipe" ("login_ce" TEXT PRIMARY KEY, '
                '"nom_prenom_ce" TEXT NOT NULL, "district_ce" BIGINT)')
    cur.execute('CREATE TABLE "agent" ("login_ae" TEXT PRIMARY KEY, '
                '"nom_prenom_ae" TEXT NOT NULL, "login_ce" TEXT, '
                '"district_ae" BIGINT)')
    cur.execute('CREATE TABLE "interview__diagnostics" '
                '("interview__key" TEXT, "responsible" TEXT)')
    cur.execute('CREATE TABLE "den_menage" ("interview__key" TEXT, "district" INTEGER)')
    conn.commit()
    return conn


def _interview(conn, cle, agent, district, diag="interview__diagnostics",
               menage="den_menage", col="district"):
    conn.execute(f'INSERT INTO "{diag}" ("interview__key","responsible") VALUES (?,?)',
                 (cle, agent))
    conn.execute(f'INSERT INTO "{menage}" ("interview__key","{col}") VALUES (?,?)',
                 (cle, district))


def _district(conn, login):
    row = conn.execute('SELECT "district_ae" FROM "agent" WHERE "login_ae"=?',
                       (login,)).fetchone()
    return None if row is None else row[0]


class SynchroniserAgents(unittest.TestCase):

    def test_district_des_interviews(self):
        conn = _base()
        _interview(conn, "k1", "EQ1_FNRV_0001", 5201)
        _interview(conn, "k2", "EQ1_FNRV_0001", 5201)
        b = equipes.synchroniser_agents_detail(conn)
        self.assertEqual(b["crees"], 1)
        self.assertEqual(b["crees_sans_district"], 0)
        self.assertEqual(_district(conn, "EQ1_FNRV_0001"), 5201)
        # Le nom reste le code, le chef d'équipe inconnu : ce sont les données
        # du téléversement Excel, pas des interviews.
        nom, ce = conn.execute('SELECT "nom_prenom_ae","login_ce" FROM "agent"').fetchone()
        self.assertEqual((nom, ce), ("EQ1_FNRV_0001", None))

    def test_contrat_d_origine_entier(self):
        conn = _base()
        _interview(conn, "k1", "EQ1_FNRV_0001", 5201)
        self.assertEqual(equipes.synchroniser_agents(conn), 1)
        self.assertEqual(equipes.synchroniser_agents(conn), 0)   # idempotent

    def test_repli_sur_la_zone_du_login(self):
        conn = _base()
        conn.execute('INSERT INTO "agent" VALUES (?,?,?,?)',
                     ("EQ_VVTN_0001", "RAKOTO", None, 5206))
        # Interview sans district renseigné -> seul le login peut parler.
        conn.execute('INSERT INTO "interview__diagnostics" VALUES (?,?)',
                     ("k1", "EQ2_vvtn_0042"))
        equipes.synchroniser_agents_detail(conn)
        self.assertEqual(_district(conn, "EQ2_vvtn_0042"), 5206)   # casse ignorée

    def test_zone_inconnue_reste_null(self):
        conn = _base()
        conn.execute('INSERT INTO "interview__diagnostics" VALUES (?,?)',
                     ("k1", "EQ1_TANN_0111"))
        b = equipes.synchroniser_agents_detail(conn)
        self.assertEqual(b["crees_sans_district"], 1)
        self.assertIsNone(_district(conn, "EQ1_TANN_0111"))

    def test_zone_ambigue_reste_null(self):
        conn = _base()
        conn.executemany('INSERT INTO "agent" VALUES (?,?,?,?)',
                         [("EQ_ABCD_0001", "A", None, 5201),
                          ("EQ_ABCD_0002", "B", None, 5206)])
        conn.execute('INSERT INTO "interview__diagnostics" VALUES (?,?)',
                     ("k1", "EQ_ABCD_0003"))
        equipes.synchroniser_agents_detail(conn)
        self.assertIsNone(_district(conn, "EQ_ABCD_0003"))

    def test_agent_sur_deux_districts_ne_tranche_pas_au_hasard(self):
        conn = _base()
        _interview(conn, "k1", "EQ1_XXXX_0001", 5201)
        _interview(conn, "k2", "EQ1_XXXX_0001", 5206)
        equipes.synchroniser_agents_detail(conn)
        self.assertIsNone(_district(conn, "EQ1_XXXX_0001"))

    def test_les_interviews_priment_sur_la_zone(self):
        conn = _base()
        conn.execute('INSERT INTO "agent" VALUES (?,?,?,?)',
                     ("EQ_VVTN_0001", "RAKOTO", None, 5206))
        _interview(conn, "k1", "EQ_VVTN_0099", 3307)
        equipes.synchroniser_agents_detail(conn)
        self.assertEqual(_district(conn, "EQ_VVTN_0099"), 3307)

    def test_district_hors_referentiel_jamais_ecrit(self):
        conn = _base()
        _interview(conn, "k1", "EQ1_ZZZZ_0001", 9999)
        equipes.synchroniser_agents_detail(conn)
        self.assertIsNone(_district(conn, "EQ1_ZZZZ_0001"))

    def test_agent_existant_sans_district_est_complete(self):
        conn = _base()
        conn.execute('INSERT INTO "agent" VALUES (?,?,?,?)',
                     ("EQ1_FNRV_0001", "RABE", "CE_FNRV_001", None))
        _interview(conn, "k1", "EQ1_FNRV_0001", 5201)
        b = equipes.synchroniser_agents_detail(conn)
        self.assertEqual((b["crees"], b["districts_poses"]), (0, 1))
        self.assertEqual(_district(conn, "EQ1_FNRV_0001"), 5201)
        # Nom et chef d'équipe intacts.
        self.assertEqual(conn.execute('SELECT "nom_prenom_ae","login_ce" FROM "agent"')
                         .fetchone(), ("RABE", "CE_FNRV_001"))

    def test_district_enregistre_jamais_remplace(self):
        conn = _base()
        conn.execute('INSERT INTO "agent" VALUES (?,?,?,?)',
                     ("EQ1_FNRV_0001", "RABE", None, 5206))
        _interview(conn, "k1", "EQ1_FNRV_0001", 5201)
        b = equipes.synchroniser_agents_detail(conn)
        self.assertEqual(b["districts_poses"], 0)
        self.assertEqual(_district(conn, "EQ1_FNRV_0001"), 5206)

    def test_marqueur_na_et_blancs_ignores(self):
        conn = _base()
        for k, code in (("k1", "##N/A##"), ("k2", "   "), ("k3", "")):
            conn.execute('INSERT INTO "interview__diagnostics" VALUES (?,?)', (k, code))
        self.assertEqual(equipes.synchroniser_agents_detail(conn)["crees"], 0)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM "agent"').fetchone()[0], 0)

    def test_base_neuve_sans_table_de_collecte(self):
        conn = sqlite3.connect(":memory:")
        self.assertEqual(equipes.synchroniser_agents(conn), 0)

    def test_vad_utilise_cq7(self):
        conn = _base()
        conn.execute(f'CREATE TABLE "{vad_db.TABLE_DIAG}" '
                     '("interview__key" TEXT, "responsible" TEXT)')
        conn.execute(f'CREATE TABLE "{vad_db.TABLE_MENAGE}" '
                     '("interview__key" TEXT, "district" INTEGER, "CQ7" INTEGER)')
        _interview(conn, "v1", "EQ1_LLGN_0007", 3307, diag=vad_db.TABLE_DIAG,
                   menage=vad_db.TABLE_MENAGE, col="CQ7")
        self.assertEqual(vad_db.synchroniser_agents(conn), 1)
        self.assertEqual(_district(conn, "EQ1_LLGN_0007"), 3307)


if __name__ == "__main__":
    unittest.main()
