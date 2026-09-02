# RSU_Web — Conception de l'application web en ligne

## 0. En une phrase

Transformer le rapport RSU 2026 (aujourd'hui produit par un `.exe` de bureau) en
une **application web** : au lieu de double-cliquer sur un programme et de choisir
des fichiers `.dta`, l'utilisateur ouvrira une **page dans son navigateur**, et
l'application lira les données dans une **base PostgreSQL** pour afficher le même
rapport interactif.

> État (maj 2026-08-17) : l'application locale marche avec, dans `serveur_app.py` :
> **login** vérifié en base avec **mots de passe hachés** (PBKDF2) et **comptes/rôles**
> (`utilisateurs.py` : **9 rôles** via table de référence `responsabilite` (FK
> `code_responsable`), dont **Admin** ; comptes avec **téléphone / CIN / e-mail**
> (facultatifs, validés) ; **affectation** district(s)/communes par
> clés étrangères, **RESPECTÉE** au routage : `perimetre(u)` + `_perimetre_vue`),
> **page de sélection** Province/Région/District + limites + type de suivi (référentiel
> `zones` depuis l'Excel `FKT_ampiasan_SS`), et un **dashboard multi-pages (MPA)** :
> une page HTML par section chargée au clic (routes
> `/vue/<section>[/commune|/fokontany/<code>]`), avec allègement des pages
> district/commune par **agrégats calculés côté serveur** (Vue générale : 24 Mo→265 Ko,
> ~92×, chiffres prouvés identiques). **Toutes les sections** ont la descente
> commune→fokontany (sous-menu `<…-drill>` ; périmètre pris de `SCOPE`, pas des ménages),
> et **« Segments multiples »** est agrégé aux 3 niveaux (district/commune/fokontany, par
> couple fokontany×code). Chaque rôle atterrit sur SA page : **Admin** →
> espace Admin (`/admin` : journal connexion + transcriptions, gestion utilisateurs =
> **ajouter / MODIFIER (formulaire pré-rempli)** cascade + import Excel, couverture) ;
> **Expert survey** → **ingestion**
> (`/transcription` : choix Dénombrement / Visite à domicile ; téléversement du dossier
> — **TOUS les fichiers et sous-dossiers** conservés, ex. `Questionnaire/` — →
> validation → transcription incrémentale, journalisée) ; **Traitement** → **espace
> Traitement** (`/traitement` : choix Tableau de bord OU **remplir la base Chef d'Équipe
> / Agent** par téléversement de 2 Excel) ; **Logistique District /
> Inter-Communale** → **espace Logistique & Finances** (`/logistique`, guide tiré du
> manuel, pas de dashboard) ; les autres → sélection + dashboard borné à leur périmètre.
> **Chefs d'Équipe et Agents** (`equipes.py`, tables `chef_equipe`/`agent`) sont **liés
> au dénombrement** : le code agent `interview__diagnostics.responsible` est une **clé
> étrangère** vers `agent(login_ae)` ; tout code du dénombrement absent d'`agent` y est
> **auto-créé** (nom = le code) ; dans le rapport, le **nom** de l'agent s'affiche au
> lieu du code s'il est renseigné (`agents_noms`). Le **CSS et Chart.js** sont dans
> `assets/` (pages légères + graphiques hors-ligne),
> les **images** dans `images/`. Les tables `.dta` sont **mises à jour incrémentalement**
> (`maj_db.py`) et leurs codes géo sont des **clés étrangères** vers `zones`. Pages
> dynamiques **non mises en cache** (`Cache-Control: no-store`).
> **Nombre de ménages attendus** : la table `commune` a une colonne `"nombreMenage"`
> (projection RGPH-3 2025) remplie depuis l'Excel dérivé `MENAGES_PAR_COMMUNE_2025.xlsx`
> (`zones.charger_menages`, CLI `python zones.py menages`). Sur la page **Vue générale**
> (district/commune), un panneau **COUVERTURE** compare le **dénombrement réalisé** à
> l'attendu (taux, jours restants au rythme observé ; `rapport_core.couverture`), avec un
> **tableau par commune** au niveau district. Un bouton **flottant « Exporter rapport »**
> télécharge un **classeur Excel** (route `/export/rapport.xlsx`, module `export_rapport.py`) :
> feuille **Rapport global** (couverture + qualité par commune/fokontany), feuille
> **Dénombrement par agent-jour** (un tableau par chef d'équipe), feuille **BaseDenParAgent**
> (table plate agent×fokontany×date).
> **COLLABORATION (maj 2026-08-31)** : au-delà du dashboard, l'app porte désormais une
> couche de **suivi d'équipe** (voir la section datée 2026-08-31) — **Journal de bord**
> (`journal.py`, `/journal` : l'équipe technique écrit ses activités du jour avec rappel
> par bulle, entrées modifiables par leur auteur (cree_le figé + modifie_le), historique
> complet ; les coordonnateurs LISENT, filtres district/fonction/
> axe/nom/date ; **SUIVI de complétude** `/journal/suivi` = qui a écrit ou non chaque
> jour de mission, par poste/district/axe, le National choisissant son district),
> **Consignes / instructions** (`consignes.py`, `/consignes` : les deux
> coordonnateurs envoient des consignes ciblées par rôles+districts, reçues via une bulle,
> modifiables/supprimables par l'auteur ; lecture filtrable), et **« Mon profil »**
> (`/profil`, tous rôles : chacun édite ses CIN/téléphone/N° Orange Float/e-mail/**sexe**,
> le reste réservé à l'Admin). Restent surtout :
> câbler l'allègement des **autres sections** (§6 étape 3), le **suivi VAD** et les
> **outils transactionnels logistiques** quand leurs données existeront, **changer le
> compte d'amorçage**, **PostgreSQL** effectif (`RSU_DB_URL`), **FastAPI**, **HTTPS**,
> **hébergement** — étape par étape, voir §6 « Feuille de route ».

## 1. Deux projets bien séparés (RÈGLE IMPORTANTE)

Il y a désormais **deux dossiers frères**, à ne pas mélanger :

| Dossier | Application | Contenu |
|---|---|---|
| `..\RSU_Rapport\` | **`.exe` de bureau** (existant) | GUI tkinter, licence, build PyInstaller, base de préchargement, données `DATA/`, contours `LimitesFokontany/` |
| `.\RSU_Web\` (ici) | **application web** (nouveau) | serveur web, adaptateur base de données, config, + copies du moteur partagé |

**Règle de séparation :**
- Un fichier utile **seulement au web** vit **ici** (`RSU_Web/`).
- Un fichier utile **seulement à l'exe** reste dans `RSU_Rapport/`.
- Un fichier **partagé** (le moteur) est **copié** ici (voir §3, « fichiers vendus »).

### Fichiers partagés = copies à garder synchronisées ⚠️
Le web réutilise le **moteur** de génération du rapport. Pour que `RSU_Web/` soit
**autonome** (déployable seul chez un hébergeur), ces fichiers en sont des **copies** :

- `rapport_core.py` — moteur (assemble le HTML, calcule les agrégats).
- `lire_dta.py` — lecteur `.dta` (utile seulement pour la *simulation*, pas en prod).
- `templeteHtml/` — **gabarits = source unique du rendu** (structure + JS du rapport).
- `assets/` — **CSS (`rapport.css`) et Chart.js (`chart.umd.min.js`)** sortis des
  gabarits (cf. §3) ; en mode exe autonome, `rapport_core` les ré-embarque dans le HTML.

👉 **Si vous modifiez le RAPPORT** (design, menus, carte, agrégats), vous éditez les
gabarits `templeteHtml/`, `assets/` et/ou `rapport_core.py`. Ils existent **dans les
deux projets** : après un changement, **recopier ENSEMBLE** la version à jour dans
l'autre dossier (les blocs web — MPA, allègement, assets — sont **inertes côté exe**,
gardés par `typeof ACTIVE_SECTION`/`SUMMARY`/`ZONES_REF`, mais les copies ne doivent
pas diverger). ⚠️ **Resynchro en attente** pour tout le travail web récent (gabarits +
`rapport_core.py` + `assets/`). Ou, plus tard, factoriser en un emplacement partagé
(§7). Le rapport final doit rester identique entre l'exe et le web.

## 2. Ce qu'est (et n'est pas) une application web — pour bien démarrer

Une application web, c'est trois morceaux :

1. **Le navigateur (client)** — ce que voit l'utilisateur. Ici, c'est **déjà fait** :
   le rapport EST une page HTML/JS autonome (`Rapport_RSU2026.html`).
2. **Le serveur** — un programme qui tourne en permanence, reçoit les requêtes du
   navigateur et renvoie des pages. C'est la **nouveauté** construite. Aujourd'hui :
   `serveur_app.py` (login, sélection, dashboard multi-pages piloté par la base ;
   `serveur_web.py` = ancien prototype gardé en référence). Demain : FastAPI (étape 5).
3. **La base de données** — où vivent les données. Ici : **PostgreSQL** (les `.dta`
   actuels en sont un export). L'app lira la base au lieu de fichiers.

Différence clé avec l'exe : l'exe tourne **sur la machine de l'utilisateur** ; le
serveur web tourne **sur UN ordinateur central** (le vôtre en local, puis un
hébergeur), et **plusieurs utilisateurs** s'y connectent par le réseau.

## 3. Structure du dossier `RSU_Web/`

```
RSU_Web/
├── CLAUDE.md            <- ce fichier (conception)
├── README.md           <- démarrage rapide (comment lancer)
├── config.py           <- TOUS les chemins au même endroit (DATA, contours, base)
│
│   ── Code de l'application web ──
├── serveur_app.py      <- SERVEUR pilote par la base. Contient desormais :   [FONCTIONNEL]
│                          - PREFIXE d'URL : tout est sous /rsu (config.PREFIXE).
│                            do_GET/do_POST depreffixent en entree ; _redirige et
│                            _prefixer (liens href/action/src, url(/img)) preffixent
│                            en sortie ; rapport = assets_url/nav_base preffixes a la
│                            source (servi sans _prefixer). Cookie Path=/rsu.
│                          - login (page + session cookie, /login /logout)
│                          - BANDEAU UTILISATEUR : bandeau_utilisateur(sess) (barre
│                            fixe haut-droite : initiales + nom/prenom + role +
│                            lien /logout) injecte par _html() apres <body> (via
│                            _RE_BODY), APRES _prefixer -> present sur CHAQUE page
│                            connectee, RAPPORT COMPRIS (servi sans _prefixer, lien
│                            deja prefixe). Rien si pas de session (login, erreurs).
│                          - page de selection Province/Region/District + limites
│                            + type de suivi (Denombrement / Visite a domicile).
│                            Rôle Traitement : zone geo MASQUEE (district = affectation),
│                            seuls limites + type de suivi sont demandes.
│                          - DASHBOARD MULTI-PAGES : /vue/<section>[/commune/<code>
│                            |/fokontany/<code>] (8 sections), /suivi -> /vue/general.
│                            rapport_vue() filtre au perimetre + ALLEGE district/
│                            commune (SECTIONS_ALLEGEES) via agregats serveur.
│                          - AFFECTATION RESPECTEE : perimetre(u) -> (districts,
│                            communes) ; _perimetre_vue impose un district du perimetre
│                            + borne commune/fokontany (403), _zone_autorisee ; role
│                            « communes » -> vue globale = AGREGAT de ses communes sauf
│                            Carte GPS. Multi-district = 1 district a la fois (selection
│                            restreinte). Cf. §6 etape 4.
│                          - ROUTAGE PAR ROLE (connexion + gardes) : Admin -> /admin ;
│                            Expert survey -> /transcription ; Logistique -> /logistique ;
│                            autres -> /choix. Chaque groupe est FERME hors de sa zone
│                            (redirige vers sa page).
│                          - INGESTION Expert (transcription.py) : /transcription (choix
│                            Denombrement / VAD), /transcription/denombrement (upload
│                            du DOSSIER : _relpath_upload preserve les sous-dossiers, ex.
│                            Questionnaire/ ; garde anti-traversee _sous_dossier ; les 3
│                            .dta requis a la RACINE), /transcription/vad (indisponible).
│                          - ESPACE TRAITEMENT (equipes.py) : /traitement (choix Tableau
│                            de bord OU base CE/Agents), /traitement/equipes (televerser
│                            2 Excel -> transcrire), /traitement/modele/{chef,agent}.xlsx.
│                            Role Traitement ; le dashboard reste via /choix.
│                          - ROUTAGE role : accueil_role() -> Traitement va sur /traitement.
│                          - ESPACE LOGISTIQUE (logistique.py) : /logistique[/taches|
│                            /paiement|/pieces|/budget] (roles Logistique, pas de dashboard).
│                          - EXPORT EXCEL : /export/rapport.xlsx (memes gardes que /vue :
│                            _perimetre_vue, district de la session + communes du role) ->
│                            export_rapport.generer_bytes(...) renvoye via _octets(...)
│                            (Content-Disposition attachment). Bouton FLOTTANT bas-droite
│                            « Exporter rapport » injecte par initMPA (le coin haut-droite
│                            est occupe par le bandeau utilisateur).
│                          - statiques : /assets/<css|js>, /img/accueil
│                          - menu Commune->Fokontany (/menu) + /fokontany/<code>
│                          - pages dynamiques NON mises en cache (Cache-Control:no-store).
├── zones.py            <- Excel FKT_ampiasan_SS -> 5 tables NORMALISEES (3NF)  [FONCTIONNEL]
│                          province/region/district/commune/fokontany (PK+FK,
│                          relations un-a-plusieurs) + arbre Prov/Reg/District.
│                          NOMBRE DE MENAGES : la table `commune` a une colonne
│                          `"nombreMenage"` (BIGINT, projection RGPH-3 2025 ; casse a
│                          respecter -> TOUJOURS entre guillemets en SQL). charger_menages()
│                          la remplit depuis MENAGES_PAR_COMMUNE_2025.xlsx (rappele en fin
│                          de charger_excel_vers_db si l'Excel est present) ;
│                          attendus_communes(ccodes) pour la couverture ; CLI
│                          `python zones.py menages`.
├── utilisateurs.py     <- comptes de connexion en base (table `utilisateurs`)  [FONCTIONNEL]
│                          nom_prenom, login, mot de passe HACHE (PBKDF2),
│                          COORDONNEES facultatives telephone/cin/email (colonnes
│                          nullables, validees par valider_coordonnees : CIN=12
│                          chiffres, email simple, tel 8-15 chiffres ; migration
│                          auto via _reconstruire), et
│                          `code_responsable` = CLE ETRANGERE vers la table de
│                          REFERENCE `responsabilite` (code_responsable PK,
│                          libelle_responsable ; 9 roles seedes : 1 Admin, 2 Comites
│                          Techniques, 3 Coord Nationale, 4 Coord regionale, 5 Traitement,
│                          6 Expert survey, 7 Superviseur Technique, 8 Logistique District,
│                          9 Logistique Inter-Communale). Ordre/codes modifiables via
│                          RESPONSABILITES_REF : `_renumeroter_codes` remappe alors les
│                          comptes existants (par LIBELLE, au demarrage). Affectation par
│                          FORME de role : district_affectation (FK district) pour
│                          mono-district ; communes via `superviseur_commune` (FK) ;
│                          districts (1 a 5) via NOUVELLE liaison `responsable_district`
│                          (FK district) pour multi-district. valider_affectation +
│                          MAX_DISTRICTS/MAX_COMMUNES_SUPERVISEUR=5 ; pour un role
│                          communes, le district est DEDUIT des communes (toutes du
│                          MEME district, sinon refus ; zones.district_de_commune).
│                          authentifier()/
│                          lister() renvoient le LIBELLE (JOIN) -> comparaisons par
│                          libelle inchangees. Migration : ancien `responsabilite`
│                          TEXT -> code (reconstruction SQLite, comptes conserves).
│                          Regles par role (cf. §6 etape 4). modifier() met a jour un
│                          compte (login = cle, non modifiable ; mdp inchange si vide ;
│                          affectation revalidee + liaisons reconstruites) ; obtenir()
│                          pour le pre-remplissage. SEXE : colonne `sexe` facultative
│                          (« Masculin »/« Feminin », SEXES + valider_sexe) migree auto.
│                          modifier_profil(login, tel/cin/email/float/sexe) = MAJ
│                          LIBRE-SERVICE (route /profil) : ces 5 champs SEULEMENT, login
│                          pris de la session ; rien d'autre (role/affectation = Admin).
│                          CLI : init/add/list/passwd/actif/del. /login -> authentifier().
├── journal.py          <- AUDIT : journal_connexion (login, role, duree),          [FONCTIONNEL]
│                          tentative_connexion (echecs) et journal_transcription
│                          = 1 ligne par EVENEMENT d'ingestion (evenement =
│                          Televersement|Transcription ; statut = Reussi|Echec ;
│                          quand, detail, bilan). consigner() ecrit succes ET echecs ;
│                          transcriptions(login=) filtre pour l'Expert. Migration
│                          idempotente (ADD COLUMN evenement/statut/detail). Affiche
│                          sur la page Expert (les siens) ET le tableau de bord Admin.
│                          fmt_quand() = JJ/MM/AAAA HH:MM. Rempli par serveur_app.
│                          JOURNAL DE BORD (activites quotidiennes) : table
│                          journal_activite(id, login, nom_prenom, fonction, zone,
│                          code_district, date_jour, journal, cree_le FIGE, modifie_le).
│                          ecrire_activite (equipe technique, plusieurs entrees/jour),
│                          obtenir_activite/modifier_activite (edition par le
│                          proprietaire ; cree_le fige, modifie_le horodate), a_ecrit_le
│                          (bulle de rappel), mes_activites (page ecriture), activites
│                          (LECTURE bornee au perimetre + filtres district/fonction/
│                          zone/nom/date), options_lecture (valeurs distinctes pour
│                          les listes ; le filtre zone/axe est DEPENDANT district+role).
│                          SUIVI : dates_ecrites(logins) = {login: jours ecrits} et
│                          plage_dates(debut) = tous les jours de mission -> page
│                          /journal/suivi (completude par poste/district/axe).
│                          Route /journal (serveur_app), cf. section datee 2026-08-31.
├── consignes.py        <- CONSIGNES / INSTRUCTIONS des Coordonnateurs.          [FONCTIONNEL]
│                          Tables consigne(id, auteur_*, roles_cibles, districts_cibles,
│                          titre, message, cree_le) et consigne_lecture(consigne_id,
│                          login, lu_le). envoyer() ; _concerne(role,districts,...) =
│                          ciblage (roles_cibles='TOUS'|libelles sep '|' ;
│                          districts_cibles='TOUS'|codes sep ',') ; pour_utilisateur/
│                          non_lues/marquer_toutes_lues (destinataires) ; envoyees_par
│                          (emetteur). Routes /consignes[/nouvelle], bulle en HAUT-
│                          GAUCHE. Cf. section datee 2026-08-31.
├── admin.py            <- ESPACE ADMIN (reserve role Admin) : tableau de bord,      [FONCTIONNEL]
│                          journal, gestion utilisateurs = 3 PAGES (liste
│                          /admin/utilisateurs avec colonne Contact + bouton MODIFIER ;
│                          ajout+import Excel /admin/utilisateurs/ajouter ; MODIFIER
│                          /admin/utilisateurs/modifier?login= = formulaire PRE-REMPLI,
│                          affectation courante pre-selectionnee par JS (PRESEL)).
│                          Ordre du formulaire ET du modele Excel : nom_prenom,
│                          responsabilite, telephone, cin, email, login, mot_de_passe,
│                          district/communes/districts. Widgets d'affectation partages
│                          (JS _cascade_js : montre le bon widget selon le role) —
│                          1 ligne Prov/Reg/Dist (mono-district), 5 lignes (multi,
│                          name=district_multi), roles communes = 1 cascade + 5 listes
│                          de communes (name=commune_multi) ; district DEDUIT ;
│                          couverture des affectations, TRANSCRIPTIONS RECENTES
│                          (_table_transcriptions : date+heure, personne, district,
│                          evenement, statut Reussi/Echec, detail), modele Excel +
│                          exports CSV. Routes /admin* dans serveur_app (403 si non-Admin).
├── transcription.py    <- PAGE EXPERT SURVEY (reserve, 403 sinon).                 [FONCTIONNEL]
│                          A la connexion -> /transcription = PAGE DE CHOIX (2 cartes) :
│                          Denombrement (page actuelle, /transcription/denombrement) ou
│                          Visite a domicile (/transcription/vad = « pas encore
│                          disponible », structure BD VAD absente). Denombrement :
│                          televerse le DOSSIER (webkitdirectory) -> TOUS les fichiers ET
│                          sous-dossiers (ex. Questionnaire/) ranges sous
│                          UPLOAD_DIR/<code_district>/ en conservant l'arborescence
│                          (_relpath_upload retire le dossier racine, garde le reste ;
│                          _sous_dossier = garde anti-traversee)
│                          -> apercu (dry-run) -> transcription incrementale (maj_db).
│                          VALIDATION avant ecriture (temp) : les 3 .dta requis A LA
│                          RACINE ET la variable `district` de DEN_MENAGE == district de
│                          l'Expert, sinon REFUS (db_source.districts_du_den). Routes
│                          /transcription* dans serveur_app. Journalise CHAQUE issue
│                          (televersement reussi/refuse, transcription reussie/echouee)
│                          via journal.consigner ; la page affiche « Historique de mes
│                          transcriptions » (_table_historique, filtre sur son login).
├── logistique.py       <- ESPACE LOGISTIQUE & FINANCES (roles Logistique District   [FONCTIONNEL]
│                          et Logistique Inter-Communale = « Responsable Logistique et
│                          Financier »). PAS d'acces au tableau de bord : espace dedie
│                          construit depuis le manuel FORMATIONLOG. 5 pages (routes
│                          /logistique[/taches|/paiement|/pieces|/budget]) : accueil
│                          (affectation), taches par etape (check-lists avant/pendant/
│                          apres formation + collecte), paiement Mvola (3 etapes +
│                          regles), pieces a gerer, budget de reference. GUIDE + SUIVI
│                          (pas de BD finances/pieces) : outils transactionnels
│                          (paiement, upload scans) affiches « en cours de conception ».
│                          A la connexion -> /logistique ; dashboard/selection ferme
│                          (redirige /logistique) ; 403 si non-logistique.
├── equipes.py          <- BASE CHEFS D'EQUIPE / AGENTS (role Traitement).       [FONCTIONNEL]
│                          Tables chef_equipe(login_ce PK, nom_prenom_ce) et
│                          agent(login_ae PK, nom_prenom_ae, login_ce -> FK chef_equipe).
│                          transcrire(conn, xlsx_chef, xlsx_agent) = UPSERT (ajoute/
│                          modifie/rien-supprimer) : CE d'abord, puis Agents (login_ce
│                          doit exister). En-tetes tolerants (alias). Modeles Excel +
│                          pages (choix Traitement, formulaire 2 fichiers).
│                          LIEN DENOMBREMENT : synchroniser_agents(conn) cree dans
│                          `agent` tout code de interview__diagnostics.responsible
│                          absent (nom = le code) -> integrite FK garantie cote Python ;
│                          noms_agents(conn) = {code: nom} des agents dont le nom != code
│                          (passe au rapport pour afficher le nom au lieu du code) ;
│                          agents_et_chefs(conn) = {login_ae: {nom, chef_login, chef_nom}}
│                          (LEFT JOIN agent->chef_equipe), utilise par l'export Excel.
├── export_rapport.py   <- EXPORT EXCEL du rapport (par district).            [FONCTIONNEL]
│                          generer_bytes(conn, code_district, nom, communes=) : reconstruit
│                          la liste des menages via rapport_core (_charger_diagnostics
│                          agents_noms=None -> garde les CODES agent, _charger_segments,
│                          _construire_menages) puis openpyxl. 3 feuilles :
│                          (1) « Rapport global » : couverture par commune vs projection
│                          RGPH-3 2025 (+total district), qualite par commune (denombres,
│                          dont avec/sans carnet, scanne, %GPS), 1 tableau/commune par
│                          fokontany ; (2) « Denombrement par agent-jour » : UN tableau par
│                          chef d'equipe (commune/agent en lignes, dates en colonnes) ;
│                          (3) « BaseDenParAgent » : table PLATE (commune, chef, agent,
│                          fokontany, dates). Carnet : {1,2}=avec, 3=sans, 1=scanne ;
│                          GPS = lat&lon numeriques. STYLE : en-tete texte FONCE sur fond
│                          CLAIR (jamais blanc/blanc), couleurs ARGB alpha OPAQUE « FF »
│                          (sinon LibreOffice rend transparent), bordures, source en
│                          italique sous chaque tableau, ligne vide titre/tableau.
├── serveur_web.py      <- ancien prototype par upload de .dta (garde en reference)
├── db_source.py        <- lire une base SQL comme si c'était un .dta       [FONCTIONNEL]
│                          source_db(conn, district=/commune=/communes=/fkt=) : filtre
│                          WHERE (communes= : IN (...), vue globale d'un Superviseur).
│                          FK_ZONES : den_menage.region/district/commune/fokontany/
│                          num_fkt -> cles etrangeres vers les tables `zones`.
│                          FK_AGENT : interview__diagnostics.responsible -> agent(login_ae)
│                          (declarative ; _coldefs + migration assurer_fk_diagnostics).
│                          _fk_de(table) reunit FK_ZONES + FK_AGENT.
├── simuler_db.py       <- scénario .dta -> base SQL -> rapport (preuve)     [FONCTIONNEL]
├── maj_db.py           <- MISE A JOUR INCREMENTALE des 3 tables depuis un    [FONCTIONNEL]
│                          dossier de .dta : ajoute les nouvelles lignes,
│                          modifie les changees, ne SUPPRIME rien (upsert par
│                          cle). SQLite ou PostgreSQL (RSU_DB_URL). --dry-run.
│                          maj_depuis_dossier() renvoie un bilan structure et leve
│                          ErreurMaj (web-safe, pas de SystemExit). Utilise par
│                          transcription.py (page Expert survey).
├── tests/              <- tests (lancer depuis la racine : python tests/<x>)
│   ├── test_agrege.py     PREUVE : agregats serveur (rapport_core.agrege) ==
│   │                      formules du gabarit (Node), champ par champ  [FONCTIONNEL]
│   └── test_agrege_oracle.js  oracle JS (formules copiees du gabarit) pour test_agrege
│
│   ── Données locales & médias ──
├── FKT_ampiasan_SS.xlsx <- decoupage administratif de Madagascar (source de `zones`)
├── MENAGES_PAR_COMMUNE_2025.xlsx <- menages estimes 2025 par commune (projection
│                          RGPH-3 croisee avec FKT_ampiasan_SS par nom district+commune ;
│                          feuille `menages_par_commune`, colonnes code_commune +
│                          menages_estimes_2025). Source de commune."nombreMenage"
│                          (zones.charger_menages). Construit hors-ligne (appariement de
│                          noms + agregation des villes), non regenere par l'app.
├── rsu_local.sqlite    <- base SQLite locale (den_menage, roster, zones, …)
├── images/             <- médias (banniere login `images.jfif`), servi /img/accueil
├── login.html          <- ancienne maquette de login autonome (le serveur gere tout, cf. §6)
│
│   ── Moteur + assets partagés (COPIES du projet exe — cf. §1) ──
├── rapport_core.py     <- moteur : assemble le HTML + agrege() (agregats prouves).
│                          generer_rapport(agents_noms={code:nom}) optionnel : le code
│                          agent (responsible) est remplace par le NOM si renseigne
│                          (defaut None -> exe inchange, garde le code).
│                          COUVERTURE : couverture(menages, attendus, niveau) calcule
│                          denombrement realise vs attendu (taux, jours restants =
│                          restant/rythme, rythme = realise/jours travailles) + detail
│                          par commune. generer_rapport(menages_attendus=) ecrit
│                          `const COUVERTURE` (garde par typeof COUVERTURE -> exe inchange).
├── lire_dta.py         <- lecteur .dta (pour la simulation uniquement)
├── assets/             <- CSS + Chart.js sortis du gabarit (pages legeres, offline)
│   ├── rapport.css        (source unique du style, marqueur <!--RSU_STYLES-->)
│   └── chart.umd.min.js   (copie locale, marqueur <!--RSU_CHARTJS-->)
└── templeteHtml/       <- gabarits du rapport (structure + JS ; source du rendu)
    ├── template_head.html
    └── template_tail.html
```

**Non dupliqués ici** (trop gros, référencés par `config.py` dans le projet exe) :
- `DATA/` (40 Mo) — les `.dta` de simulation. En **production**, remplacés par la base.
- `LimitesFokontany/` (108 Mo, 19 454 fichiers) — les contours des fokontany.

En production, ces chemins seront redéfinis par variables d'environnement (voir §5).

## 4. Comment ça marche (architecture actuelle)

Le point de conception central : **le moteur ne connaît pas la provenance des
données**. `rapport_core.generer_rapport(chemins, source=...)` lit les données à
travers un petit objet exposant seulement 4 choses : `.nobs`, `.varnames`,
`.col(nom)`, `.col_decoded(nom)`. On peut donc lui donner :

- soit des **fichiers `.dta`** (défaut, `source=None`) — comme l'exe ;
- soit une **table de base de données** (`source=db_source.source_db(conn)`) —
  `db_source.DbDataset` fait « passer » une table SQL pour un `.dta`.

```
                         ┌─────────────────────────┐
   .dta  ───────────────▶│                         │
                         │  rapport_core           │──▶  Rapport_RSU2026.html
   Base SQL ── DbDataset ▶│  (moteur, inchangé)     │
                         └─────────────────────────┘
```

**Portabilité SQLite ↔ PostgreSQL** : `db_source.py` passe par la norme Python
**DB-API 2.0**. Le même code marche pour `sqlite3` (dans Python, zéro installation,
pour simuler tout de suite) et `psycopg` (PostgreSQL, en production). Seule la
**connexion** change (`config.RSU_DB_URL`).

## 5. Lancer les choses (voir aussi README.md)

```
# 1) Charger le referentiel geographique (Excel -> table `zones`) :
python zones.py
#    -> lit FKT_ampiasan_SS.xlsx (20 256 fokontany) dans la base courante.
#    (le nombre de menages par commune est rempli automatiquement si
#     MENAGES_PAR_COMMUNE_2025.xlsx est present ; sinon : python zones.py menages)

# 1bis) Remplir/mettre a jour commune."nombreMenage" sans recharger les zones :
python zones.py menages
#    -> lit MENAGES_PAR_COMMUNE_2025.xlsx (projection RGPH-3 2025 par commune).

# 2) Lancer l'application (login + selection + dashboard + admin) :
python serveur_app.py
#    -> TOUTE l'appli est servie sous le prefixe /rsu (config.PREFIXE, env RSU_PREFIXE).
#       Ouvrir http://127.0.0.1:8000/rsu/choix (/ et les URL sans prefixe y redirigent).
#       (compte d'amorcage RSU/RSU = role Admin, A CHANGER)
#       login role Admin -> /admin (journal, gestion utilisateurs, couverture) ;
#       autres roles -> selection (Province/Region/District, limites, type de suivi)
#       -> /vue/general (dashboard multi-pages). Clic section = /vue/<section> (district) ;
#          sous-menu commune/fokontany = descente au perimetre.

# 3) Simulation « données en base » (SQLite local, rien à installer) :
python simuler_db.py
#    -> transcrit les .dta en base SQLite, génère le rapport DEPUIS la base,
#       et vérifie qu'il est identique au rapport issu des .dta.

# 3bis) Preuve d'equivalence des AGREGATS serveur (necessite Node.js) :
python tests/test_agrege.py
#    -> compare rapport_core.agrege() (Python) aux formules du gabarit (Node) sur
#       le district : doit afficher « TOUT IDENTIQUE ». A relancer apres toute
#       modif d'une formule d'agregat.

# 3ter) Mise a jour INCREMENTALE des tables depuis un nouvel export .dta :
python maj_db.py [dossier_dta] [--dry-run]
#    -> ajoute les lignes absentes, met a jour les changees, ne supprime rien.
#       Cle : interview__key (den_menage, interview__diagnostics) ;
#       (interview__key, segment_roster__id) pour segment_roster. Idempotent.
#       Sans argument : dossier = config.DATA_DIR. --dry-run = simuler sans ecrire.

# 3quater) Gerer les comptes de connexion (mots de passe haches, saisis au clavier) :
python utilisateurs.py add                 # ajouter un utilisateur (interactif)
python utilisateurs.py list                # lister les comptes (sans mots de passe)
python utilisateurs.py passwd <login>      # changer un mot de passe
python utilisateurs.py actif <login> on|off#   activer / desactiver un compte
python utilisateurs.py del   <login>       # supprimer un compte
#    -> la table est aussi creee automatiquement au demarrage de serveur_app.py ;
#       si elle est vide, un compte d'amorcage RSU/RSU est cree (A CHANGER).

# 4) Bascule PostgreSQL (le mot de passe est saisi par l'utilisateur, jamais par l'assistant) :
pip install "psycopg[binary]"
set RSU_DB_URL=postgresql://utilisateur:motdepasse@localhost:5432/rsu
python zones.py          # (re)charger les zones dans PostgreSQL
python simuler_db.py     # (re)charger les .dta dans PostgreSQL
```

## 6. Feuille de route (du débutant à la production)

Chaque étape est petite et testable. **Ne pas sauter d'étape.**

- [x] **Étape 0 — Prototype local**. Serveur qui génère le rapport (`serveur_web.py`).
- [x] **Étape 1 — Lire une base de données**. Adaptateur `db_source` + preuve
      d'équivalence (`simuler_db.py`), sur SQLite (simulation de PostgreSQL).
- [x] **Étape 2 — Vrai PostgreSQL en local (simulation)**. PostgreSQL 18 installé
      et actif. La base **`rsu`** est créée et **peuplée** : zones normalisées
      (`zones.py`) + données `.dta` (`simuler_db.py`), et le rapport généré depuis
      PostgreSQL est **identique octet à octet** à celui issu des `.dta` (preuve).
      L'application entière tourne sur PostgreSQL quand `RSU_DB_URL=postgresql://
      postgres:...@localhost:5432/rsu` est défini (sinon SQLite par défaut).
      ⚠️ Reste pour la **vraie** production : le schéma réel des données RSU
      (tables/colonnes/libellés) — différent de cette simulation — devra être
      branché dans `db_source.FICHIERS` et le décodage des labels le moment venu.
- [~] **Étape 3 — Le serveur lit la base** (au lieu de l'upload de `.dta`).
      **FAIT pour le fokontany** : `serveur_app.py` sert un menu Commune→Fokontany
      (`/menu`) et, au clic, génère à la demande le rapport **allégé** d'un seul
      fokontany (~150 Ko / ~200 ménages au lieu de 25 Mo / 58 653 — testé, 100×
      plus léger, 0,5 s), via une source filtrée (`db_source.source_db(conn,
      fkt=...)` → `DbDataset` avec clause `WHERE`), sans toucher au gabarit.
      **FAIT aussi — sélection géographique** : `zones.py` charge l'Excel
      `FKT_ampiasan_SS` (6 provinces, 23 régions, 120 districts, 1 704 communes,
      20 256 fokontany) dans **5 tables normalisées (3NF)** reliées par clés
      primaires/étrangères (province→region→district→commune→fokontany, relations
      un-à-plusieurs) ; la page d'accueil après login propose un choix
      **Province → Région → District** (listes déroulantes dépendantes), le mode de
      **limites** (OCHA 2018 / générées / dossier via chemin) et le **type de suivi**
      (Dénombrement / Visite à domicile), enregistré en session.
      **FAIT aussi — suivi par district** : après la sélection, `/suivi` ouvre le
      **rapport de dénombrement filtré sur le district** (`source_db(conn,
      district=...)` : DEN filtré sur la colonne `district`, ROSTER/DIAG via ses
      interview__key). Un district **sans données** produit un rapport à **sections
      vides** (`autoriser_vide=True` dans `rapport_core`) mais dont la **carte
      affiche quand même les contours** du district (`codes_geo=` = tous les codes
      fokontany du district via `zones.codes_fokontany_district`). Le mode de
      limites choisi (OCHA/générées/dossier) est transmis. Si le type choisi est
      **Visite à domicile**, `/suivi` affiche une page « **indisponible / en cours
      de conception** » (pas encore de données VAD). Testé : VAD→message,
      district vide→sections vides + 226 contours, MAMPIKONY→rapport complet.
      **FAIT aussi — complétude géographique** : le rapport de district liste
      TOUTES les communes/fokontany du district depuis `zones` (référentiel
      complet), pas seulement ceux ayant des données — pour repérer les zones
      oubliées. Le serveur passe `zones_ref=zones.reference_district(...)` ; le
      moteur écrit `const ZONES_REF` ; le gabarit `template_tail.html` fusionne
      cette liste dans sa hiérarchie commune→fokontany (bloc **gardé par
      `typeof ZONES_REF`** → l'exe, qui n'émet pas ZONES_REF, reste identique).
      Testé : MAMPIKONY affiche 195 fokontany dont **11 sans données** (avant :
      cachés) ; district vide affiche toutes ses communes/fokontany.
      **FAIT aussi — dashboard MULTI-PAGES (MPA)** : la navigation n'est plus une
      SPA (bascule de `<div>` en JS) mais des **pages HTML distinctes servies au
      clic**. Routes `/vue/<section>[/commune/<code>|/fokontany/<code>]` (sections :
      general, agent, zone, gps, gpscap, qualite, historique, multi) ; `/suivi`
      redirige vers `/vue/general`. `serveur_app.rapport_vue()` filtre les données au
      périmètre (`source_db(district=/commune=/fkt=)` — colonne `den_menage.commune`
      = code 6 chiffres) et passe `section`/`scope`/`nav_tree` au moteur, qui injecte
      `const ACTIVE_SECTION/SCOPE/NAV_TREE/NAV_BASE`. Côté gabarit, `initMPA()`
      (gardé par `typeof ACTIVE_SECTION`) réécrit la barre latérale en **liens** :
      les **boutons de section = niveau district** (retour au district), le
      **sous-menu commune→fokontany = descente** au périmètre. L'exe (rien d'injecté)
      garde sa navigation SPA. **`initMPA()` retire aussi la barre d'actions du rapport**
      (`.topbar-actions` = boutons **CSV** et **Imprimer**) via
      `querySelector('.topbar-actions').remove()` — **web uniquement** (l'exe, hors
      `initMPA`, garde ses boutons). Les boutons restent dans le HTML source **partagé**,
      supprimés au chargement JS.
      **FAIT aussi — assets externes + hors-ligne** : le CSS et Chart.js sont sortis
      des gabarits dans `assets/` (`rapport.css`, `chart.umd.min.js`), appelés via
      `/assets` (pages plus légères, mises en cache ; **graphiques lisibles sans
      internet**). Le head porte les marqueurs `<!--RSU_STYLES-->`/`<!--RSU_CHARTJS-->`
      remplis par `rapport_core._tete_assets` : **références externes** si `assets_url`
      fourni (web), sinon **embarqués** (exe autonome). Images déplacées dans `images/`.
      (Leaflet + polices restent en CDN — carte non hors-ligne, hors périmètre.)
      **FAIT aussi — désagrégation complète + segments multiples (2026-08-16)** : (1) les
      sections `zone`/`qualité`/`historique` ont reçu leur conteneur `<…-drill>` (avant :
      absent → `buildMpaDrill` sortait sans afficher la descente commune→fokontany ;
      masqués en mode SPA pour l'exe) ; (2) `mpaFilter` prend le périmètre de **`SCOPE`**
      (serveur) et non de `MENAGES[0]` — un fokontany avec segments mais 0 ménage roster
      filtre quand même ; (3) **« Segments multiples »** (`renderMultiSection`) agrège
      district/commune/fokontany, détection par couple **(fokontany, code segment)**,
      colonne `Fokontany` aux niveaux commune/district (en-tête/titre dynamiques
      `multi-thead`/`multi-title`), affichage fokontany inchangé, exe inchangé (résultats
      au fokontany seul). Vérifié via la **vraie fonction exécutée en Node**.
      **FAIT aussi — allègement par AGRÉGATION serveur (en cours)** : au district/
      commune, les sections « résumé » n'embarquent plus les ménages bruts (24 Mo)
      mais un `const SUMMARY` d'agrégats calculés par `rapport_core.agrege(menages)`
      (piloté par `generer_rapport(alleger=True)` via `serveur_app.SECTIONS_ALLEGEES`,
      gardé par `typeof SUMMARY`). **Fait : `general`** (24 Mo→265 Ko, ~92× ; commune
      128 Ko). Chiffres **prouvés identiques** au calcul du gabarit : `test_agrege.py`
      compare `agrege()` (Python) à `test_agrege_oracle.js` (Node) — toutes sections
      IDENTIQUES sur MAMPIKONY (⚠️ `Math.round` JS ≠ `round()` Python → `_js_round`).
      ⚠️ **Resynchro exe (cf. §1)** : `template_head.html`, `template_tail.html`,
      `rapport_core.py` **+ `assets/`** à **recopier ENSEMBLE** vers le projet exe
      (blocs web inertes côté exe, mais copies à ne pas laisser diverger).
      **Reste à faire** : (a) câbler l'allègement des **autres sections** (gpscap,
      qualite, historique via `SUMMARY` ; zone, agent via `SEGMENTS_AGG` ; gps en
      points allégés ; export CSV en téléchargement serveur) — même patron prouvé ;
      (b) brancher un vrai **suivi Visite à domicile** quand les données VAD existeront.
      **FAIT aussi — ingestion par l'Expert survey** (`transcription.py`, route
      `/transcription`, réservée au rôle **Expert survey** affecté à un district) :
      pensée pour le **VPS** — l'Expert **téléverse** son dossier de `.dta` (le
      navigateur envoie les fichiers ; on ne lit pas le disque du client), le serveur
      les **valide dans un temporaire** (les 3 `.dta` exacts + la variable `district`
      de DEN_MENAGE == district de l'Expert, sinon **refus** sans rien écrire), les range
      sous **`config.UPLOAD_DIR/<code_district>/`** (district = affectation, donc imposé),
      montre un **aperçu** (dry-run) puis applique la **transcription incrémentale**
      (`maj_db`, upsert : ajoute/modifie, ne supprime rien) et journalise l'opération.
      Un Expert est redirigé vers `/transcription` après connexion.
- [~] **Étape 4 — Authentification (login)**. **FAIT** : `serveur_app.py` exige une
      connexion vérifiée **côté serveur**, avec **session par cookie** (`HttpOnly`,
      8 h) ; toutes les pages redirigent vers `/login` si non connecté. **FAIT aussi —
      comptes en base + mots de passe hachés** (`utilisateurs.py`) : table
      `utilisateurs` (login, nom_prenom, **`code_responsable` = FK vers la table de
      référence `responsabilite`**, mot de passe **PBKDF2-HMAC-SHA256 salé**, actif,
      cree_le, **district_affectation**) dans la **même base** ; `authentifier()`
      (comparaison à temps constant) pilote le `/login` et met l'utilisateur (avec son
      affectation, **libellé du rôle résolu par JOIN**) **en session**. **9 rôles**
      (table `responsabilite`, codes 1–9) : **Admin**, Coordonnateur Nationale,
      Coordonnateur régionale, Traitement, Superviseur Technique, Comités Techniques,
      Logistique District, Logistique Inter-Communale, Expert survey. Comptes **multiples**
      gérables par CLI (`python utilisateurs.py add/list/passwd/actif/del`) ; tables
      créées au démarrage (+ migrations : ancien `responsabilite` TEXT → `code_responsable`,
      comptes conservés), avec **compte d'amorçage RSU/RSU (rôle Admin) si vide**.
      **Affectation par FORME de responsabilité** (validée à l'ajout, `valider_affectation`) :
      *Admin / Coordonnateur Nationale* → **toute la zone** (rien) ;
      *Coordonnateur régionale / Comités Techniques* → **1 à 5 districts** (`MAX_DISTRICTS`) ;
      *Traitement / Logistique District / Expert survey* → **un district** (toutes ses
      communes) ; *Superviseur Technique / Logistique Inter-Communale* → **un district + de 1 à
      5 communes** (`MAX_COMMUNES_SUPERVISEUR`). **Clés étrangères** :
      `utilisateurs.district_affectation` → **`district(code_district)`** ; les communes
      (plusieurs) dans la **table de liaison** `superviseur_commune(login, code_commune→
      commune)` ; les districts d'un rôle multi-district dans la liaison
      `responsable_district(login, code_district→district)` (une liste ne peut pas être
      une FK dans une seule colonne). ⚠️ SQLite ne vérifie les FK
      que si `PRAGMA foreign_keys=ON` (off par défaut) — non activé pour ne pas gêner
      un rechargement de `zones` ; PostgreSQL (prod) les applique. L'intégrité est de
      toute façon garantie côté Python. Listes/contrôles via `zones` (`tous_districts`,
      `communes_district`, `commune_dans_district`).
      **FAIT aussi — espace Admin** (`admin.py` + `journal.py` ; routes `/admin*` dans
      `serveur_app`, réservées à `responsabilite=="Admin"`, sinon 403 ; un Admin est
      redirigé vers `/admin` après connexion) : **journal de connexion/utilisation**
      (nom, rôle, **durée**, statut — ouvert au login, clôturé au logout, rafraîchi à
      l'activité) + **tentatives échouées** ; **gestion des utilisateurs** (lister/
      activer/désactiver/supprimer/réinitialiser + **ajout par formulaire** avec
      cascade **Province→Région→District→Commune** (`zones.arbre_geo` +
      `communes_par_district` ; province/région non stockées, juste pour raccourcir la
      liste ; communes en multi-sélection) + **import Excel** openpyxl, mots de passe
      hachés à l'insertion) ; **tableau de bord**
      (comptes par rôle, connectés) ; **couverture des affectations** (districts/
      communes sans responsable) ; **modèle Excel + exports CSV**. Upload multipart
      parsé via le module `email` (stdlib, `cgi` étant retiré).
      **FAIT aussi — bandeau utilisateur (2026-08-14, web only)** : sur **chaque page**
      servie à un connecté, une **barre fixe en haut à droite** affiche
      **initiales + nom/prénom + rôle + bouton Déconnexion** (`/rsu/logout`).
      Centralisé : `serveur_app.bandeau_utilisateur(sess)` est injecté par `_html()`
      juste après `<body>` (regex `_RE_BODY`) **après `_prefixer`** — donc présent aussi
      sur le **rapport** (servi `prefixer=False`, lien déjà préfixé) ; **rien** si pas de
      session (login, erreurs). Les liens « Déconnexion » propres à chaque page ont été
      **retirés** (page_accueil, page_selection, `admin._entete`, `transcription._entete`)
      pour éviter les doublons.
      **FAIT (2026-08-14) — l'affectation est RESPECTÉE** : `serveur_app.perimetre(u)`
      renvoie `(districts, communes)` par rôle — `districts` est un **ENSEMBLE** de codes
      (ou None) : Admin/Coordonnateur Nationale → `(None, None)` = toute la zone ;
      Traitement/Logistique District → `({district}, None)` = district entier ;
      Coordonnateur régionale/Comités Techniques → `({1 à 5 districts}, None)` =
      **multi-district, consulté UN à la fois** (la sélection ne propose que ses districts,
      `_perimetre_vue` vérifie l'appartenance) ; Superviseur Technique/Logistique Inter-Communale
      → `({district}, {communes})` = ses communes ; Expert survey n'atteint pas le
      dashboard. `Handler._perimetre_vue()` (route `/vue`) **impose** un district du
      périmètre (écrase `sel["code_district"]` si hors périmètre) et **borne**
      commune/fokontany (`_zone_autorisee` cherche dans TOUS les districts autorisés,
      403 sinon).
      **Rôles « district + communes » — vue GLOBALE = AGRÉGAT de leurs communes** (et NON tout le district) :
      au niveau « district », `rapport_vue(communes_autorisees=)` charge la source
      `db_source.source_db(conn, communes=[...])` (nouveau filtre `commune IN (...)`),
      donc la Vue générale/qualité/… somme UNIQUEMENT ses communes (ex. 120+80 = 200 ;
      prouvé : 36960 = 24132+12828, < district 73560). **SEULE EXCEPTION : la Carte GPS**
      (`section == "gps"`, points ménage nominatifs) n'a PAS de vue globale → descente
      forcée sur une commune (sa 1re ; sous-menu latéral pour les autres). La barre
      latérale / carte / liste de réf. sont **filtrées à ses seules communes**
      (`nav_tree` restreint). Traitement / Logistique District / multi-district voient
      leur district (entier, gps compris) — un district à la fois pour le multi-district.
      La sélection borne le district (UI figée pour 1 district, **liste déroulante
      restreinte** pour multi-district, POST validé) pour tout rôle affecté. Routes
      héritées bornées : `/menu` (menu global) redirige les rôles affectés vers
      `/vue/general` ; `/fokontany/<code>` passe par `_zone_autorisee`. Prouvé hors-ligne
      ET en HTTP réel (Traitement/Superviseur/Logistique Inter-Communale/Coordonnateur
      régionale, districts 3305/3301/2101).
      ⚠️ Limite connue : un rôle « communes » qui clique un **bouton de section** revient au
      niveau « global » (agrégat de ses communes) — attendu ; mais s'il clique **GPS**
      il est ramené à sa **1re** commune, pas celle en cours (pas de changement de
      gabarit ; sous-menu latéral = navigation exacte commune/fokontany).
      **FAIT (2026-08-14) — pages non mises en cache** : `_html` envoie
      `Cache-Control: no-store, no-cache, must-revalidate` + `Pragma: no-cache` sur
      TOUTE page dynamique (données RSU nominatives hors du cache disque ; et surtout un
      navigateur ne peut plus resservir une copie cachée de `/choix` en contournant les
      gardes de rôle). Les statiques `/assets` gardent `max-age=86400`.
      **FAIT (2026-08-14) — Expert survey borné** : les routes de sélection/dashboard
      (`/choix`, `/suivi`, `/vue*`, `/menu`, `/fokontany/*`, POST `/suivi`) le
      redirigent vers `/transcription` (sa seule page).
      **Reste à faire avant mise en ligne** : **changer le compte d'amorçage**, éventuellement
      CSRF, politique de mots de passe. Tant que non déployé derrière HTTPS, **usage
      local uniquement**. **FAIT — expiration par inactivité** : `_session` invalide
      toute session sans requête depuis `INACTIVITE_MAX` (30 min) — l'utilisateur doit
      se reconnecter (le cookie garde une durée max absolue de 8 h). Toutes les routes
      (dont `/`) redirigent déjà vers `/login` sans session valide.
      **FAIT (2026-08-16) — coordonnées + modification** : comptes avec `telephone`/`cin`/
      `email` (facultatifs, validés) ; l'Admin peut **modifier** un compte via un
      formulaire pré-rempli (`/admin/utilisateurs/modifier`, `utilisateurs.modifier`).
      **FAIT (2026-08-16) — espace Traitement** (`equipes.py`, rôle Traitement) : à la
      connexion → `/traitement` (choix Tableau de bord OU **base Chef d'Équipe / Agent**
      remplie par 2 Excel) ; le dashboard reste via `/choix`. Tables `chef_equipe`/`agent`
      **liées au dénombrement** (FK `interview__diagnostics.responsible → agent`) : codes
      auto-créés (nom = code) et **nom affiché au lieu du code** dans le rapport.
- [ ] **Étape 5 — Passage à FastAPI + serveur robuste (uvicorn)**. Remplace le
      prototype `http.server`. La logique métier ne bouge pas.
- [ ] **Étape 6 — HTTPS**. Chiffrer les échanges.
- [ ] **Étape 7 — Hébergement**. **Décision à prendre** : serveur interne INSTAT
      (recommandé pour des données nominatives) vs cloud public. Déployer `RSU_Web/`.

## 7. Contraintes & principes

- **Confidentialité (priorité n°1)** : les données RSU sont **nominatives** (noms,
  adresses, GPS de dizaines de milliers de ménages). Mettre ça « en ligne » n'est
  pas anodin. Décisions structurantes : hébergement **interne INSTAT** de
  préférence, **login obligatoire**, **HTTPS**, et **suppression** des données
  temporaires après usage. Ne jamais exposer le prototype actuel sur internet.
- **Le rapport est la source unique du rendu** : toute évolution du rapport se fait
  dans `templeteHtml/` + `assets/` (style/JS) et, pour les agrégats, `rapport_core.py`
  (cf. §1, synchronisation groupée avec le projet exe).
- **Autonomie du dossier web** : `RSU_Web/` doit pouvoir être déployé seul. D'où les
  copies du moteur (§3) et les chemins configurables (`config.py`).
- **Dépendances** : le prototype actuel est en **bibliothèque standard** (comme
  l'exe). En production, deux ajouts assumés côté **serveur** (pas côté client) :
  `psycopg` (PostgreSQL) et, à l'étape 5, `fastapi`/`uvicorn`. C'est normal : un
  serveur n'a pas la contrainte « machine nue » qu'avait l'exe. **Node.js** n'est
  requis **que** pour lancer `test_agrege.py` (oracle JS) — outil de test, pas de prod.
- **Amélioration future** : factoriser le moteur partagé (`rapport_core`, `lire_dta`,
  `templeteHtml`, `assets/`) en **un seul emplacement** (un petit paquet Python importé
  par les deux projets) pour supprimer la duplication et le risque de divergence. Non
  fait pour l'instant, pour garder les deux dossiers simples et indépendants.

## 8. Ce qui reste dans le projet exe (`..\RSU_Rapport\`) — rappel

Pour mémoire, **ne pas** ramener ici : la GUI tkinter (`rapport_rsu_gui.py`), la
licence (`licence.py`), le build (`build_exe.py`, `RapportRSU.exe`, `dist/`,
`build/`), la base de préchargement (`base_prechargement.py`,
`affectation_agents.py`), les scripts d'extraction de limites, les `.do` Stata,
et les gros dossiers `DATA/`, `Cartographie/`, `LimitesFokontany/`. Ils appartiennent
à l'application de bureau. Le web ne réutilise que le **moteur de rapport**.

## 9. Bilan : réalisé, reste à faire, leçons apprises

### 9.1 Réalisé
- **Base de données** : lecture via `db_source` (SQLite local / PostgreSQL), preuve
  d'équivalence `.dta`↔base ; **mise à jour incrémentale** `maj_db` (upsert par clé,
  ne supprime rien) ; **clés étrangères** géo `den_menage`→`zones` (`FK_ZONES`).
- **Référentiel** `zones` (Excel→5 tables 3NF) + sélection Province/Région/District.
- **Nombre de ménages par commune** (2026-08-17) : colonne `commune."nombreMenage"`
  (projection RGPH-3 2025) remplie depuis `MENAGES_PAR_COMMUNE_2025.xlsx`
  (`zones.charger_menages` ; CLI `python zones.py menages`). Cet Excel est dérivé de
  `FKT_ampiasan_SS` croisé avec la projection population INSTAT par **appariement de
  noms** district+commune (points cardinaux malgache/français, agrégation des villes).
  ⚠️ Nom de colonne à casse mixte → **toujours entre guillemets** en SQL (PostgreSQL).
- **Indicateurs de couverture** (2026-08-17, web) : sur la page **Vue générale**
  district/commune, panneau `COUVERTURE` = **dénombrement réalisé vs projection 2025**
  (taux ; si <100 %, **jours restants** = restant/rythme, rythme = réalisé/jours
  travaillés) + **tableau par commune** au niveau district. `rapport_core.couverture`
  (prouvé sur district 4405), `const COUVERTURE` gardé par `typeof COUVERTURE`.
- **Export Excel du rapport** (2026-08-17, web) : bouton flottant « Exporter rapport »
  → route `/export/rapport.xlsx` → `export_rapport.generer_bytes`. 3 feuilles :
  **Rapport global** (couverture + qualité par commune/fokontany), **Dénombrement par
  agent-jour** (un tableau par chef d'équipe), **BaseDenParAgent** (table plate). Style :
  en-tête foncé sur clair, couleurs ARGB **opaques `FF`** (sinon invisible sous
  LibreOffice), bordures, source en italique. Vérifié en HTTP réel + rendu Excel.
- **Dashboard multi-pages (MPA)** : une page par section/périmètre (`/rsu/vue/...`),
  navigation = liens serveur ; **allègement par agrégats serveur** prouvés identiques
  au gabarit (`agrege` + `test_agrege.py`/oracle Node) — **Vue générale** faite (~92×).
- **Désagrégation commune/fokontany sur TOUTES les sections** (2026-08-16) : les
  sections `zone`, `qualité`, `historique` ont désormais leur conteneur `<…-drill>`
  (avant : absent -> `buildMpaDrill` sortait, pas de sous-menu). Le périmètre vient
  de **`SCOPE`** (serveur) et non de `MENAGES[0]` (`mpaFilter` corrigé) : un fokontany
  avec des segments mais **aucun ménage roster** filtre quand même correctement.
- **« Segments multiples » agrégé aux 3 niveaux** (2026-08-16) : `renderMultiSection`
  gère district/commune/fokontany. Détection PAR **(fokontany, code segment)** (un S01
  n'est unique qu'au sein d'un fokontany) ; au district/commune, tableau agrégé avec
  colonne **Fokontany** ; au fokontany, affichage inchangé. Web only (l'exe garde
  l'affichage au fokontany seul). Prouvé (fonction réelle en Node) : 4405 = 30 multiples
  / 18 fokontany, cohérent entre niveaux.
- **Assets externes** (CSS + Chart.js dans `assets/`, graphiques hors-ligne) ; images
  dans `images/`.
- **Authentification** : comptes en base, **mots de passe hachés** (PBKDF2), **9 rôles**
  (table de référence `responsabilite`, FK `code_responsable`, ordre/codes modifiables via
  `RESPONSABILITES_REF` + migration `_renumeroter_codes` par libellé) dont Admin ;
  **affectation** district(s) (FK + liaison `responsable_district` multi-district) +
  communes (liaison `superviseur_commune`), session cookie + **expiration par inactivité**
  (30 min).
- **Affectation RESPECTÉE** au routage (`perimetre` + `_perimetre_vue`/`_zone_autorisee`) :
  district imposé, commune/fokontany bornés (403) ; rôle « communes » → vue globale =
  **agrégat de ses communes** (sauf Carte GPS) ; multi-district consulté 1 à la fois.
- **Comptes : coordonnées** (2026-08-16) — `utilisateurs` a `telephone` / `cin` / `email`
  (facultatifs, validés par `valider_coordonnees` : CIN=12 chiffres, e-mail simple),
  migration auto par reconstruction ; affichés (colonne Contact liste + export CSV), saisis
  au formulaire d'ajout et à l'**import Excel**. **+ `numero_orange_float`** (Float) et
  **`sexe`** (« Masculin »/« Féminin ») ajoutés de même. **« Mon profil »** (`/rsu/profil`,
  tous rôles, lien bandeau) : chaque utilisateur édite en **libre-service** ses CIN,
  téléphone, N° Orange (Float), e-mail et sexe UNIQUEMENT (`modifier_profil`) ; le reste
  (login, nom, rôle, affectation) reste **réservé à l'Admin**. Voir section datée 2026-08-31.
- **Espace Admin** (`/rsu/admin`) : journal connexion/durée + tentatives +
  **transcriptions récentes** ; gestion utilisateurs en **3 pages** (liste avec colonne
  Contact + bouton **Modifier** ; ajout + import Excel ; **modification par formulaire
  PRÉ-REMPLI** — `utilisateurs.modifier`/`obtenir`, login non modifiable, mdp inchangé si
  vide, affectation courante pré-sélectionnée par JS `PRESEL`). Ordre du formulaire et du
  modèle Excel alignés (nom, rôle, tél, CIN, e-mail, login, mdp, affectation). Tableau de
  bord ; couverture ; exports CSV + modèle Excel.
- **Ingestion Expert survey** (`/rsu/transcription`) : **page de choix** Dénombrement /
  Visite à domicile (VAD = « pas encore disponible ») ; Dénombrement = téléversement du
  **DOSSIER complet** — **tous les fichiers ET sous-dossiers** (ex. `Questionnaire/`) rangés
  sous `UPLOAD_DIR/<district>/` en conservant l'arborescence (`_relpath_upload` +
  `_sous_dossier`), **validation** (3 `.dta` requis à la racine + district == affectation),
  aperçu (dry-run) puis transcription incrémentale ; **chaque
  issue journalisée** (`journal.consigner`) + **historique** affiché (Expert : les siens ;
  Admin : tous).
- **Espace Traitement** (`/rsu/traitement`, rôle Traitement) : **page de choix** Tableau de
  bord (`/choix`) OU **remplir la base Chef d'Équipe / Agent** (`/traitement/equipes`) =
  téléversement de **2 fichiers Excel** (CE puis Agents) → transcription **upsert**
  (`equipes.transcrire`, validation FK login_ce) ; modèles Excel fournis.
- **Journal de bord** (`/rsu/journal`, `journal.py`) — voir la section datée
  **2026-08-31** pour le détail : **ÉCRITURE** quotidienne par l'équipe technique (tous
  rôles sauf les 2 coordonnateurs et Admin ; plusieurs entrées/jour ; **bulle de rappel**
  si rien écrit le jour ; **entrées MODIFIABLES par leur auteur** — `cree_le` figé +
  `modifie_le` horodaté) ; **LECTURE** par les coordonnateurs National/Régional + Admin
  (bornée au périmètre ; **filtres** District cascade/restreint, Fonction, Axe/Zone
  dépendant — Superviseur/Logistique Inter-Communale au sein d'un district —, Nom, Date) ;
  **HISTORIQUE** personnel complet (`/journal/historique`) ; **SUIVI de complétude**
  (`/journal/suivi`, carte sur le menu Coordonnateur) = tableau membres × jours de mission
  (✓/✗) pour voir qui a écrit ou non, **par poste**, et **par district puis axe** pour
  Superviseur Technique / Logistique Inter-Communale (le National choisit d'abord son
  district par cascade ; colonnes = du début de mission `config.DATE_DEBUT_MISSION` à ce jour).
- **Consignes / instructions** (`consignes.py`, `/rsu/consignes[/nouvelle]`) — voir la
  section datée **2026-08-31** : les Coordonnateurs (National/Régional) envoient des
  consignes ciblées par **rôles** (ou tout le monde) et **districts** (ou tous ; Régional
  borné à ses districts) ; les destinataires les reçoivent via une **bulle** (haut-gauche)
  ouvrant `/consignes` (marquées lues). Accès : **carte** sur le menu Coordonnateur +
  **lien « Consignes »** au bandeau (tous). Tables `consigne` / `consigne_lecture`.
  Accès par le **bandeau** (tous) + **carte « Journal »** sur chaque page de choix.
  Table `journal_activite`.
- **Chefs d'Équipe / Agents liés au dénombrement** (`equipes.py` + `db_source.FK_AGENT`) :
  code agent `interview__diagnostics.responsible` = **FK** vers `agent(login_ae)`
  (déclarative ; migration `assurer_fk_diagnostics`) ; `synchroniser_agents` **auto-crée**
  dans `agent` tout code présent au dénombrement mais absent (**nom = le code**) ; le
  **rapport affiche le NOM** de l'agent au lieu du code quand il est renseigné
  (`noms_agents` → `generer_rapport(agents_noms=)`). Cache purgé après transcription
  (données ou noms modifiés). Le lien vers un **Chef** se fait via `agent.login_ce`.
- **Espace Logistique & Finances** (`/rsu/logistique`, rôles Logistique District /
  Inter-Communale — **PAS de dashboard**) : guide tiré du manuel FORMATIONLOG (accueil,
  tâches par étape, paiement Mvola, pièces, budget) ; outils transactionnels « en cours
  de conception ».
- **Ergonomie/rôles** : Traitement/Logistique ne choisissent pas leur zone (imposée) ;
  chaque rôle atterrit sur sa page (Admin→/admin, Expert→/transcription,
  Logistique→/logistique, autres→/choix) et y est **borné**.
- **Bandeau utilisateur** (web only) : barre fixe haut-droite (initiales + nom/prénom +
  rôle + **Déconnexion**) injectée par `_html()` sur **chaque page connectée, rapport
  compris** (`bandeau_utilisateur`) ; liens « Déconnexion » par page retirés (doublons).
- **Rapport web** : boutons **CSV** et **Imprimer** retirés côté web (`initMPA()` supprime
  `.topbar-actions`) ; l'exe garde les siens (gabarit partagé, retrait au chargement JS).
- **Préfixe d'URL `/rsu`** partout (de-préfixage en entrée, préfixage en sortie).

### 9.2 Reste à faire (par priorité)
0. ~~**FAIRE RESPECTER l'affectation**~~ **FAIT (2026-08-14)** : `perimetre(u)` +
   `Handler._perimetre_vue`/`_zone_autorisee` bornent `/vue`, `/menu`, `/fokontany` au
   périmètre du rôle. Traitement = son district entier. Superviseur = ses communes :
   la **vue globale agrège SES communes** (`source_db(communes=[...])`, ex. 120+80=200),
   **sauf la Carte GPS** qui descend sur une commune ; commune/fokontany hors périmètre
   → 403. District imposé à la sélection et au routage. Cf. §6 étape 4. Reste
   éventuellement : sur clic **GPS**, atterrir sur la commune en cours plutôt que la 1re
   (demande une retouche du gabarit).
1. **Changer le compte d'amorçage** RSU/RSU (sécurité).
2. **Câbler l'allègement des autres sections** (gpscap, qualite, historique via
   `SUMMARY` ; zone, agent via `SEGMENTS_AGG` ; gps en points allégés ; export CSV
   serveur) — patron déjà prouvé.
3. **PostgreSQL de production** effective (`RSU_DB_URL`) + **vrai schéma RSU** dans
   `db_source.FICHIERS`/décodage des labels (différent de la simulation). ⚠️ La **FK
   `interview__diagnostics.responsible → agent`** est déclarative (SQLite ne l'applique
   pas) : sur PostgreSQL (FK appliquées), **synchroniser `agent` AVANT de charger**
   `interview__diagnostics`, sinon l'insert violerait la contrainte.
4. **Vrai suivi Visite à domicile** (dashboard ET transcription VAD) quand les données
   VAD existeront (remplacer les pages « pas encore disponible »).
5. **Outils transactionnels logistiques** (exécution des paiements Mvola, téléversement
   des pièces scannées) quand une base finances/pièces existera — `logistique.py` fournit
   déjà le guide + la navigation ; remplacer les blocs « en cours de conception ».
6. **FastAPI/uvicorn** (étape 5), **HTTPS** (étape 6), **hébergement VPS/INSTAT**
   (étape 7). Tant que pas derrière HTTPS : **usage local uniquement**.
7. Durcissement : **CSRF**, politique de mots de passe, éventuellement cookie de
   session expirant à la fermeture du navigateur.
8. ⚠️ **Resynchro exe** : `template_head.html`, `template_tail.html`, `rapport_core.py`
   **+ `assets/`** à recopier ENSEMBLE vers `..\RSU_Rapport\` (blocs web inertes côté
   exe, mais copies à ne pas laisser diverger). Récent (2026-08-16) à inclure : conteneurs
   `<zone|qualite|historique-drill>` (masqués en SPA), `mpaFilter` basé sur `SCOPE`,
   `renderMultiSection` 3 niveaux (en-tête/titre dynamiques `multi-thead`/`multi-title`),
   `rapport_core.generer_rapport(agents_noms=)`. Récent (2026-08-17) à inclure aussi :
   panneau **couverture** (`#couverture-panel` dans `template_head.html`, `renderCouverture()`
   + `rapport_core.couverture`/`const COUVERTURE`) et **bouton flottant « Exporter rapport »**
   (`initMPA` remplace `.topbar-actions`) — gardés `typeof COUVERTURE`/`initMPA`, donc
   inertes côté exe. `export_rapport.py` est **web-only** (pas de copie exe).

### 9.3 Leçons apprises (pièges rencontrés — à ne pas réapprendre)
- **`Math.round` (JS) ≠ `round()` (Python)** : JS arrondit .5 vers le haut, Python fait
  un arrondi bancaire. Pour tout agrégat prouvé identique au gabarit : `rapport_core._js_round`.
- **SQLite ne vérifie PAS les clés étrangères** sauf `PRAGMA foreign_keys=ON` (off par
  défaut) : nos FK sont déclaratives en SQLite, **appliquées seulement en PostgreSQL**.
  L'activer couplerait les rechargements (drop `zones` bloqué). Intégrité garantie côté Python.
- **`SystemExit` dans une requête web = danger** (tue le thread) : les fonctions
  bibliothèque lèvent une exception métier (`maj_db.ErreurMaj`), `SystemExit` réservé au CLI.
- **Sécurité navigateur** : un serveur **ne peut pas lire le disque du client par un
  chemin**. Pour un VPS/déploiement distant, les fichiers de l'utilisateur doivent être
  **téléversés** (upload), pas référencés par chemin (le chemin ne marche que si serveur
  = machine du client).
- **`cgi` retiré des Python récents** : parser le multipart d'upload via le module
  **`email`** (stdlib). Pour distinguer PLUSIEURS champs fichier (ex. Excel CE + Excel
  Agents), lire `part.get_param("name", header="content-disposition")` (`_upload_par_champ`).
- **Téléverser un DOSSIER** (`<input webkitdirectory>`) : le navigateur envoie des chemins
  relatifs `racine/sous-dossier/fichier`. Pour conserver l'arborescence côté serveur, ne
  PAS `basename` (aplatit) : retirer le 1er segment (dossier racine) et garder le reste
  (`_relpath_upload`), en écartant `.`/`..`/`:` et en vérifiant que la cible reste sous le
  temporaire (`_sous_dossier`) — sinon traversée de dossier.
- **FK vers une table non alimentée à l'insert (PostgreSQL)** : déclarer une FK sur une
  colonne existante (ex. `responsible → agent`) casse l'ETL PG si les valeurs n'existent
  pas encore dans la table cible. Sur SQLite (FK déclaratives) c'est sans effet ;
  l'intégrité est assurée en Python par une **synchronisation** (`synchroniser_agents` crée
  les lignes manquantes, nom = code). En PG il faudra synchroniser AVANT de charger.
- **Tester sur une COPIE, pas la vraie base** : un `UPDATE ... LIMIT 1` de test sur
  `rsu_local.sqlite` a touché une ligne réelle — les tables `chef_equipe`/`agent` étaient
  déjà remplies (235 chefs, 905 agents nommés). Vérifier le contenu AVANT toute écriture de
  test, et préférer une base jetable.
- **Une valeur multiple ne peut pas être une FK dans une colonne** (1 à 5 communes) →
  **table de liaison** (`superviseur_commune`), pas une chaîne « c1,c2 ».
- **Emoji dans `print()` plante la console Windows (cp1252)** : garder la sortie
  serveur/CLI en ASCII.
- **openpyxl : couleurs en ARGB alpha OPAQUE `FF`** (`FFFFFFFF`, `FF2563EB`…). Un code
  6 chiffres est stocké avec alpha `00` (transparent) : Excel l'ignore, mais LibreOffice
  le respecte → fond « transparent » (blanc) + police blanche = **texte invisible**
  (blanc sur blanc). En plus, préférer **texte foncé sur fond clair** pour les en-têtes
  (lisible même si le remplissage n'est pas appliqué). Piège vécu sur l'export Excel.
- **Colonne SQL à casse mixte = piège PostgreSQL** : `commune."nombreMenage"` doit être
  citée **exactement** (guillemets) partout ; sans guillemets, PG replie en minuscules et
  ne trouve pas la colonne. (SQLite est insensible à la casse → le bug ne se voit qu'en PG.)
- **Réutiliser le moteur pour l'export** : `export_rapport` reconstruit les ménages via
  `rapport_core._charger_diagnostics(...,agents_noms=None)` (garde les **codes** agent pour
  joindre aux chefs) + `_charger_segments` + `_construire_menages` — mêmes jointures
  prouvées que le rapport, pas de SQL dupliqué. Code commune = `fktcode[:6]`.
- **Un bouton dans le coin haut-droite est masqué par le bandeau utilisateur** (fixe,
  z-index très élevé) : placer les actions du rapport ailleurs (ex. bouton **flottant
  bas-droite** pour « Exporter rapport »).
- **Session persistante ≠ absence d'auth** : `/` semblait « ouvert » à cause d'un
  **cookie de session** encore valide, pas d'un trou (toutes les routes redirigent vers
  `/login` sans session). Vérifier en **navigation privée**.
- **Préfixe d'URL** : dé-préfixer en **entrée** (routage inchangé) et préfixer en
  **sortie** (`_redirige` + `_prefixer` sur href/action/src) ; le rapport est préfixé
  **à la source** (`assets_url`, `nav_base`) et servi **sans** re-traitement (volumineux +
  éviter le double préfixe).
- **Un seul gabarit, deux comportements** (web MPA vs exe SPA) via des blocs gardés par
  `typeof ACTIVE_SECTION` / `SUMMARY` / `ZONES_REF` / `SCOPE` : l'exe n'injecte rien → inchangé.
- **Filtrer sur le PÉRIMÈTRE serveur (`SCOPE`), pas sur les données** : `mpaFilter`
  dérivait le fokontany courant de `MENAGES[0]` → si un fokontany a des segments mais
  0 ménage roster (`MENAGES` vide, fréquent en cours de dénombrement), le filtre était
  indéfini et « Segments multiples » n'affichait plus rien. Corrigé en lisant
  `SCOPE.code`/`SCOPE.commune` (autoritaire, toujours présent en MPA).
- **Un sous-menu de désagrégation par section nécessite un conteneur `<…-drill>`** dans
  le gabarit : `buildMpaDrill` fait `getElementById(ACTIVE_SECTION+'-drill')` et sort si
  absent. 3 sections (`zone`, `qualité`, `historique`) n'en avaient pas → aucune descente
  commune/fokontany. Ajoutés (et masqués en mode SPA pour garder l'exe identique).
- **Un code de segment n'est unique qu'AU SEIN d'un fokontany** : agréger « segments
  multiples » en commune/district se fait par couple **(fokontany, code)**, jamais par code
  brut (sinon on additionne les S01 de fokontany différents).
- **Vérifier une fonction JS SANS navigateur** : le navigateur intégré bloque `localhost` ;
  pour prouver un rendu, exécuter la **vraie fonction** dans **Node** avec les `const`
  réels extraits du rapport (SEGMENTS_DEN/SCOPE/NAV_TREE) + un faux `document.getElementById`
  qui capture `innerHTML`/`textContent`. Plus fiable qu'une réimplémentation Python.
- **Tests = preuve** : reproduire le style `simuler_db` (identité octet/champ à champ,
  ici via un **oracle Node**) pour faire confiance à un refactor lourd.
- **Données concrètes** : `den_menage.commune` = code 6 chiffres (filtrage direct) ;
  `fokontany` et `num_fkt` sont le **même** code 8 chiffres ; `district` peut être `None`
  (lignes incomplètes, à ignorer aux comparaisons).
- **Tests locaux** : toujours **libérer le port 8000** avant de relancer le serveur —
  une instance résiduelle renvoie de vieux 404 trompeurs (et un nouveau serveur qui ne
  se lie pas laisse la VIEILLE instance répondre → tests trompeurs, ex. login qui échoue
  car l'ancienne base n'a pas le compte de test).
- **Cache navigateur contourne les gardes de rôle** : sans `Cache-Control: no-store`, le
  navigateur ressert une page (`/choix`…) SANS repasser par le serveur → le contrôle
  d'accès n'est jamais atteint. `_html` envoie `no-store` sur toute page dynamique.
- **Renuméroter une clé primaire référencée** : identifier chaque ligne par une clé
  STABLE (le **libellé** du rôle), remapper en **une passe SQL `CASE`** (pas de
  double-application), et détecter « déjà migré » via l'état lu AVANT le re-seed
  (`_renumeroter_codes`). Les comparaisons métier passent par le libellé → codes = pur
  détail interne.
- **Déduire plutôt que ressaisir** : un rôle « district + communes » ne saisit que ses
  communes ; le district est **déduit** (`zones.district_de_commune`, toutes du même
  district sinon refus) → formulaire plus simple (1 cascade + 5 listes de communes).
- **Un rôle sans dashboard = espace dédié + garde** : comme l'Expert (`/transcription`),
  les Logistiques ont `/logistique` ; un garde par groupe de rôles redirige hors zone.

---

## Déploiement en ligne (journal 2026-08-28)

Mise en ligne de l'application sur le serveur `rse.instat.mg` (Ubuntu 24, Apache),
accessible sous **`https://rse.instat.mg/rsu-web/`**, à côté des autres applications
déjà hébergées. **État : EN LIGNE** ✅ — service systemd `rsu-web` *active* + *enabled*
(redémarrage auto + au boot), Apache proxifie `/rsu-web/` sur `http` et `https`
(HTTP 200 vérifié). Accessible depuis n'importe quel appareil avec un navigateur, sans
rien installer côté visiteur.

### Ce que nous avons fait

- **Code sur GitHub** : dépôt `https://github.com/RANDRIANALISOA/RSU_Web.git` (public).
  `.gitignore` créé AVANT le commit final pour exclure `venv/`, `__pycache__/`, `*.sqlite`,
  `*.db`, `*.dta`, `uploads/`, `instance/`, `*.log`, `.env`. Historique réinitialisé
  (suppression de `.git` + re-init) car un premier commit contenait déjà la base de 102 Mo.
- **Clone sur le serveur** dans `/home/rse/rsu-web` (et non `/var/www`, pour éviter sudo
  sur les fichiers).
- **Environnement** : venv Python 3.12, `pip install openpyxl` (SEULE dépendance externe
  du projet ; le reste est la bibliothèque standard). `gdown` installé pour le transfert.
- **Base de données** : `rsu_local.sqlite` (103 Mo, 22 tables ; `den_menage` 4961,
  `segment_roster` 303691, `interview__diagnostics` 4961 ; comptes réels dont l'admin
  `randrianalisoa`) transférée depuis le PC via **Google Drive** puis téléchargée avec
  `gdown` — le SSH (port 22) est bloqué depuis Internet et le PC n'est pas sur le LAN.
- **Test local OK** : `RSU_PREFIXE=/rsu-web python serveur_app.py` → `127.0.0.1:8000`,
  `/rsu-web/login` répond **HTTP 200**.
- **Reverse-proxy Apache** : bloc `ProxyPass /rsu-web/ http://127.0.0.1:8000/rsu-web/`
  (préfixe CONSERVÉ) ajouté dans les DEUX vhosts (`rse.conf` :80 et
  `rse.instat.mg.conf` :443), **avant** l'attrape-tout Survey Solutions. Sauvegardes dans
  `deploy/backups/`.
- **Fichiers de déploiement** créés : `deploy/rsu-web.service` (systemd) et
  `deploy/installer.sh` (installe le service + teste la syntaxe Apache AVANT reload).

Installation finale faite le 2026-08-28 : `sudo bash deploy/installer.sh` (lancé par
l'utilisateur sur le serveur) → service systemd installé, app démarrée, Apache rechargé.
Piège résolu : une instance de test tenait le port 8000 → conflit avec le service systemd ;
après arrêt de l'instance de test, systemd a repris le port et l'app est stable.

### Ce qui reste à faire

- **Vrai certificat HTTPS** : remplacer le certificat auto-signé `snakeoil` (avertissement
  « non sécurisé ») par Let's Encrypt (`certbot`) ou Cloudflare. *(nécessite sudo)*
- **Sauvegarder les modifications de code sur GitHub** : les changements faits directement
  sur le serveur (voir « Mises à jour ultérieures ») ne sont PAS encore poussés → `git
  commit` + `git push` depuis `/home/rse/rsu-web`, puis `git pull` sur le PC pour éviter la
  divergence.
- **(Optionnel) PostgreSQL** : PG 16 est déjà installé sur l'hôte (`127.0.0.1:5432`, distinct
  de celui de Survey Solutions en Docker). Basculer via `RSU_DB_URL` + `pip install
  "psycopg[binary]"` si besoin de robustesse/concurrence.
- **Rendre `PORT` configurable** par variable d'environnement (codé en dur à 8000,
  `serveur_app.py:54`).
- **Sécurité** : changer le mot de passe sudo de `rse` (il a été exposé en conversation).

### Mises à jour ultérieures (2026-08-28)

- **Suppression du choix de « limites » sur la page de sélection** (demande utilisateur) :
  retiré le `<fieldset>` « Limites administratives » (OCHA / générer / dossier), le JS
  associé (`zoneDossier`/`champChemin`, qui aurait planté et cassé les listes déroulantes),
  la ligne « Limites » du récapitulatif (`page_suivi`) et la variable `libelle_limites`.
  Étapes renumérotées (`n_sui` : le « Type de suivi » remonte d'un cran ; `n_lim` supprimé).
  Côté serveur AUCUN changement nécessaire : `champs.get("limites", ["ocha"])` retombe déjà
  sur **OCHA** en l'absence du champ, et les **limites corrigées des 4 districts** restent
  injectées automatiquement (`limites_db.contours_pour`, indépendant du choix).
- **Robustesse `SO_REUSEADDR`** : `serveur_app.py:main()` fixe désormais
  `ThreadingTCPServer.allow_reuse_address = True` avant le `bind` → redémarrage immédiat
  même si le port 8000 est en `TIME_WAIT` (fini le « Address already in use » au restart).
- **Redémarrer sans sudo** : `kill <pid de serveur_app.py>` suffit — systemd (`Restart=always`)
  relance le service avec le nouveau code. (Le process tourne en `rse`, donc pas besoin de sudo
  pour le tuer ; `systemctl restart`, lui, exigerait sudo.)

### Mises à jour ultérieures (2026-08-29)

- **Chaque utilisateur peut changer SON mot de passe** (self-service, tous les rôles) :
  nouvelle page `/motdepasse` (GET formulaire + POST `_traiter_motdepasse` dans
  `serveur_app.py`), accessible depuis un lien **« Mot de passe »** ajouté au **bandeau
  utilisateur** (présent sur chaque page connectée). La route GET est placée **AVANT** les
  gardes de rôle (Expert→/transcription, Logistique→/logistique) pour rester ouverte à tous.
  Le handler prend le **login en session** (jamais du formulaire), **vérifie l'ancien mot de
  passe** (`utilisateurs.authentifier`), applique une **politique minimale** (`MDP_MIN=6`,
  confirmation identique, différent de l'actuel), puis `utilisateurs.changer_mot_de_passe`.
  La session en cours reste valide ; le nouveau mot de passe est demandé à la prochaine
  connexion. Réutilise l'existant (`authentifier` + `changer_mot_de_passe`), pas de nouvelle
  fonction dans `utilisateurs.py`. Testé sur une **copie** de la base (jamais la vraie).
  Nécessite un redémarrage du service pour être servi (voir « Redémarrer sans sudo »).

- **Coordonnateur Nationale — 3ᵉ choix « Équipe technique »** sur la page de sélection
  (en plus de Dénombrement / Visite à domicile). Réservé à ce rôle (radio `value="equipe"`
  injecté dans `page_selection` seulement si `responsabilite=="Coordonnateur Nationale"` ;
  validé côté serveur dans `_traiter_selection`, `suivis_ok` étendu à `equipe` pour ce seul
  rôle). En le choisissant pour un district, `/suivi` affiche `page_equipe_technique` = la
  fiche de **l'encadrement (comptes) affecté au district** — PAS les agents de terrain —
  groupé par rôle : **Coordonnateur régionale, Superviseur Technique, Traitement, Expert
  survey** (constante `utilisateurs.ROLES_EQUIPE_TECHNIQUE`). Données via
  `utilisateurs.equipe_technique_district(conn, code)` : filtre `lister()` sur
  `district_affectation==code` OU `code ∈ responsable_district` (multi-district). Chaque
  carte montre nom + les **contacts Téléphone / N° Orange (Float) / E-mail** (le **CIN
  n'y figure PAS** — donnée d'identité, retirée le 2026-08-31), communes (pour un
  Superviseur). Testé
  (lecture seule) : district 1101 → Coord régional + 2 Traitement + 1 Expert survey.
  Redémarrage requis pour être servi.

- **Export Excel du dénombrement — 4ᵉ feuille « segment_multiple »** (`export_rapport.py`) :
  rapport « Segments multiples » identique à la page du tableau de bord. Un code de
  segment est MULTIPLE quand il se répète plus d'une fois dans un même fokontany, compté
  sur les lignes DEN_MENAGE (`rapport_core._construire_segments_den` → SEGMENTS_DEN), clé
  = (fokontany, code). Colonnes : Fokontany / Segment / Nombre de segments dénombrés /
  Agents concernés (noms via `equipes.agents_et_chefs`, sinon code), triées par libellé
  fokontany puis nombre décroissant. `_menages_scope` renommé `_donnees_scope` (renvoie
  désormais `(menages, segments_den)`). Respecte le périmètre (district entier OU communes
  d'un superviseur). Vérifié : district 4405 MAMPIKONY → **30 segments multiples / 18
  fokontany** (= chiffre de contrôle du gabarit). Redémarrage requis pour être servi.

- **Manuel d'utilisation intégré, ADAPTÉ AU RÔLE** (`manuel.py`, `manuel_ui.py`,
  `manuel_roles.py`) : lien **« Manuel »** ajouté au bandeau (présent sur chaque page,
  tous rôles), route `/manuel` (GET) placée AVANT les gardes de rôle comme `/motdepasse`.
  `manuel.page_manuel(role)` assemble une page avec sommaire + sections. Contenu SPÉCIFIQUE
  par poste (`manuel_roles.sections_role`) : Traitement (dashboard + base CE/Agents avec
  **maquettes Excel** `login_ce`/`login_ae`, + préchargement avec modes), Expert survey
  (dossier des 3 `.dta` à téléverser, **arborescence** illustrée, transcription
  incrémentale), Superviseur Technique (dashboard borné à ses communes), Coordonnateur
  Nationale (sélection libre + Équipe technique), Coordonnateur régionale / Comités
  Techniques (multi-district), Logistique (espace guide), Admin (gestion comptes) ; plus
  des sections communes (connexion, bandeau, mot de passe, sécurité, aide). Illustrations
  en **HTML/CSS** (schémas de flux, maquettes tableur, arborescence, maquette dashboard) —
  pas de captures réelles. Séparation : `manuel_ui.py` = briques de rendu + CSS + illus ;
  `manuel_roles.py` = contenu par rôle ; `manuel.py` = sections communes + assemblage
  (import de `manuel_ui`, pas d'import circulaire). Testé : rendu OK pour les 9 rôles +
  cas inconnu. Redémarrage requis pour être servi.
  - **Version imprimable / PDF** : bouton « Imprimer / Enregistrer en PDF »
    (`window.print()`) + feuille de style `@media print` (masque sommaire/boutons,
    `break-inside:avoid` par section). Pas de génération PDF serveur — impression
    navigateur (aucune dépendance ajoutée).
  - **Vraies captures d'écran (facultatives)** : `manuel_ui.capture(nom, legende,
    remplacement)` embarque en data-URI un fichier `images/manuel/<nom>` s'il existe,
    sinon garde l'illustration (ou rien). Emplacements câblés : login, bandeau,
    motdepasse, selection, traitement_accueil/equipes, prechargement,
    transcription_accueil/denombrement, logistique_accueil (voir
    `images/manuel/README.txt`). ⚠️ CONFIDENTIALITÉ : PAS de capture du tableau de
    bord / exports / journal Admin dans le manuel partagé (données nominatives) — ces
    écrans restent des maquettes schématiques. Aucun navigateur headless dispo dans
    l'environnement (chromium/wkhtml absents) + le navigateur intégré bloque localhost
    -> captures fournies par l'utilisateur, déposées dans `images/manuel/`.

### Mises à jour ultérieures (2026-08-30)

- **Fiche « Équipe technique » — nouvel ordre + Superviseurs par axe** (`serveur_app.
  page_equipe_technique`, `utilisateurs.ROLES_EQUIPE_TECHNIQUE`) : l'ordre d'affichage est
  désormais **Coordonnateur régionale → Traitement → Expert survey → Superviseur
  Technique**. Les **Superviseurs Techniques** sont présentés **par axe de supervision**
  (zone d'affectation = leur jeu de communes) : chaque axe est un sous-titre
  **« Axe de supervision : Commune 1, Commune 2… »** (communes affichées **par nom** via
  `zones.libelle_commune`, résolues dans `equipe_technique_district` -> champ
  `communes_noms`), suivi **en retrait** de la liste des superviseurs de cette zone. Les
  superviseurs partageant exactement le même jeu de communes sont regroupés dans le même
  axe. La ligne « Communes » (codes bruts) de la carte-personne est retirée (l'info est
  portée, en clair, par le sous-titre d'axe).

- **Accès « Équipe technique » ÉTENDU aux rôles bornés à un district** (Traitement,
  Superviseur Technique, Expert survey) — **chacun ne voit que SON district** : nouvelle
  route **`/equipe`** (GET, `Handler._equipe_get`), placée **AVANT les gardes de rôle**
  (comme `/motdepasse`/`/manuel`) pour ne pas être détournée (Expert -> /transcription).
  Le district est résolu par **`perimetre(u)`** (source de vérité de l'accès, jamais d'une
  saisie) ; réservée à `_ROLES_EQUIPE_DISTRICT`, sinon redirection vers `accueil_role`. Le
  Coordonnateur Nationale continue de passer par la **sélection** (district libre). Points
  d'entrée : **carte « Équipe technique »** sur le menu **Traitement**
  (`equipes.page_choix_traitement`) et sur le menu **Expert survey**
  (`transcription.page_choix_transcription`), toutes deux -> `/equipe` ; pour le
  **Superviseur Technique** (pas de menu-cartes, il passe par la sélection), le **radio
  « Équipe technique »** de `page_selection` lui est ouvert (comme au Coord. Nationale) et
  `suivis_ok` étendu à `equipe` -> chemin `/suivi` existant (son district est **imposé**
  par la validation zone de `_traiter_selection`). `page_equipe_technique` prend
  `retour_href`/`retour_label` pour un bouton de retour adapté (mon espace vs sélection).
  Testé en HTTP réel **sur une COPIE de la base** (jamais la vraie ; ⚠️ le service systemd
  `rsu-web` tient le port 8000 -> test sur port 8011, cf. leçon « libérer le port ») :
  Traitement/Expert (district 1101) et Superviseur (1106) obtiennent **200** + la fiche de
  LEUR district ; Coord. Nationale sur `/equipe` -> **303** vers `/choix`. Redémarrage du
  service requis pour être servi.

- **MENU d'opération pour Coordonnateurs + Superviseur Technique** (`serveur_app.
  page_menu_operation`, `Handler._menu_operation_get`, `_ROLES_MENU_OPERATION` =
  Coordonnateur Nationale / Coordonnateur régionale / Superviseur Technique) : après
  connexion, `accueil_role` mène **chaque rôle sur SA route dédiée** (constante
  `_MENU_CHEMINS` : **`/coordonat`**, **`/coordoreg`**, **`/suptech`**), sur le modèle de
  `/traitement`. Ces routes (placées AVANT les gardes de rôle, chacune vérifiant que le rôle
  courant correspond, sinon redirection vers son propre accueil) affichent un **menu de
  cartes** : **Tableau de bord — Dénombrement**, **Tableau de bord — Visite à domicile
  (VAD)** et **Équipe technique**. La page reprend
  **EXACTEMENT la charte de la page Traitement** — `admin._STYLE` (fond clair `#f0f2f7`),
  barre sombre `.bar`, cartes `equipes._CSS_CHOIX` — **sans image de fond** (l'ancienne
  maquette à `url(/img/accueil)` + `.voile` a été retirée). `/choix` **redirige** ces rôles
  vers leur route dédiée. L'aiguillage se fait par **`<menu>?op=den|vad|equipe`** :
  - **Superviseur Technique** (district FIXE) va **directement** au résultat — `op=den`/`vad`
    -> prépare `sess["selection"]` (son district, suivi=op) et redirige vers **`/suivi`**
    (den -> vue générale ; vad -> page « pas encore disponible ») ; `op=equipe` -> `/equipe`.
  - Le choix **VAD est CONSERVÉ** (comme demandé) : faute de données VAD, il mène à la page
    « pas encore disponible » (`page_vad_indisponible`) ; le vrai tableau de bord VAD sera
    branché plus tard. Carte marquée « Bientôt disponible » mais cliquable.
  - **Coordonnateurs** (district à choisir) -> `page_selection(op=…)` : les vignettes
    « type de suivi » sont remplacées par un **champ caché `suivi=op`** + rappel de
    l'opération + lien **« ← Menu »** ; ils choisissent le district (cascade complète pour
    le National, liste restreinte pour le Régional) puis POST `/suivi` mène au tableau de
    bord ou à la fiche équipe. `suivis_ok` inclut `equipe` pour **tous** les rôles à menu
    (Coord. régionale compris) ; sur erreur de validation, `page_selection` reçoit
    `op=op_form` pour **conserver l'opération** (le champ caché) dans le formulaire.
    Le district reste **borné par `perimetre(u)`** à la validation du POST (district hors
    affectation -> 400). Les rôles multi-district **hors** menu (ex. Comités Techniques)
    gardent la **sélection classique** (radios den/vad), `page_selection(op=None)`.
  Testé HTTP réel **sur une COPIE** (port 8011) : login -> `/suptech` / `/coordonat` /
  `/coordoreg` (menu, **0 réf. image de fond**, fond `#f0f2f7`, barre `.bar` + cartes `.ca`
  comme Traitement, **3 cartes** dont VAD) ; Superviseur `?op=den`->`/suivi`->vue générale,
  `?op=vad`->`/suivi`->« pas encore disponible », `?op=equipe`->`/equipe`,
  `/choix`->`/suptech` ; Coord. Nationale `?op=equipe`+district 1101 -> fiche équipe,
  `?op=den`+4405 -> dashboard 200, `?op=vad`+1101 -> « pas encore disponible », accès croisé
  `/suptech` -> redirigé vers `/coordonat` ; Coord. régionale `?op=equipe` -> sélection,
  district **4405 hors périmètre -> 400** avec op conservée. Redémarrage du service requis pour être servi. *(Comités Techniques laissé
  volontairement sur l'ancien flux — non demandé ; à basculer en l'ajoutant à
  `_ROLES_MENU_OPERATION` + `_MENU_CHEMINS`.)*

### Mises à jour ultérieures (2026-08-31)

- **Nouvelle coordonnée « N° Orange (Float) »** sur les comptes (`utilisateurs`) :
  colonne **`numero_orange_float`** (TEXT, **facultative**, NULL possible), destinée
  au numéro Orange Money servant au « Float » de l'équipe technique. Ajoutée au **schéma
  cible** (`_COLS_UTILISATEURS`/`_COLS_CIBLE`) → migration SQLite **automatique** au
  démarrage (`_migrer`/`_reconstruire` : reconstruit la table, **comptes conservés**).
  **Validée comme un téléphone** (8-15 chiffres) : `valider_coordonnees` prend un 4ᵉ
  paramètre et renvoie désormais un **4-uplet** `(tel, cin, email, orange)` (helper
  `_valider_tel` factorisé) ; `ajouter`/`modifier` ont un paramètre
  `numero_orange_float`. Câblé partout où passaient les coordonnées : `lister()`
  (SELECT + dict), formulaires Admin **ajout** + **modification** (champ « N° Orange
  (Float) »), **import Excel** + **modèle** (colonne `numero_orange_float`, facultative),
  **export CSV** + affichage **Contact** (`_contact_html`), POST admin
  (`serveur_app._admin_action_utilisateur`), CLI `add` (`_saisir_coordonnees`), et la
  **fiche Équipe technique** (`page_equipe_technique` affiche le n°). Testé sur une
  **COPIE** de la base (jamais la vraie) : migration (56 comptes conservés, colonne
  présente), aller-retour ajout/modif/vidage, rejet d'un numéro invalide, et cycle
  **modèle→import Excel** (colonne lue au bon rang malgré le décalage). **Redémarrage
  du service requis** pour être servi (`kill` du process → systemd relance ;
  cf. « Redémarrer sans sudo »).

- **JOURNAL DE BORD (activités quotidiennes)** — nouvelle route unique **`/journal`**
  (GET + POST, `journal.py` + `serveur_app.py`), placée **AVANT les gardes de rôle**
  (comme `/motdepasse`/`/manuel`/`/equipe`) pour rester ouverte à tous les rôles
  concernés. Deux usages selon le rôle :
  - **ÉCRITURE** (`_ROLES_JOURNAL_ECRITURE` = toute l'équipe technique SAUF les deux
    coordonnateurs et l'Admin : Comités Techniques, Traitement, Expert survey,
    Superviseur Technique, Logistique District, Logistique Inter-Communale) : page
    « Mon journal de bord » (`page_journal_ecrire`) — **Nom/Prénom, Fonction, Axe/Zone
    pré-remplis** (jamais saisis : la zone vient de `perimetre(u)` via `_journal_zone`
    — communes = « Axe de supervision : … », sinon « District(s) : … »), champ **Date**
    (défaut = aujourd'hui, jamais dans le futur) + **textarea** des activités. POST =
    `journal.ecrire_activite`. **Plusieurs entrées/jour autorisées**. La page liste
    « Mes dernières entrées » (`journal.mes_activites`) avec un lien **« Voir tout mon
    journal → »** vers **`/journal/historique`** (route rôles d'écriture, placée AVANT
    les gardes ; un lecteur y est renvoyé vers `/journal`) : page dédiée qui affiche
    **TOUTES** ses entrées (`mes_activites(limite=1000000)`) avec le **total** et un
    **filtre par date**. Testé (COPIE) : total exact, filtre date, redirection lecteur.
  - **MODIFICATION d'une entrée** (comme les consignes) : chaque entrée listée porte un
    bouton **✏️ Modifier** → **`/journal/modifier?id=`** (GET formulaire pré-rempli +
    POST), **propriétaire UNIQUEMENT** (`journal.obtenir_activite`/`modifier_activite`
    vérifient le login ; sinon 303/refus). On peut corriger la **date du jour** et le
    **texte**. **`cree_le` reste FIGÉ** (date initiale) et une colonne **`modifie_le`**
    (migration auto `_migrer_activite`) reçoit l'horodatage de la dernière modification ;
    la liste affiche « écrit le … » et « modifié le … ». Testé (COPIE) : migration
    (colonne ajoutée), pré-remplissage, `cree_le` inchangé + `modifie_le` renseigné,
    garde propriétaire (autre rédacteur → 303, POST non appliqué).
  - **SUIVI de complétude** (`/journal/suivi`, `_ROLES_JOURNAL_LECTURE`, **carte sur
    le menu Coordonnateur**) : tableau **membres × dates** (✓ a écrit / ✗ non) pour voir,
    chaque jour passé, qui a rempli son rapport. **Groupé par POSTE**, et **par DISTRICT
    puis AXE** (communes) pour **Superviseur Technique** et **Logistique Inter-Communale**
    (`_ROLES_DISTRICT_COMMUNES`) — `groupes` = `[(poste, mode, data)]` avec mode `flat`
    (data=[membres]) ou `district` (data=[(district, [(axe,[membres])])]). Membres suivis
    = comptes des rôles d'ÉCRITURE (`_ROLES_JOURNAL_ECRITURE`) **dans le périmètre**.
    **Choix du district (2026-08-31)** : le National / Admin (zone entière) **doit d'abord
    CHOISIR un district** via une **cascade Province→Région→District** (`page_journal_suivi_
    choix`, JS `ARBRE_GEO`) — le suivi s'affiche ensuite pour CE district (lien « Changer
    de district ») ; le **Régional** voit **directement ses districts** (groupés par district
    pour les rôles à axe). Colonnes de dates = **TOUS les jours de la mission**
    (`journal.plage_dates(config.DATE_DEBUT_MISSION)` = du **début de mission**, défaut
    **2026-08-27**, réglable par `RSU_DATE_DEBUT_MISSION`, **à aujourd'hui**) — y compris
    les jours SANS écriture, pour voir les manques (✗) ; `journal.dates_ecrites(logins)`
    donne les jours écrits par membre, total `n/N`. `page_journal_suivi` :
    défilement horizontal, 1re colonne (nom) figée. Testé (COPIE) : National sans district
    → page de choix (pas de tableau) ; National `?district=1101` → suivi de ce district,
    Sup Tech groupé par district+axe, autre district exclu ; Régional → 2 districts groupés
    (AMBOHIDRATRIMO + AVARADRANO) ; ✓/✗ et totaux exacts ; périmètre respecté.
  - **LECTURE** (`_ROLES_JOURNAL_LECTURE` = Coordonnateur Nationale, Coordonnateur
    régionale, Admin) : page « Journaux des équipes » (`page_journal_lecture`) —
    liste **bornée au périmètre** (`journal.activites(districts=perimetre(u)[0])` :
    **None = tout** pour National/Admin ; **set = ses districts** pour le Régional,
    filtré par recoupement de `code_district`) + **filtre par date**.
  - **Table** `journal_activite(id, login, nom_prenom, fonction, zone, code_district,
    date_jour, journal, cree_le)` créée au démarrage (`journal.creer_tables`). `id` =
    jeton Python (portable, pas d'auto-incrément) ; `code_district` = codes du
    périmètre séparés par virgules (pour le filtrage de lecture du Régional).
  - **Bulle de RAPPEL** (`bulle_rappel_journal`, injectée par `_html` avec le bandeau
    sur **chaque page connectée SAUF `/journal`**) : s'affiche pour un rôle d'écriture
    qui **n'a rien écrit aujourd'hui** (`journal.a_ecrit_le`), bas-gauche (haut-droite
    = bandeau, bas-droite = bouton « Exporter rapport »). Disparaît dès la 1re entrée
    du jour. Résultat **caché dans la session** (`_journal_jour`/`_journal_ck`/
    `_journal_bulle`, re-vérif ≤ 1×/120 s) pour limiter les requêtes.
  - **Accès** : (1) lien **« Journal »** (écriture) / **« Journaux »** (lecture) au
    **bandeau utilisateur** (présent sur chaque page, tous rôles concernés) ; (2)
    **carte « Journal »** (📓) ajoutée à **chaque page de choix**, au même niveau que
    les autres choix — `page_menu_operation` (Coordonnateurs + Superviseur : libellé
    adaptatif « Journaux des équipes » en lecture / « Mon journal de bord » en
    écriture), `equipes.page_choix_traitement`, `transcription.page_choix_transcription`
    et `logistique.page_accueil` (« Mon journal de bord »). *Comités Techniques* passe
    par la sélection à radios (pas de cartes) → accès via le bandeau uniquement.
    Testé en HTTP réel **sur une COPIE** de la base (port 8011 ; le service systemd
    tient le 8000) : écriture Traitement (zone district, POST + succès + rappel qui
    disparaît), Superviseur (zone = axe de communes, refus si vide), lecture National
    (tout) / Régional (ses districts seulement — district hors périmètre non visible) ;
    carte présente et bien libellée sur les 6 pages de choix. **Redémarrage du service
    requis** pour être servi.
  - **FILTRES de LECTURE (Coordonnateurs National + Régional)** : la page « Journaux
    des équipes » a **5 filtres** combinables (GET, `journal.activites` étendu +
    `journal.options_lecture`) : **District**, **Fonction/Poste**, **Axe/Zone de
    supervision** (dépendant, voir ci-dessous), **Nom** (sous-chaîne insensible à la
    casse) et **Date**. Le filtre **District** est une **cascade
    Province→Région→District** pour le National/Admin (sans restriction —
    `_filtre_district_html` + JS de cascade réutilisant `ARBRE_GEO` ; **pré-remplie
    côté serveur** via `_geo_reverse` quand un district est déjà choisi, le JS ne
    gérant que les changements) ; pour le Coordonnateur régional c'est une **liste
    déroulante restreinte à SES districts** (un district hors périmètre passé en
    paramètre est ignoré). **Fonction** est un `<select>` peuplé des **valeurs
    distinctes présentes dans le périmètre** (`options_lecture` — donc, tant que
    seuls des Superviseurs ont écrit, la liste ne contient qu'eux : c'est voulu, on
    n'offre que des filtres qui donnent des résultats). Le filtre **Axe/Zone de
    supervision** est **DÉPENDANT** : il ne concerne que les rôles « district +
    communes » (`_ROLES_DISTRICT_COMMUNES` = **Superviseur Technique**, **Logistique
    Inter-Communale**) et n'a de sens qu'au sein d'UN district → il n'est **actif que
    si un District ET une de ces deux fonctions sont choisis** ; ses options sont
    alors les **axes (zones) de cette fonction DANS ce district** (calculées à la
    volée dans `_journal_get`, périmètre respecté ; libellé = zone sans le préfixe
    « Axe de supervision : »). Sinon le `<select>` est **désactivé** avec un libellé
    explicatif, et un texte d'astuce rappelle la marche à suivre. Le filtre district
    recoupe le `code_district` (codes séparés par virgules) du journal. Testé sur
    COPIE (port 8011) : National — district/fonction/nom/date + combinaisons +
    pré-sélection cascade ; **axe** : désactivé sans district/fonction, peuplé et
    borné au district choisi pour Superviseur ET Logistique Inter-Communale (les axes
    d'un autre district n'apparaissent pas), désactivé pour une fonction hors
    « district + communes » (ex. Traitement) ; Régional — dropdown restreint à
    1101/1106, district hors périmètre ignoré, résultats toujours bornés à ses
    districts.

- **CONSIGNES / INSTRUCTIONS des Coordonnateurs** (`consignes.py`, routes
  `/consignes` + `/consignes/nouvelle`) : un Coordonnateur (National ou régional)
  **rédige une consigne** et choisit **qui la reçoit** (rôles) et **pour quels
  districts** ; les destinataires la reçoivent via une **bulle d'info** ouvrable.
  - **Émetteurs** (`_ROLES_CONSIGNE_ENVOI`) : Coordonnateur Nationale **et** régionale.
    Le National peut viser **tous les districts** (`districts_cibles='TOUS'`) ; le
    Régional est **borné à SES districts** (`perimetre`) — sa sélection est filtrée et
    « Tous les districts » = **tous les SIENS** (jamais 'TOUS'), un district hors
    périmètre soumis est écarté.
  - **Ciblage RÔLES** : cases à cocher (« **Tout le monde** » = `roles_cibles='TOUS'`,
    sinon une sélection de `_ROLES_CONSIGNE_CIBLES` = tous les rôles **sauf Admin**).
  - **Ciblage DISTRICTS** : `<select multiple>` (optgroups par région, réutilisant
    `ARBRE_GEO`, borné au périmètre de l'émetteur) + case « Tous les districts ».
  - **Réception** (`/consignes`, **tous rôles**) : un utilisateur est destinataire si
    `role ∈ roles_cibles` (ou TOUS) **ET** son/ses district(s) (`perimetre(u)[0]`)
    **recoupe(nt)** `districts_cibles` (ou TOUS) — `consignes._concerne`. La page liste
    les consignes reçues et les **marque lues** à l'ouverture. **3 filtres d'AFFICHAGE**
    (GET, appliqués dans `_consignes_get`, sans changer le marquage-lu qui reste global) :
    **Poste de l'émetteur** (`<select>` des deux Coordonnateurs, `_ROLES_CONSIGNE_ENVOI`),
    **Nom de l'émetteur** (sous-chaîne insensible à la casse sur `auteur_nom`) et **Date**
    d'émission (`cree_le[:10]`). Testé sur COPIE (port 8011) : chaque filtre + combinaisons.
  - **Bulle** (`bulle_consignes`, injectée par `_html` comme le bandeau, **en haut à
    gauche** — le bandeau prend le haut-droite, la bulle journal le bas-gauche) : «📣 N
    consigne(s) à lire » si non-lues > 0 ; disparaît dès l'ouverture de `/consignes`.
    Comptage en cache session, **throttle court (30 s)** car le déclencheur est
    **externe** (l'émetteur), pas l'utilisateur lui-même.
  - **Tables** : `consigne(id, auteur_login/nom/role, roles_cibles, districts_cibles,
    titre, message, cree_le)` + `consigne_lecture(consigne_id, login, lu_le)`. Créées
    au démarrage (`consignes.creer_tables` dans `preparer`).
  - **Confirmation AVANT envoi/modification** : le formulaire (`#cj-form`) demande une
    **confirmation JS** récapitulant les rôles et districts visés avant de poster (le
    verbe s'adapte selon `EST_EDIT` : « Envoyer » / « Enregistrer les modifications »).
  - **Suppression / rappel** : chaque consigne envoyée porte un bouton **🗑 Supprimer**
    (POST `/consignes/supprimer`, confirmation JS) → `consignes.supprimer(id,
    auteur_login)` retire la consigne ET ses lectures, **uniquement si le demandeur en
    est l'AUTEUR** (un coordonnateur ne peut retirer que SES consignes). Une fois
    supprimée, les destinataires ne la voient plus (la bulle se recalcule).
  - **Modification** : chaque consigne envoyée porte un bouton **✏️ Modifier** →
    **GET `/consignes/modifier?id=`** ouvre le **même formulaire pré-rempli** (titre,
    message, cases rôles cochées / « Tout le monde », districts sélectionnés / « Tous »),
    **POST `/consignes/modifier`** applique via `consignes.modifier(id, auteur_login, …)`
    — **auteur uniquement** (sinon redirection, aucune écriture). La modification
    **réinitialise les accusés de lecture** (`consigne_lecture` vidé pour cet id) : les
    destinataires (y compris de NOUVEAUX si la cible change) **revoient la version à
    jour** et la bulle se ré-affiche. Lecture du formulaire factorisée (`_consignes_cibles`)
    et partagée avec l'envoi ; sur erreur de validation, le formulaire d'édition est
    **ré-affiché sans perte de saisie** (`_edition_depuis_form`). Testé (COPIE) :
    pré-remplissage, retargetage (l'ancien destinataire perd la consigne, le nouveau la
    reçoit), reset des lectures, garde auteur (autre coordonnateur redirigé, aucune modif),
    ré-affichage sur message vide.
  - **Accès** : **carte « Consignes & instructions »** sur le menu des Coordonnateurs
    (`page_menu_operation`, → `/consignes/nouvelle`) + **lien « Consignes »** au
    **bandeau** (tous rôles, → `/consignes` reçues). Routes placées AVANT les gardes de
    rôle. Testé en HTTP réel **sur une COPIE** (port 8011) : ciblage rôle+district,
    « Tout le monde »/« Tous districts », périmètre du Régional (district hors périmètre
    → écarté/erreur), bulle qui apparaît pour le bon destinataire et disparaît après
    lecture, validations (message/rôle/district vides), 403 pour un non-coordonnateur ;
    **confirmation JS présente**, **suppression** par l'auteur (bulle du destinataire
    qui disparaît) et **refus** de suppression par un AUTRE coordonnateur (garde auteur).
    **Redémarrage du service requis** pour être servi (crée les tables + sert les routes).

- **« MON PROFIL » — libre-service (TOUS les rôles)** + **nouvelle variable `sexe`**
  sur `utilisateurs`. Route **`/profil`** (GET + POST, placée AVANT les gardes de rôle
  comme `/motdepasse`), lien **« Profil »** au bandeau (tous rôles).
  - **Champs modifiables par l'utilisateur lui-même** : **CIN, téléphone, N° Orange
    (Float), e-mail, sexe** — et RIEN d'autre. `utilisateurs.modifier_profil(login,
    …)` ne met à jour QUE ces 5 colonnes ; le **login est pris de la SESSION** (jamais
    du formulaire). Vérifié : un POST injectant `responsabilite`/`login`/`nom_prenom`/
    `district_affectation` est **ignoré** (rôle/nom/affectation intacts). Le reste
    (login, nom, rôle, zone/axe d'affectation) est affiché **en lecture seule** et
    reste **réservé à l'Admin**.
  - **`sexe`** : colonne TEXT **facultative** (NULL possible) ajoutée au schéma cible
    (`_COLS_UTILISATEURS`/`_COLS_CIBLE`) → **migration SQLite automatique** au démarrage
    (`_migrer`/`_reconstruire`, **comptes conservés** — testé : 56 comptes préservés,
    colonne ajoutée). Valeurs canoniques **« Masculin »/« Féminin »** (`utilisateurs.
    SEXES`), saisies M/H/F/homme/femme… normalisées par `valider_sexe`. Câblé partout
    où passaient les coordonnées : `ajouter`/`modifier`/`lister`, **formulaires Admin**
    ajout + modification (`<select>` sexe), **import Excel** + **modèle** (colonne
    `sexe`, facultative), **export CSV**, affichage **Contact** (`_contact_html`),
    et POST admin (`_admin_action_utilisateur`).
  - Testé en HTTP réel **sur une COPIE** (port 8011) : `/profil` (champs éditables +
    contexte lecture seule, enregistrement + succès, rejet CIN/e-mail/sexe invalides),
    injection de champs non autorisés ignorée, Admin ajout/modif avec sexe, colonne
    Contact + en-tête CSV `sexe`. **Redémarrage du service requis** (applique la
    migration `sexe` + sert `/profil`).

### Leçons à retenir

- **Git refuse > 100 Mo** : ne jamais versionner base/données ; poser le `.gitignore` AVANT
  le premier commit. Si un gros fichier est déjà committé, l'ajouter au `.gitignore` NE
  suffit pas (le blob reste dans l'historique et le push est rejeté) → réécrire l'historique
  (ici : supprimer `.git` et repartir propre, car rien n'était encore poussé).
- **Structure ≠ contenu** : le code sait auto-créer les tables + un compte d'amorçage, mais
  PAS les données. `preparer()` exige une base déjà remplie OU les `.dta` sources ; sinon
  l'app **refuse de démarrer** (`no such table: den_menage`). Une base « qui se crée à
  l'usage » a quand même besoin de ses graines.
- **Le serveur ne peut pas aller chercher un fichier sur le PC** : SSH 22 bloqué depuis
  Internet, PC hors du LAN `192.168.88.0/24`. Il faut un relais (cloud). `gdown` gère la
  confirmation Drive des gros fichiers ; sa nouvelle syntaxe prend l'**ID en argument
  positionnel** (plus de `--id` ni `--fuzzy`).
- **Architecture du serveur** : c'est **Apache** qui sert 80/443 (nginx est en échec car
  Apache occupe déjà les ports — ses configs sont dormantes). Chaque app tourne sur un port
  interne `127.0.0.1` (5000 `traitement-rsu`, 5001 `rsu-vague2`, 5002 `rlf-rsu-v2`,
  **8000 `rsu-web`**, 8080 Survey Solutions). Ajouter une app = un bloc `ProxyPass` **avant**
  l'attrape-tout `/`.
- **Les vhosts Apache appartiennent à `rse`** → éditables sans sudo ; seul `systemctl reload
  apache2` (et l'install du service) exige sudo.
- **Cette app est du `http.server` natif** (pas Flask/gunicorn) → on lance le script
  directement sous systemd, pas via gunicorn. Elle gère nativement un préfixe d'URL via
  `RSU_PREFIXE` ; le proxy doit **conserver** le préfixe (`/rsu-web/` → `:8000/rsu-web/`).
- **Toujours libérer le port 8000** avant un test (voir aussi la leçon « Tests locaux »
  plus haut) — une instance résiduelle fausse les résultats.

---

## Affichage adaptatif / responsive (journal 2026-09-02)

**Problème** : l'app était dessinée **100 % en pixels fixes** → « bien chez moi, mais
trop grand/petit ailleurs » selon la **résolution** et la **mise à l'échelle Windows**
(125/150 %) de chaque poste. Corrigé en **deux mécanismes complémentaires** qui
cohabitent via un **marqueur CSS** (pas de double mise à l'échelle).

### Phase 1 — normalisation globale (pansement, `serveur_app._STYLE_RESPONSIVE`)
- Injectée par `_html()` juste **avant `</head>`** sur **TOUTE** page (rapport et login
  compris ; après les styles de la page, `charset` reste en tête). `_RE_HEAD_FIN`.
- Un petit script ajuste l'**échelle** (`document.documentElement.style.zoom`) selon la
  largeur d'écran, **uniquement vers le bas** : écrans **≥ `_UI_LARGEUR_REF`** (défaut
  **1200**, réglable par env `RSU_UI_LARGEUR_REF`) **inchangés** (le poste de dev reste
  identique) ; plus petits réduits jusqu'à `_UI_ZOOM_MIN` (0.78). Garde-fous
  `img{max-width:100%}` + `text-size-adjust:100%`.

### Phase 2 — refonte fluide (px → rem + base fluide)
- Chaque feuille convertie porte sur `:root` : **`--rsu-fluid:1`** (le script Phase 1 lit
  cette variable et **NE zoome PAS** cette page → pas de double échelle) et
  **`font-size:clamp(12px, 0.22vw + 10.2px, 14px)`** (plafonnée à **14px** = la taille
  d'origine, jamais plus grande ; réduite jusqu'à ~12px sur petits écrans — RÉGLAGE de la
  base = ces 3 nombres, à changer PARTOUT à l'identique, cf. plus bas). Toutes les tailles
  sont en **rem** → suivent cette base. Bordures fines (1-2px), ombres, letter-spacing et
  **conditions de media queries** restent en **px** ; points de rupture ajoutés
  (rapport.css : 1024/860/480px).
- **Converti (fluide)** : `assets/rapport.css` (dashboard), `admin._STYLE` (admin + menus
  Coordonnateur/Superviseur + Traitement/Transcription/Logistique qui l'incluent),
  `equipes._CSS_CHOIX`, `transcription._CSS_CHOIX`, `logistique._CSS`,
  `serveur_app._STYLE_JOURNAL`/`_STYLE_SUIVI`/`_STYLE_CONSIGNE_EXTRA`, `manuel_ui.CSS`, et
  les styles inline de `page_login`/`page_selection`/`page_equipe_technique`/
  `page_motdepasse`. Les fragments (`_CSS_CHOIX`, `_CSS`, `_STYLE_SUIVI`,
  `_STYLE_CONSIGNE_EXTRA`) sont **convertis sans `:root`** : ils héritent du `:root` de
  `admin._STYLE`/`_STYLE_JOURNAL` avec lesquels ils sont toujours servis.
- **Pages f-string** (accolades CSS échappées `{{ }}`) : `page_accueil`, `page_suivi`
  (récap), `page_vad_indisponible` — converties AUSSI (le `:root` injecté y est écrit à
  accolades DOUBLÉES `:root{{...}}` ; `ast.parse` détecte toute erreur d'accolade).
  → **toutes les pages de l'app sont fluides** ; le zoom Phase 1 ne sert plus que de
  filet (il no-op sur toute page portant `--rsu-fluid`).

### Révision 2026-09-02 (retour utilisateur)
Base fluide d'abord réglée trop haut (≤17px) → **police trop grande** ; abaissée à
`clamp(12px, 0.22vw + 10.2px, 14px)`. Dashboard **cassé sur smartphone** (barre latérale
fixe → contenu coupé) → sous **860px**, abandon du gabarit plein écran (`height:100vh` +
`overflow:hidden`) au profit d'un **défilement naturel** : barre latérale compacte en haut
(`max-height:42vh`, défilante), contenu dessous, KPI 1 colonne <480px. ⚠️ `rapport.css`
étant mis en cache 24h (`/assets` `max-age=86400`), tester avec **Ctrl+F5** après un
redéploiement.

### Menus repliables (2026-09-02)
- **Bandeau** (haut-droite) : bouton **☰** (`.rsu-b-toggle`, 1er enfant de `#rsu-bandeau`)
  qui bascule la classe `.rsu-col` (CSS : cache `.rsu-b-txt` + tous les `a`, ne laisse que
  bouton + initiales). Script inline dans `bandeau_utilisateur`, état mémorisé
  (`localStorage rsu_bandeau_col`), **replié par défaut ≤700px**.
- **Barre latérale des sections** (dashboard) : bouton **☰** (`.rsu-nav-toggle`) injecté
  dans `.topbar` par le script global (`_STYLE_RESPONSIVE`, fonction `nav()`), **web
  uniquement** (n'agit que si `.sidebar`+`.topbar` existent → l'exe, sans ce script, garde
  sa barre). Bascule `body.rsu-nav-col` → `.sidebar{display:none}` (CSS dans rapport.css).
  État mémorisé (`localStorage rsu_nav_col`), **replié par défaut ≤860px**.

### ⚠️ Resync .exe
`assets/rapport.css` est partagé avec `..\RSU_Rapport\` (cf. §1) → **recopier** la version
fluide. Le `--rsu-fluid` et la base `clamp` y sont bénins (l'exe n'injecte pas le script
Phase 1 ; à écran fixe, la base ≈ 16px).

### Vérifié en HTTP réel (jamais la vraie base)
Instance de test **port 8011** contre une **COPIE** de `rsu_local.sqlite`
(`RSU_SQLITE=<copie>`, `serveur_app.PORT=8011`), toutes les pages → **200** avec marqueur
`--rsu-fluid` présent. Le rendu **visuel** (échelle sur petits écrans) est à valider sur
de vrais postes / en rétrécissant la fenêtre.

### Pièges rencontrés
- **`%` de formatage Python vs `100%` du CSS** : une chaîne CSS contenant `100%` passée à
  `"...%d..." % x` lève `unsupported format character` → **concaténer**, pas `%`-formater.
- **`pkill -f "lancer_test.py"`** tue le **shell courant** (sa ligne de commande contient
  la chaîne) → exit 144 ; gérer le PID via `$!` à la place.
- **`sleep` de premier plan bloqué** dans l'environnement d'assistance → attendre le
  serveur via `curl --retry --retry-connrefused --retry-delay`, pas `sleep`.
- **Convertisseur px→rem** : gérer les décimaux **sans zéro initial** (`.5px`) avec
  `(\d*\.?\d+)px` (sinon `.5px` → `.0.3125rem`, CSS cassé) ; **protéger** les préludes de
  media queries (`@media ... {`) pour garder les points de rupture en px.
