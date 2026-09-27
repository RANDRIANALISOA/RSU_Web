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
> triplet fokontany×code×**agent** — définition révisée le 2026-09-17). Chaque rôle atterrit sur SA page : **Admin** →
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
> feuille **Rapport global** (couverture + **structure des ménages** par commune/fokontany),
> feuille **Dénombrement par agent-jour** (un tableau par chef d'équipe), feuille
> **BaseDenParAgent** (table plate agent×fokontany×date), feuille **segment_multiple**,
> feuille **Écart par agent** (synthèse : un agent = une ligne) et feuille
> **Écart déclaration-serveur** (le même écart, détaillé par date et par chef d'équipe).
> **ÉCART DÉCLARATION ↔ SERVEUR, PAR AGENT — LES DEUX PHASES (maj 2026-09-21)** : la
> page **« Par agent »** affiche désormais ce que chaque agent **DÉCLARE** avoir fait
> face à ce qui est **ARRIVÉ AU SERVEUR** — 3 KPI, un graphique des 12 plus grands
> écarts, un tableau (un agent = une ligne). **VAD** : page `/vad/agents` + feuille
> **« Écart par agent »** du classeur VAD. **Dénombrement** : page `/vue/agent` au
> niveau district (clic sur une ligne = détail par date) + feuilles **« Écart par
> agent »** et **« Écart déclaration-serveur »**. Un seul calcul pour les quatre
> sorties : `rapport_core.ecart_declaration`. La saisie des déclarations est devenue
> **consciente de la phase** (agents et dates proposés par le modèle Excel).
> Voir la section datée 2026-09-21.
> **TABLEAU DE BORD (maj 2026-09-17)** : tout ce qui touchait au **carnet e-Fokontany**
> (KPI « Avec carnet », deux graphiques « Possession de carnet », colonnes « % Avec carnet »,
> colonne « Carnet » de l'export CSV) a été **RETIRÉ** — la question a disparu du
> questionnaire de septembre 2026 et n'affichait plus que des « n/d ». À la place, une carte
> KPI **« Taille moyenne des ménages »** (sous-titre : écart-type + nombre de personnes) et,
> sur la page Qualité, moyenne + écart-type sous l'histogramme des tailles.
> 📌 **Un BILAN DE SESSION daté du 2026-09-17/18 clôt ce fichier** : ce qui a été fait
> (12 chantiers), les **leçons apprises**, et **ce qui reste à faire** — dont un point
> à trancher d'urgence sur des données VAD chargées en production par erreur.
> **CARTE GPS VAD + JOURNAUX D'INGESTION (maj 2026-09-20)** : la **carte GPS de la
> VAD** reprend le fonctionnement de celle du dénombrement — fonds satellite (Bing,
> Google, Esri), points colorés par **agent** (≤ 12 agents) ou par **date** au-delà,
> filtres par agent et par date, bulle détaillée, contours **rouge = niveau affiché /
> bleu = ses enfants** — et gagne une **descente District → Commune → Fokontany** en
> sous-menu de la barre latérale (flèches de dépliage), bornée au périmètre du rôle.
> Les contours sont servis **à part** (`/vad/contours.json`, allégés par
> Douglas-Peucker : 2,3 Mo → 187 Ko) et le **bouton ☰** du dénombrement masque
> désormais aussi la barre des sections du VAD (préférence partagée). Côté
> **journaux d'ingestion** : les opérations VAD ressortaient en ROUGE (statut
> « Succès » ≠ « Réussi » attendu par l'affichage) ; la couleur se décide maintenant
> sur `journal.reussi()`, les deux phases ont **chacune leur journal** (Admin et
> Expert survey), le district est **nommé** et les refus de téléversement VAD sont
> enfin consignés. Voir la section datée 2026-09-20.
> **EXPERT SURVEY (maj 2026-09-18)** : il **ingère les deux phases** (dénombrement et
> VAD) et voit **les deux tableaux de bord**, bornés à son district ; la garde qui
> l'enfermait dans `/transcription` a été retirée.
> **VISITE À DOMICILE — EN SERVICE (maj 2026-09-18)** : la VAD a désormais ses tables
> (`vad_menage`, `vad_membre`, `vad_diagnostics` — module `vad_db.py`), son **ingestion
> par l'Expert survey** (`/transcription/vad` : téléversement du dossier d'export
> RSUe, aperçu, puis transcription UPSERT) et son **tableau de bord complet**
> (`/vad/<section>`, modules `vad_core.py` + `vad_web.py`) en 8 sections — Vue globale,
> Démographie (pyramide des âges, masculinité, dépendance), Habitation, Biens & actifs,
> Eau & assainissement, Carte GPS, Listing d'erreurs, Par agent — ouvert aux
> **Coordonnateurs National et Régional, au Traitement et au Superviseur Technique**,
> chacun borné à son périmètre. Voir la section datée pour CE QUI RESTE À FAIRE.
> **« VISITE À DOMICILE » À CÔTÉ DU DÉNOMBREMENT — ACTIVÉ (maj 2026-09-19)** : sur la
> **fenêtre de sélection** (choix du district + type de suivi), la vignette **Visite à
> domicile** ouvre désormais le **VRAI tableau de bord VAD** (`/vad/general`) **borné au
> district choisi**, et non plus l'écran « pas encore disponible » (`page_vad_indisponible`
> **supprimée**). Ouvert à **TOUS les rôles qui atteignent cette fenêtre** : `_ROLES_VAD`
> gagne les **Comités Techniques** et l'**Admin** (correctif 2026-09-19, cf. ci-dessous)
> — donc tout le monde sauf les deux **Responsables Logistiques**, seuls à ne pas avoir
> de tableau de bord (ils sont renvoyés vers `/logistique` avant même `/choix`).
> **COEFFICIENT DE VARIATION (maj 2026-09-17)** : la taille des ménages est désormais
> décrite par **moyenne, écart-type ET coefficient de variation** (σ ÷ moyenne, en %) —
> dans le KPI de la vue générale, sur la page Qualité, et en colonne des tableaux 2 et 3 de
> la feuille « Rapport global » de l'export Excel.
> **MANUELS (maj 2026-09-17)** : les guides par poste (`/manuel`) sont à jour de tout ce
> qui précède, et gagnent une section **Journal de bord** pour TOUS les postes (écriture ou
> lecture selon le rôle) ainsi qu'une section **Déclaration des agents** pour le Superviseur
> Technique. Les groupes de rôles du journal vivent désormais dans `utilisateurs.py`
> (`ROLES_JOURNAL_ECRITURE` / `ROLES_JOURNAL_LECTURE` / `ROLES_DECLARATION`), partagés par
> `serveur_app` et `manuel_roles`.
> **JOURNAL — PIÈCES JOINTES (maj 2026-09-17)** : sur `/journal/modifier`, on peut
> désormais **retirer** des photos/fichiers (une case « Retirer » par pièce, avec vignette)
> et en **ajouter** d'autres, le tout appliqué en **une seule validation** avec le texte.
> Auparavant un `<form>` imbriqué faisait supprimer par le navigateur le formulaire de
> suppression ET sortait les champs d'ajout du formulaire principal : ni l'un ni l'autre ne
> fonctionnait depuis un navigateur.
> **PRÉCHARGEMENT (maj 2026-09-17)** : sur `/traitement/prechargement`, la règle
> d'acceptation d'un préchargement déjà généré est désormais **explicite** — un classeur est
> valide dès qu'**une** de ses feuilles porte la colonne `interview_keyden` ; `e_fokontany`
> peut être vide ou absente, un fichier réduit à `nouveau` est juste. Les fichiers
> réellement inexploitables sont refusés **en disant lequel et pourquoi**.
> **DÉCLARATIONS DES AGENTS (maj 2026-09-17)** : nouvelle table `declaration_agent`
> (`code_agent` → FK `agent`, `date`, `type_operation` ∈ {DEN, VAD}, `nombre`) et nouveau
> module `declarations.py`. Le **Superviseur Technique** a, dans son menu (`/suptech`), un
> choix « Déclaration des nombres de ménages dénombrés / interviewés par les Agents »
> (`/declaration`) → sous-choix **Dénombrement** ou **VAD** → téléversement d'un **classeur
> Excel** bâti sur le **modèle** fourni (colonne 1 = code agent, colonnes 2..n = dates) →
> transcription (UPSERT) vers la base. L'export Excel confronte ensuite, par chef d'équipe
> et par date, ce que l'agent **déclare** et ce qui **arrive au serveur**.
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
│                          Televersement|Transcription, suffixe « VAD » pour la
│                          visite a domicile ; statut = Reussi|Echec ;
│                          quand, detail, bilan). consigner() ecrit succes ET echecs ;
│                          transcriptions(login=, phase=DEN|VAD) filtre pour l'Expert
│                          et separe les DEUX JOURNAUX (maj 2026-09-20) ; reussi(statut)
│                          decide de la pastille (tout ce qui n'est pas « Echec »),
│                          noms_districts() nomme le district (« FARATSIHO (1406) »). Migration
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
├── consignes.py        <- CONSIGNES / INSTRUCTIONS des Coordonnateurs + ADMIN.   [FONCTIONNEL]
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
│                          couverture des affectations, INGESTIONS RECENTES en DEUX
│                          tableaux separes — Denombrement et Visite a domicile
│                          (_table_transcriptions : date+heure, personne, district
│                          NOMME, operation, statut Reussi/Echec, detail), modele Excel +
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
├── declarations.py     <- DECLARATIONS DES AGENTS (role Superviseur Tech.). [FONCTIONNEL]
│                          Table declaration_agent(code_agent -> FK agent(login_ae),
│                          date AAAAMMJJ, type_operation 'DEN'|'VAD', nombre ;
│                          PK (code_agent, date, type_operation)). Ce que l'agent DIT
│                          avoir dénombré / interviewé, a comparer a ce qui ARRIVE AU
│                          SERVEUR (feuille « Ecart declaration-serveur » de l'export).
│                          modele_xlsx(conn, type, districts, communes) : classeur a
│                          remplir, DEUX feuilles — « declaration » (colonne 1 = code
│                          agent PRE-REMPLI depuis les donnees du perimetre, colonnes
│                          2..n = dates observees, sinon 14 jours a partir
│                          d'aujourd'hui) et « mode d'emploi ». AUCUN renseignement
│                          sur l'agent dans le classeur (nom, CE) : ils vivent dans
│                          `agent`/`chef_equipe`, atteints par la FK code_agent ->
│                          agent(login_ae) — une seule source de verite.
│                          recap_agents(conn, type, codes) = jointure
│                          declaration_agent -> agent -> chef_equipe : {code, nom,
│                          chef, jours, total} pour TOUS les agents du perimetre (index
│                          idx_declaration_agent_code) ; affichee, repliee, sur la page
│                          de televersement (remplace l'ancienne feuille « agents »).
│                          transcrire(conn, xlsx, type,
│                          codes_autorises=) : lit le format LARGE, normalise les
│                          en-tetes de date (date Excel, JJ/MM/AAAA, AAAA-MM-JJ,
│                          AAAAMMJJ) et fait un UPSERT ; cellule VIDE = pas de
│                          declaration (PAS un zero) ; refuse un code agent inconnu ou
│                          HORS PERIMETRE (codes_perimetre(conn, districts, communes)
│                          = codes vus dans interview__diagnostics.responsible du
│                          perimetre). Pages : choix DEN/VAD + formulaire + bilan.
├── export_rapport.py   <- EXPORT EXCEL du rapport (par district).            [FONCTIONNEL]
│                          generer_bytes(conn, code_district, nom, communes=) : reconstruit
│                          la liste des menages via rapport_core (_charger_diagnostics
│                          agents_noms=None -> garde les CODES agent, _charger_segments,
│                          _construire_menages) puis openpyxl. 5 feuilles :
│                          (1) « Rapport global » : couverture par commune vs projection
│                          RGPH-3 2025 (+total district), STRUCTURE DES MENAGES par commune
│                          (denombres, personnes, taille moyenne, ecart-type de la taille,
│                          % menages presents, %GPS), 1 tableau/commune par fokontany ;
│                          (2) « Denombrement par agent-jour » : UN tableau par
│                          chef d'equipe (commune/agent en lignes, dates en colonnes) ;
│                          (3) « BaseDenParAgent » : table PLATE (commune, chef, agent,
│                          fokontany, dates) ; (4) « segment_multiple » : un MEME AGENT
│                          qui denombre plus d'une fois le MEME code de segment dans un
│                          MEME fokontany (cle fokontany x code x agent) ; (5) « Ecart
│                          declaration-serveur » : par chef d'equipe, agent et date, le
│                          nombre DECLARE (declaration_agent) face au nombre RECU, l'ecart
│                          et l'ecart en % (cf. declarations.py). PLUS DE COLONNES CARNET
│                          e-Fokontany : la question a disparu du questionnaire de sept.
│                          2026 (elles n'affichaient que des « n/d »), remplacees par des
│                          renseignements reellement collectes. Taille du menage =
│                          taille_menD > 0 ; ecart-type de POPULATION (denombrement
│                          exhaustif) ; menage present = presence == 1 ; « — » = non
│                          calculable ; GPS = lat&lon numeriques.
│                          STYLE : en-tete texte FONCE sur fond
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
│                          transcription.py (page Expert survey). La STRUCTURE est
│                          RECONCILIEE (2026-09-21) : un .dta qui apporte des colonnes
│                          en plus (ou en moins) est accepte, colonnes ajoutees par
│                          ALTER TABLE, anciennes conservees ; garde-fou maj_db.REQUISES.
├── ajouter_colonne.py  <- ajoute a l'avance les colonnes d'un nouveau              [FONCTIONNEL]
│                          questionnaire, SANS transcrire de donnees (meme mecanique
│                          que maj_db ; ordre de `_schema` = celui du .dta).
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
4. ~~**Vrai suivi Visite à domicile** (dashboard ET transcription VAD) quand les données
   VAD existeront (remplacer les pages « pas encore disponible »).~~ **FAIT** :
   transcription et tableau de bord VAD en service (2026-09-18), et la vignette
   « Visite à domicile » de la fenêtre de sélection y mène, district par district
   (2026-09-19). `page_vad_indisponible` a été supprimée.
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

### Mises à jour ultérieures (2026-09-02)

- **RAPPORT DE MISSION IA — accès restreint + export WORD illustré** (`rapport_word.py`
  nouveau ; `rapport_mission.py` + `serveur_app.py`). Le rapport de mission **rédigé par
  IA** (`/rapport-mission/ia`) est désormais :
  - **RÉSERVÉ à deux LOGINS** (et non à un rôle) : `serveur_app.LOGINS_RAPPORT_IA =
    {"COORDOREG_01", "COORDOREG_02"}` (les deux Coordonnateurs régionaux), testé via
    `peut_rapport_ia(u)`. **Le National ET l'Admin PERDENT l'accès au rapport IA** (demande
    utilisateur). La **compilation HORS-LIGNE** `/rapport-mission` reste, elle, ouverte aux
    rôles de lecture (`_ROLES_JOURNAL_LECTURE`) ; seul le **bouton « Rapport rédigé par IA
    (Word) »** est masqué pour les non-autorisés (`ia_href=""` si `not peut_rapport_ia`).
    Pour ouvrir à un futur `COORDOREG_03` : l'ajouter à `LOGINS_RAPPORT_IA`.
  - **LIVRÉ EN WORD (.docx)** directement, plus en page HTML. Comme la génération IA dure
    1-2 min et que le streaming existe pour éviter le **504** proxy, le flux est :
    `/rapport-mission/ia` (GET) affiche la **page de progression EN FLUX** (heartbeats)
    pendant que l'IA rédige, puis — la rédaction finie — injecte le Markdown dans un
    **formulaire caché auto-soumis** (`rapport_mission.ia_stream_word_declenche`) qui **POST**
    vers **`/rapport-mission/ia/word`** (`_rapport_mission_ia_word_post`, route ajoutée à
    `do_POST`). Cette route **convertit le Markdown déjà produit** en `.docx` (AUCUN 2e appel
    IA -> rapide, pas de timeout) et le renvoie en pièce jointe (`_octets`, MIME
    wordprocessingml). Le Markdown posté est **déjà anonymisé** (aucun nom).
  - **Entrée directe depuis le formulaire** : pour les logins autorisés, le formulaire
    `page_formulaire(..., mode_ia=True)` a son **action pointée sur `/rapport-mission/ia`** —
    le bouton « **Générer le rapport Word (IA)** » lance donc directement la génération Word
    (plus la compilation hors-ligne). Les autres rôles de lecture gardent l'action
    `/rapport-mission` (compilation hors-ligne, bouton « Générer le rapport »). Le texte du
    formulaire prévient, en mode IA, que les journaux ANONYMISÉS sont envoyés à l'API.
  - **`rapport_word.construire_docx(markdown, rapport, perim_label) -> bytes`** (python-docx
    + matplotlib backend Agg + Pillow, **installés au venv**) : **page de garde** (bannière
    `images/images.jfif` convertie en PNG via PIL, titre, période/périmètre, **bande aux
    couleurs du drapeau** malgache), **cartes KPI** colorées, **2 GRAPHIQUES** matplotlib
    (entrées par district = barres H ; activité par jour = barres V), puis le **corps IA**
    (titres colorés/soulignés, listes, tableaux, gras/italique) via un mini-parseur
    Markdown->docx. Charte reprise du rapport HTML (`#12325c`/`#1558c9`). Numéros de page
    en pied. Module **tolérant** (bannière/graphe manquant -> sauté).
  - Testé en HTTP réel **sur une COPIE** (port 8011, préfixe `/rsu`, jamais la vraie base) :
    `COORDOREG_01` -> bouton IA présent, `POST /rapport-mission/ia/word` = **200** + `.docx`
    valide (en-tête `PK`, MIME + `Content-Disposition` corrects, ~300 Ko) ; `COORDONAT_01`
    -> **bouton absent**, `GET /rapport-mission/ia` = **303** vers `/coordonat`, `POST` word
    = **403**. Génération docx unitaire validée (3 tableaux, 3 images, ré-ouverture OK).
  - ⚠️ **Nouvelles dépendances serveur** : `python-docx`, `matplotlib` (+ `numpy`, `Pillow`,
    `lxml`…). À installer sur le serveur de prod : `venv/bin/pip install python-docx
    matplotlib`. La génération IA reste conditionnée à `ia_active()` (`RSU_IA_RAPPORT=1` +
    `ANTHROPIC_API_KEY`). **Redémarrage du service requis** pour servir les nouvelles routes
    (`kill` du process -> systemd relance ; cf. « Redémarrer sans sudo »).

- **CONTEXTE DE RÉFÉRENCE injecté dans le prompt IA** (`contexte_rsu.py` nouveau) : la note
  conceptuelle RSU/e-Fokontany (contexte, cadre RSU, e-Fokontany, articulation, principes,
  gouvernance + **mandat INSTAT / Loi n°2018-004 / secret statistique**, résultats attendus,
  **historique des phases 2023->2025**) est stockée dans `contexte_rsu.CONTEXTE_RSU` et
  ajoutée au système IA (`rapport_mission._SYSTEM_IA`). But : les sections CADRÉES
  (introduction, concept/justification, objectifs, gouvernance, historique) s'appuient sur des
  faits réels du programme. **Règle explicite** dans le prompt : le contexte sert au cadrage
  SEULEMENT ; le **déroulement et tous les chiffres viennent EXCLUSIVEMENT des journaux** (ne
  pas présenter l'historique/les districts d'autres vagues comme la mission en cours). Pas de
  nouvelle dépendance ; pris en compte au même redémarrage.

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

---

## Consolidation des branches + activation IA (récap 2026-09-02)

Trois chantiers ont été menés sur des branches séparées puis **réunis sur `main`**
(commit de fusion `910b03a`). `main` = version complète ; `responsive-ui` reste comme
historique (déjà fusionnée). **Rien n'est encore poussé sur GitHub** (faire `git push`
après validation ; ⚠️ `deploy/rsu-web.env` est gitignoré — ne jamais le pousser).

**Ce que `main` contient désormais, réuni :**
1. **Affichage adaptatif** (voir « Affichage adaptatif / responsive ») : base fluide
   `clamp(11px,0.18vw+9.5px,13px)`, défilement naturel + barre latérale sticky, mobile
   ≤860px, pages toutes fluides (`--rsu-fluid`).
2. **Menus repliables** (voir « Menus repliables ») : bouton **☰ du bandeau**
   (`.rsu-b-toggle` → `.rsu-col`) et bouton **☰ du dashboard** (`.rsu-nav-toggle` →
   `body.rsu-nav-col`), état mémorisé en `localStorage`.
3. **Rapport de mission** (`rapport_mission.py`, `rapport_word.py`, `contexte_rsu.py` ;
   voir les sections datées) : compilation **hors-ligne** (`/rapport-mission`, tous les
   rôles de lecture, gratuite) **+** rapport **rédigé par IA → Word** (`/rapport-mission/ia`,
   **réservé aux logins `LOGINS_RAPPORT_IA`**).

**Dépendances serveur (venv) ajoutées** — installer sur toute nouvelle machine :
`venv/bin/pip install anthropic python-docx matplotlib` (tire aussi Pillow, numpy, lxml…).
`anthropic` sert l'appel IA ; `python-docx`+`matplotlib`+`Pillow` l'export Word.

**Activer l'IA (sinon bouton → page « inactive », aucune donnée ne sort)** :
1. `cp deploy/rsu-web.env.exemple deploy/rsu-web.env` puis remplir
   `ANTHROPIC_API_KEY=sk-ant-…` et garder `RSU_IA_RAPPORT=1`. Si la clé est **liée à un
   workspace**, ajouter `ANTHROPIC_WORKSPACE_ID=wrkspc_…` (sinon erreur
   *anthropic-workspace-id is required*) — géré par `rapport_mission._client_ia`.
2. `deploy/rsu-web.service` charge ce fichier via `EnvironmentFile=-…/deploy/rsu-web.env`.
   Comme l'unité a changé, la réinstaller **une fois** (sudo) :
   `sudo cp deploy/rsu-web.service /etc/systemd/system/ && sudo systemctl daemon-reload
   && sudo systemctl restart rsu-web`. Ensuite, recharges de code = `kill` sans sudo.
3. Modèle **`claude-opus-5`** (~0,3–0,6 $/rapport ; Sonnet possible pour ~2,5× moins cher).

**Piège 504 (résolu)** : la génération IA (~1-2 min) dépassait le timeout du proxy
(nginx/Apache devant l'app). Corrigé **côté application** (pas de config proxy) : réponse
**en flux** avec un **heartbeat `<!-- . -->` sur CHAQUE événement du stream** (réflexion
comprise, pas seulement le texte — sinon coupure pendant la phase de réflexion) +
en-tête `X-Accel-Buffering: no`. Cf. `synthese_ia_iter` / `_rapport_mission_ia_get`.

**Cache CSS** : `/assets` est mis en cache 24 h (`max-age=86400`) → après un déploiement
qui touche `rapport.css`, tester avec **Ctrl+F5** (sinon l'ancien CSS est resservi).

---

## Pièces jointes du JOURNAL DE BORD (journal 2026-09-07)

L'équipe technique peut désormais **joindre des IMAGES et d'autres FICHIERS**
(Word, Excel, PDF…) à ses entrées de journal, à la **saisie** (`/journal`) **et** à la
**modification** (`/journal/modifier`).

### Stockage (par district)
- **Images** → `config.RAPPORT_IMAGES_DIR/<code_district>/` (défaut `Rapport_Images/`,
  env `RSU_RAPPORT_IMAGES`).
- **Autres fichiers** → `config.RAPPORT_FICHIER_DIR/<code_district>/` (défaut
  `Rapport_Fichier/`, env `RSU_RAPPORT_FICHIER`).
- Le **code district** est le 1er code du périmètre de l'auteur (`_dossier_district` ;
  les rôles d'écriture ont un seul district, sauf Comités Techniques → son 1er district).
- Classement image/fichier par **extension** (`_categorie_fichier`, `_EXT_IMAGE`) — donc
  robuste quel que soit le champ d'upload utilisé. Nom de stockage **sécurisé** + unique
  (`_nom_sur` + préfixe horodatage/jeton, garde `_sous_dossier`). Nom d'origine conservé
  en base pour l'affichage/téléchargement.

### Base
- Nouvelle table `journal_fichier(id, activite_id, login, code_district, categorie,
  nom_fichier, chemin, taille, cree_le)` créée au démarrage (`journal.creer_tables`).
  `chemin` = **relatif à `config.BASE`**. Helpers `ajouter_fichier`, `obtenir_fichier`,
  `fichiers_par_activite` (lot, 1 requête), `supprimer_fichier` (auteur seul).
- `journal.ecrire_activite` **renvoie l'`id`** de l'entrée (pour y rattacher les fichiers).
- `journal.activites` (lecture coordonnateur) **expose `id`** → pièces jointes visibles
  aussi en lecture.

### Serveur (`serveur_app.py`)
- `_form_multipart()` : parse UN POST → `(champs, fichiers)`, gère plusieurs fichiers par
  champ (`<input multiple>`) et retombe sur l'urlencodé. Remplace la lecture manuelle du
  corps dans `_journal_post` / `_journal_modifier_post`.
- `_stocker_fichiers_journal()` : range + enregistre (garde-fou taille `_TAILLE_MAX_FICHIER`
  = 25 Mo/fichier ; l'upload passe en RAM via `email`).
- Route **`GET /journal/fichier?id=`** (`_journal_fichier_get`) : sert la pièce (image
  **inline** pour JPG/PNG/GIF/WEBP/BMP via `_IMG_INLINE`, sinon **téléchargement** ; SVG
  jamais inline). **Accès** : l'auteur, OU un lecteur (`_ROLES_JOURNAL_LECTURE`) dont le
  périmètre couvre `code_district`. `Cache-Control: no-store` (données nominatives).
- Route **`POST /journal/fichier/supprimer`** (`_journal_fichier_supprimer_post`) : retire
  base + disque, **auteur seul**. Toutes ces routes placées **AVANT les gardes de rôle**.
- Affichage : `_journal_fichiers_html` (vignettes images + liens fichiers), injecté dans
  `_journal_entree_html` (mes entrées / historique) et dans `page_journal_lecture`
  (coordonnateurs) ; `_attacher_fichiers(conn, entrees)` renseigne `e["fichiers"]` en lot.
  Formulaires `page_journal_ecrire`/`page_journal_modifier` en `multipart/form-data` avec
  2 champs (images / autres) ; la page de modif liste les pièces existantes + 🗑.

### `.gitignore`
`Rapport_Images/`, `Rapport_Fichier/` (et `DATA_serveur/`) ajoutés — **données
nominatives, jamais versionnées**.

### Testé (COPIE de la base, jamais la vraie)
`ecrire_activite`→id ; parsing multipart (champ vide ignoré) ; rangement
`Rapport_Images/1101` (2) + `Rapport_Fichier/1101` (1) ; `fichiers_par_activite` (2 image/
1 fichier) ; `activites` expose l'id ; `supprimer_fichier` (refus autre login, OK auteur) ;
classification + sécurité du nom. **Redémarrage du service requis** (crée la table + sert
les routes ; cf. « Redémarrer sans sudo »). ⚠️ Rendu visuel (upload réel + vignettes) à
valider en HTTP sur un vrai poste.

## Pièces jointes ANALYSÉES par l'IA + reprises dans le rapport (journal 2026-09-07)

Suite (même jour) : les pièces jointes des journaux (photos + fichiers) sont désormais
**exploitées par la génération de rapport par IA** — réservée aux **logins
`LOGINS_RAPPORT_IA` = {COORDOREG_01, COORDOREG_02}** (inchangé).

- **Collecte** (`rapport_mission.pieces_jointes(conn, rapport, limite)`) : liste
  ORDONNÉE et bornée (`_MAX_PIECES`, env `RSU_RAPPORT_MAX_PIECES`, défaut 25) des pièces
  des journaux de la période/périmètre, numérotées **« Pièce n°K »**, avec contexte
  (district, date, fonction, extrait du journal). Dédoublonnage par `activite_id` (une
  entrée multi-district n'est comptée qu'une fois). **Ordre déterministe → mêmes numéros
  côté IA et côté Word.** Garde `_chemin_sur` (lecture uniquement sous Rapport_Images /
  Rapport_Fichier).
- **Analyse IA** (`_contenu_ia` → `synthese_ia_iter(rapport, perim_label, pieces)`) : le
  message utilisateur devient une **liste de blocs** = texte des journaux (anonymisé) +,
  pour chaque pièce, un libellé numéroté puis le contenu : **image** ré-encodée JPEG et
  redimensionnée ≤1400px (`_bloc_image_ia`, bloc `image` base64), **PDF** en bloc
  `document` base64, **Word/Excel/CSV/txt** en **texte extrait** (`_texte_document`,
  tronqué `_MAX_TEXTE_DOC`=4000 ; docx→python-docx, xlsx→openpyxl). `_SYSTEM_IA` instruit
  le modèle d'illustrer/justifier les activités via les pièces et de les citer par numéro
  (et de ne pas commenter des personnes identifiables).
- **Reprise dans le WORD** (`rapport_word._annexe_pieces` ; `construire_docx(markdown,
  rapport, perim_label, pieces)`) : nouvelle **« Annexe — Pièces justificatives »**
  (saut de page) — chaque **image** embarquée (Pillow→JPEG, `_image_pour_word`) sous son
  libellé « Pièce n°K — district · date · fonction » + l'extrait d'activité en légende ;
  les autres fichiers listés en référence. Mêmes numéros que ceux vus par l'IA.
- **serveur_app** : `_rapport_mission_ia_get` calcule `pieces` (conn ouverte) et les passe
  à `synthese_ia_iter` ; `_rapport_mission_ia_word_post` recalcule la MÊME liste et la
  passe à `construire_docx`. Bytes relus du disque (pas de conn nécessaire au streaming).
- **UI** : le formulaire IA (`page_formulaire(mode_ia=True)`) prévient que **photos et
  fichiers joints sont envoyés à l'API**, images analysées et reprises en annexe.
  ⚠️ **Confidentialité** : contrairement aux journaux (anonymisés), les **images/fichiers
  peuvent contenir des données nominatives** et **sortent vers l'API** — décision assumée
  (demande utilisateur) ; noté honnêtement dans l'UI.
- **Deps** : aucune nouvelle (Pillow/python-docx/openpyxl/anthropic déjà au venv). PDF via
  bloc `document` (support natif Opus 5).
- Testé sur COPIE : `pieces_jointes` (2 pièces numérotées + contexte), `_contenu_ia`
  (bloc image JPEG b64 + texte .docx « 42 ménages » extrait + libellés Pièce n°1/2),
  `construire_docx` (annexe présente, images embarquées, docx rouvrable). **Redémarrage
  du service requis.** ⚠️ Un vrai appel IA (clé active) avec photos réelles reste à
  valider en ligne.

## Rapport IA — tableau de présentation de l'équipe (journal 2026-09-07)

Ajout, dans le rapport de mission **rédigé par IA (Word)**, d'une section
**« Composition de l'équipe »** (après les KPI, avant les graphiques et le corps IA).
Tableau à 4 colonnes : **Nom et Prénom**, **Fonction / Poste**, **District
d'affectation**, **Axe** (communes) — ce dernier renseigné uniquement pour
**Superviseur Technique** et **Logistique Inter-Communale** (`_ROLES_AXE`).

- **Déterministe, PAS produit par l'IA** : construit depuis les comptes
  (`rapport_mission.equipe(conn, districts)` → `utilisateurs.lister`), donc **avec les
  noms réels** (la table est factuelle ; les journaux envoyés à l'IA restent anonymisés).
  Borné au **périmètre du rapport** (districts_eff) ; exclut Admin et Coordonnateur
  Nationale (zone entière) ; comptes actifs seulement. Trié par ordre de poste
  (`_ORDRE_ROLES`) puis district puis nom. District = libellé(s) via `_noms_districts` ;
  axe = communes via `zones.libelle_commune`.
- **Rendu Word** : `rapport_word._tableau_equipe(doc, equipe)` (en-tête foncé/texte blanc,
  style Table Grid) ; `construire_docx(..., equipe=)`. `serveur_app._rapport_mission_ia_
  word_post` calcule `equipe = rapport_mission.equipe(conn, districts_eff)` et le passe.
  Le GET (analyse IA) est inchangé — aucun nom envoyé à l'API.
- Testé sur COPIE (base réelle) : districts 1101+1106 → 28 membres, ordre par poste,
  axe réservé Sup Technique/Log Inter-Communale, section + tableau présents dans le .docx.
  **Redémarrage du service requis.**

## Journal — ajout PROGRESSIF de plusieurs pièces (journal 2026-09-07)

Les champs images/fichiers de la saisie (`page_journal_ecrire`) ET de la modification
(`page_journal_modifier`) portaient déjà `multiple` (le serveur `_form_multipart` accepte
plusieurs fichiers par champ). Ajout d'un confort d'usage : `_JOURNAL_PJ_SCRIPT` (inline,
injecté dans les deux pages) permet de **cumuler** les fichiers en **plusieurs clics** (au
lieu du remplacement natif à chaque sélection), affiche la **liste des fichiers choisis**
(chips) et permet d'en **retirer** un avant l'envoi. Repose sur `DataTransfer`
(input.files réassigné → envoi standard, rien à changer côté serveur) ; **repli** sur le
`multiple` natif si `DataTransfer` indisponible. Marqueurs : classe `jr-file-multi` +
conteneur `#liste-<id>` par input. CSS `.jr-file-chip`/`.jr-file-x` dans `_STYLE_JOURNAL`.

## Journal — sous-dossier par LOGIN (journal 2026-09-07)

Niveau de rangement supplémentaire : les pièces jointes sont désormais stockées sous
**`<district>/<login>/`** (et non plus directement sous `<district>/`) :
`Rapport_Images/<code_district>/<login>/…` et `Rapport_Fichier/<code_district>/<login>/…`.
`_stocker_fichiers_journal` ajoute `_dossier_login(login)` (login nettoyé). Le service
(`/journal/fichier`) et la suppression résolvent le chemin depuis la base (colonne
`chemin`) et restent bornés aux deux dossiers racine — aucun autre changement.

## Changement de QUESTIONNAIRE — migration de structure (journal 2026-09-11)

Le téléversement de l'Expert était **refusé** : « structure différente ». Diagnostic et
migration complète.

### Cause réelle (deux blocages distincts)
1. **Structure** (`maj_db.maj_table`, l.140) : la base avait été construite avec l'**ancien
   questionnaire** (mission précédente), le terrain collecte avec le **nouveau**. Écart :
   `den_menage` **14 → 413** colonnes (perd `num_fkt`, `nbr_max_bat`, `nbr_max_men` ;
   gagne `date`, `login` + 400 colonnes `segment_men__N`/`__Nc`) ; `segment_roster`
   **25 → 20** (perd `date`, **`carnet`**, `copie_carnet`, `ID_efkt`, `indication`,
   `copie_presence` ; gagne `segment_men`) ; `interview__diagnostics` **inchangé**.
   ⚠️ Comparer deux EXPORTS ne montre rien — la référence est le schéma en base (`_schema`).
2. **Données** (`serveur_app`, l.4813) : l'export contenait **1 segment sur 329** saisi sur
   un autre district (essai d'agent : `05-00-65-26`, VAVATENINA 5206, agent `EQ1_FNRVE_0147`,
   6 ménages) → `districts_du_den != {code}` refusait TOUT le dossier.

### Ce qui a été fait
- **Règle « filtrer et avertir »** (décision utilisateur) : `db_source.cles_hors_district
  (dossier, code)` renvoie les `interview__key` hors district ; `maj_db.maj_table/
  maj_depuis_dossier` acceptent **`exclure_cles`** (filtre les 3 tables, qui se rattachent
  au segment par `interview__key`) ; `serveur_app._transcription_post` ne refuse plus que si
  **rien** ne concerne le district de l'Expert (`code not in districts`), sinon écarte +
  **avertit** (bandeau orange dans `transcription.page_transcription`, `apercu["ecartes"]`
  / `["ecartes_districts"]`) et journalise le nombre écarté. Filtre appliqué à l'aperçu ET
  à l'application.
- **Lecture TOLÉRANTE aux deux structures** (`rapport_core._col_opt`) : une colonne absente
  vaut `None` au lieu de planter → **les bases archivées restent exploitables**.
  `num_fkt` → retombe sur `fokontany` (même code 8 chiffres, cf. §9.3) ; la `date` du ménage
  retombe sur celle du **segment** (elle a migré du roster vers DEN_MENAGE) ; `_REQUIS`
  allégé en conséquence.
- **Sections « carnet » / « électrification » CONSERVÉES mais en « n/d »** (décision
  utilisateur — surtout PAS des 0, qui se liraient comme de vrais résultats) :
  `rapport_core._dispo(menages, champ)` → `carnetDispo`/`elecDispo` dans les agrégats +
  `const CARNET_DISPO`/`ELEC_DISPO` injectés ; gabarit `template_tail.html` : helpers
  `carnNum`/`carnPct`/`chartND` (repli `true` si non injecté → **exe inchangé**), 4 donuts
  remplacés par une note `.chart-nd` (CSS dans `assets/rapport.css`), série « Avec carnet »
  retirée du graphe par agent. Export Excel (`export_rapport`) : `_carnet_dispo`/`_c`,
  colonnes carnet en « n/d » + note explicative dans le titre du Tableau 2.
- **Migration de la base** (suppression des anciennes données **autorisée par
  l'utilisateur**) : 2 sauvegardes à chaud dans `deploy/backups/` (`rsu_local-avant-
  migration-*.sqlite`, 124 Mo), DROP des 3 tables + purge de `_schema`/`_value_labels`,
  rechargement par le chemin réel (`maj_db` + filtre district), `equipes.synchroniser_agents`,
  `VACUUM` (124 Mo → **24 Mo**), redémarrage du service.
  **Perdu volontairement** : 5 882 segments / 353 646 ménages de la mission précédente
  (MAMPIKONY, IKALAMAVONY, BELO SUR TSIRIBIHINA, SOANIERANA IVONGO, ANTSIRABE I,
  MIANDRIVAZO). **Préservé** : journaux (616), comptes (57), zones, consignes, pièces jointes.
  **État** : 328 segments / 1 857 ménages / 343 diagnostics, FENERIVE EST, 05→08 sept. 2026.

### Vérifié (sur COPIE d'abord, jamais la vraie base)
Migration + rechargement (filtre : 1 segment et 6 ménages écartés, exactement l'essai) ;
chaîne de rapport (date héritée du segment, `fktcode` = 52010602, `carnetDispo=False`) ;
rapport HTML généré (893 Ko, `CARNET_DISPO = false`) ; export Excel (colonnes « n/d » +
note) ; **compatibilité ascendante** sur la base archivée (district 4405 : `carnet=4`,
`elec=1`, chiffres réels 249/943/198, aucune mention « n/d ») ; app en ligne après
redémarrage (Apache http **et** https → 200).

### À retenir
- **« Structure différente » ≠ les deux exports diffèrent** : `maj_db` compare le `.dta` au
  **schéma enregistré en base** (`_schema`). Deux exports successifs peuvent être identiques
  et le téléversement échouer quand même, parce que la BASE date d'un questionnaire antérieur.
- **Un 0 n'est pas « pas de donnée »** : une question retirée du questionnaire produit des
  comptages à 0 que le lecteur prend pour des résultats. Toujours distinguer par un drapeau
  de disponibilité (`_dispo`) et afficher « n/d ».
- **Ne pas refuser tout un lot pour une ligne** : un export de terrain contient des essais
  d'agents. Filtrer + avertir garde la collecte fluide sans polluer la base.
- **Largeur des colonnes texte Stata (`str26`→`str53`)** : varie avec la valeur la plus
  longue de l'extrait, ce n'est PAS un changement de structure.
- **Orphelins préexistants** (non corrigés) : 7 lignes `segment_roster` (5 interviews :
  29-69-14-19, 46-68-58-09, 63-69-17-52, 91-98-10-93, 98-88-58-15) n'ont pas de segment
  correspondant dans `DEN_MENAGE` — présent dans les exports du 7 ET du 8 septembre, donc
  côté Survey Solutions. D'où 1 857 lignes chargées mais 1 850 ménages au rapport.

### ⚠️ Resync exe (cf. §1)
`rapport_core.py`, `templeteHtml/template_tail.html` et `assets/rapport.css` ont changé
ensemble → à recopier ENSEMBLE vers `..\RSU_Rapport\`. Les blocs ajoutés sont **inertes côté
exe** (`typeof CARNET_DISPO === 'undefined'` → `true`, comportement d'origine).

### Préchargement (VAD) — conséquence du changement de questionnaire (2026-09-11)

Vérification demandée du fichier de sortie de `prechargement.py`. **Le résultat attendu
est bien produit** — mais il l'était pour une mauvaise raison, corrigée.

**Constat** : `ID_efkt` (scan du carnet e-Fokontany) et `num_fkt` ne sont plus au
questionnaire. Or `prechargement._charger_menages` les lisait par `ros.col("ID_efkt")` /
`den.col("num_fkt")`.

⚠️ **PIÈGE SQLite — chaîne double-quotée** : `DbDataset.col` construit `SELECT "<nom>"`.
Quand la colonne n'existe pas, SQLite **ne lève PAS d'erreur** : il retombe sur une
**chaîne littérale** et renvoie le texte `'ID_efkt'` / `'num_fkt'` sur **chaque ligne**.
Vérifié : `SELECT "num_fkt" FROM den_menage LIMIT 3` -> `['num_fkt','num_fkt','num_fkt']`.
Ici l'effet était bénin par hasard (`_nettoyer_idefkt` rejette toute valeur < 15
caractères -> `''` -> `est_nouveau=True`), mais c'est **latent** : si `fokontany` était
NULL, `code8` prendrait la chaîne `'num_fkt'` ; et **PostgreSQL échouerait franchement**
(`column "num_fkt" does not exist`) — cf. étape 3 de la feuille de route.

**Correction** : `prechargement._col_opt(d, nom, defaut=None)` (même patron que
`rapport_core._col_opt`) — une colonne absente de `d.varnames` renvoie une colonne à
`None`, jamais un `SELECT` hasardeux. Appliqué à `num_fkt` et `ID_efkt`.

**Sortie vérifiée** (district 5201, base réelle, `base_prechargement_*.xlsx`) :

| Feuille | Lignes | Colonnes |
|---|---|---|
| `Ensemble` | 1 850 | 17 |
| `nouveau` | **1 850** | 20 |
| `e_fokontany` | **0** (en-tête seul) | 17 |

- `nouveau` == `Ensemble` (mêmes `interview_keyden`, ensembles **identiques**, 0 écart) ;
- colonne `IdeFKT` : **toutes vides** (plus aucune fuite du littéral) ;
- géographie saine : district `5201` sur les 1 850 lignes, 49 codes fokontany, **0** code
  non numérique ;
- `charge_agents_*.xlsx` : 146 agents ; **les 3 modes** (`denombrement`, `equilibre`,
  `equilibre_fort`) produisent le même découpage sans erreur.

**UI** : la page `/traitement/prechargement` porte désormais un bandeau orange expliquant
que la feuille `e_fokontany` est vide **par construction** (plus de collecte du carnet) et
que `Ensemble == nouveau` — sinon une feuille vide passerait pour un bug de génération.

**À retenir** : en SQLite, une colonne disparue ne casse pas une requête — elle renvoie
silencieusement son propre nom. **Toujours tester l'existence via `varnames`** avant de
lire une colonne susceptible d'avoir été retirée du questionnaire.

## Déclarations des agents + refonte des colonnes e-Fokontany (journal 2026-09-17)

Trois demandes liées, autour d'une même idée : **confronter ce que les agents DÉCLARENT
avoir fait à ce qui ARRIVE RÉELLEMENT AU SERVEUR**.

### 1. Nouvelle table `declaration_agent` (module `declarations.py`)

```sql
declaration_agent(
  "code_agent"     TEXT NOT NULL REFERENCES "agent"("login_ae"),  -- Code_Agent
  "date"           TEXT NOT NULL,          -- AAAAMMJJ (le format des dates du rapport)
  "type_operation" TEXT NOT NULL,          -- 'DEN' (dénombrement) ou 'VAD'
  "nombre"         INTEGER NOT NULL,       -- ménages dénombrés / interviewés déclarés
  PRIMARY KEY ("code_agent","date","type_operation"))
```

Noms de colonnes en `snake_case` minuscule comme **toutes** les autres tables du projet
(`chef_equipe`, `agent`, `journal_activite`…). La table est créée au démarrage par
`preparer()` **après** `equipes.creer_tables` (cible de la clé étrangère).

Le format de `date` est **AAAAMMJJ** — volontairement celui de `menages["date"]`
(`rapport_core._date_j`) : sans ça, aucune jointure possible entre déclaration et serveur.

### 2. Saisie par le Superviseur Technique (routes `/declaration…`)

Menu `/suptech` → nouvelle carte **« Déclaration des nombres de ménages dénombrés /
interviewés par les Agents »** (`_ROLES_DECLARATION`, 403 pour tout autre rôle) :

| Route | Rôle |
|---|---|
| `GET /declaration` | choix **Dénombrement** ou **VAD** (compteurs de ce qui est déjà en base) |
| `GET /declaration/{den,vad}` | rappel du format, modèle, formulaire de téléversement, bilan |
| `GET /declaration/modele/{den,vad}.xlsx` | modèle **pré-rempli** (ses agents, ses dates) |
| `POST /declaration/{den,vad}` | transcription du classeur → `declaration_agent` |

**Format du classeur** (celui du modèle) : ligne 1 = en-têtes, **colonne 1 = le code de
l'agent**, **colonnes 2 à n = les dates**. Une cellule = le nombre déclaré ; une cellule
**vide = pas de déclaration ce jour-là** (et surtout **pas un zéro** : rien n'est écrit).
Les en-têtes de date sont acceptées en date Excel, `JJ/MM/AAAA`, `AAAA-MM-JJ` ou
`AAAAMMJJ` (`declarations._norm_date`). La transcription est un **UPSERT** (ajoute / met à
jour / ne supprime rien), comme `equipes.py` et `maj_db.py`.

**Périmètre respecté** : `codes_autorises = declarations.codes_perimetre(conn, districts,
communes)` — les codes agent vus dans `interview__diagnostics.responsible` du périmètre
donné par `perimetre(u)` (SOURCE DE VÉRITÉ). Un code hors périmètre, ou absent de la table
`agent`, est **refusé ligne par ligne** et signalé dans le bilan ; le reste passe.
Vérifié en bout-en-bout : sur BETIOKY SUD, le superviseur de 5 communes ne voit que
**36 déclarations / 21 agents** là où le district en compte 243 / 154.

Le modèle porte **2 feuilles** — `declaration` (la **seule** lue) et `mode d'emploi`.
Faute de dates observées (cas du **VAD**, pas encore collecté), il propose 14 jours à
partir d'aujourd'hui.

**Aucun renseignement d'agent dans le classeur** (décision utilisateur) : le nom et le chef
d'équipe sont déjà dans `agent` / `chef_equipe`, et `declaration_agent` y est reliée par la
clé étrangère `code_agent -> agent(login_ae)`. Les recopier dans l'Excel créerait une
seconde source de vérité, qui divergerait à la première correction de nom. La
correspondance **code → agent → chef d'équipe** est donc obtenue **par jointure** :
`declarations.recap_agents(conn, type, codes)` (index `idx_declaration_agent_code`) renvoie
`{code, nom, chef, jours, total}` pour **tous** les agents du périmètre — y compris ceux
qui n'ont encore rien déclaré — et alimente un tableau replié « Vos agents (n) » sur la page
de téléversement. Un nom encore égal au code (agent auto-créé par
`equipes.synchroniser_agents`) s'affiche « nom non renseigné » plutôt que de répéter le code.

### 3. Export Excel : les colonnes e-Fokontany remplacées

Les colonnes **« dont avec carnet / sans carnet / carnet scanné »** (carnet **e-Fokontany**)
ne portaient plus que des `n/d` depuis le questionnaire de septembre 2026 (cf. la section
datée 2026-09-11 : `carnet`, `copie_carnet`, `ID_efkt` ont disparu du roster). Elles sont
**retirées** des tableaux 2 et 3 de la feuille « Rapport global » et remplacées par ce qui
est **réellement collecté** :

| Colonne | Définition |
|---|---|
| Ménages dénombrés | inchangée |
| Personnes dénombrées | somme des `taille_menD` renseignées |
| Taille moyenne du ménage | moyenne des `taille_menD` **> 0** (une taille nulle/absente n'est pas un ménage d'une personne : c'est une taille non renseignée — même règle que le gabarit) |
| Écart-type de la taille du ménage | `statistics.pstdev` — écart-type de **population**, le dénombrement étant exhaustif sur le périmètre |
| Ménages présents (%) | `presence == 1` sur les `presence ∈ {1,2}` (99,98 % renseignés en base) |
| GPS capturé (%) | inchangée (lat **et** lon numériques) |

`« — »` = non calculable (aucun ménage, aucune taille renseignée, un seul ménage pour
l'écart-type). `_stats()` ne renvoie plus un tuple mais un **accumulateur** (`_cumul`,
`_acc_vide`, `_ligne_struct`) : les totaux commune/district recalculent moyenne et
écart-type sur **l'ensemble des tailles**, et non comme une moyenne de moyennes.

### 4. Nouvelle feuille « Écart déclaration-serveur »

Cinquième feuille du classeur. Un **tableau par chef d'équipe** ; une ligne par
**agent × date** ; colonnes *Ménages déclarés · Ménages reçus au serveur · Écart
(déclaré − reçu) · Écart (% du déclaré)*, avec un total par CE et un total général.

- **Écart > 0** : il est arrivé MOINS que déclaré (synchronisation en retard, ou
  sur-déclaration). **Écart < 0** : il est arrivé PLUS que déclaré.
- Périmètre des lignes : les agents ayant des données dans le district / les communes,
  **plus** ceux qui ont déclaré et dépendent d'un chef d'équipe du périmètre — sinon un
  agent qui déclare alors que **rien** n'est encore arrivé au serveur (le cas le plus
  intéressant) serait invisible.
- Seul le **DEN** est comparable : les déclarations **VAD** sont bien stockées, mais aucune
  donnée VAD n'arrive encore au serveur → une phrase de la note d'en-tête le dit et donne
  leur nombre, plutôt que de laisser croire à un oubli.

### Vérifications faites

- Modèle généré (154 agents, 3 dates observées), rempli, transcrit : `+243` déclarations,
  **2e passage → `=243` inchangées** (UPSERT idempotent) ; cellule `"abc"` et agent
  `AGENT_BIDON` refusés ligne par ligne avec message.
- Parcours HTTP réel (serveur sur un port de test, base **copiée**) : login superviseur →
  `/suptech` (carte présente) → `/declaration` → `/declaration/den` → modèle `.xlsx` →
  `POST` du classeur rempli (`+7 / ~35`, agent hors périmètre refusé) → `/declaration/vad`
  (`+42`) → `/export/rapport.xlsx` : 5 feuilles, écart calculé, borné aux 5 communes.
- Rôle **Traitement** sur `/declaration` : **403** « Accès réservé aux Superviseurs
  Techniques ».

**À retenir** : quand une question disparaît du questionnaire, ne pas se contenter
d'afficher `n/d` indéfiniment — au bout d'un moment, la colonne occupe de la place sans
rien dire. La remplacer par un indicateur que la collecte fournit vraiment.

## Tableau de bord : carnet e-Fokontany RETIRÉ, taille des ménages AJOUTÉE (journal 2026-09-17)

Suite logique de la refonte de l'export Excel (section précédente) : le **carnet
e-Fokontany** disparaît aussi du **tableau de bord**, et la **taille des ménages** prend sa
place. Le carnet n'était plus collecté depuis le questionnaire de septembre 2026 : ses
blocs affichaient `n/d` (décision du 2026-09-11), ce qui occupait de la place sans rien
dire. On ne l'affiche plus du tout.

### Ce qui a été retiré (3 fichiers + les tests)

| Fichier | Retiré |
|---|---|
| `templeteHtml/template_head.html` | carte KPI « Avec carnet » ; graphique « Possession de carnet » (vue générale) ; graphique « Possession de carnet de dénombrement » (page Qualité) ; colonne « % Avec carnet » du récap par agent et du tableau par zone ; sous-titre « Total, Présents, Avec carnet » |
| `templeteHtml/template_tail.html` | `CARNET_LABEL`, `CARNET_COLOR`, `hasCarnet()`, `_carnOk`, `carnNum()`, `carnPct()` ; `nCarnet` des agrégats de segment ; les 3 graphiques ; la série « Avec carnet » du graphique par agent ; les `<td>` correspondants ; la colonne « Carnet » de **l'export CSV** ; la carte KPI « Avec carnet » de la fiche d'un agent (grille 4 → 3 colonnes) |
| `rapport_core.py` | lecture de la colonne `carnet` et champ `carnet` des ménages ; `_has_carnet()` ; `nCarnet` / `nbCarnet` / `carnet` / `carnetDispo` des agrégats serveur ; injection de `const CARNET_DISPO` |
| `tests/test_agrege_oracle.js`, `tests/test_agrege.py` | mêmes suppressions, pour que l'oracle JS reste le miroir exact de `rapport_core.agrege` |
| `manuel_roles.py` | la puce « Qualité — carnet, scan, complétude » décrit maintenant le contenu réel de la section |

⚠️ `ELEC_DISPO` / `_elecOk` / `chartND()` **restent** : l'électrification (`indication`) n'est
plus collectée non plus, mais l'utilisateur n'a demandé que le retrait du carnet — son bloc
continue d'afficher « n/d ».

### Ce qui a été ajouté : taille moyenne + écart-type

- **Nouvelle carte KPI « Taille moyenne des ménages »** (à la place du carnet, même position,
  même couleur) : valeur = moyenne, sous-titre = `écart-type 1,37 · 615 personnes`.
- **Page Qualité** : le sous-titre de l'histogramme « Taille des ménages » porte désormais
  `Moyenne 2,37 · écart-type 1,37 · 260 ménage(s) renseigné(s)`.
- Règles, identiques à celles de l'export Excel : seules les tailles **> 0** comptent (une
  taille nulle/absente n'est pas un ménage d'une personne, c'est une taille non renseignée —
  même règle que l'histogramme existant) ; **écart-type de POPULATION** (le dénombrement est
  exhaustif sur le périmètre).

**Double implémentation, volontairement jumelle** : `rapport_core._taille_stats()` (agrégat
serveur des pages district/commune allégées) et `tailleStats()` du gabarit (données brutes,
niveau fokontany et rapport exe). Même ordre d'opérations des deux côtés, et même arrondi —
`_r2()` en Python reprend `_js_round(x*100)/100`, `r2()` en JS est `Math.round(x*100)/100` —
pour que les deux chemins affichent **le même nombre**. `general` porte désormais
`nTaille`, `nbPersonnes`, `tailleMoy`, `tailleEt` ; l'oracle JS des tests les recalcule.

### Vérification : navigateur réel, faute de Node

`tests/test_agrege.py` ne peut pas tourner ici (**Node.js n'est pas installé sur le
serveur** : `FileNotFoundError: 'node'`). L'équivalence Python ↔ JS a donc été vérifiée
**dans un vrai navigateur**, via `geckodriver` + Firefox headless (tous deux présents en
snap), sur une **copie** de la base :

| Chemin | Source des chiffres | Résultat |
|---|---|---|
| `/vue/general` (district, **agrégat serveur**) | `rapport_core._taille_stats` | `2,37` · écart-type `1,37` · 615 personnes |
| Rapport complet SPA (**données brutes, calcul navigateur**) | `tailleStats()` du gabarit | `2,37` · écart-type `1,37` · 615 personnes |

Soit **le même nombre par les deux chemins** — ce que l'oracle Node aurait vérifié.
Également contrôlé : plus aucune occurrence de « carnet » dans le DOM des pages
`general` / `qualite` / `agent` / `zone` ; tableau par zone **8 `<th>` / 8 `<td>`** ;
récap agent **5 / 5** ; fiche d'un agent **6 / 6** avec 3 cartes KPI ; page Qualité à
**5 graphiques** (au lieu de 6) ; `exportCSV()` s'exécute sans erreur.

> Astuce réutilisable : `geckodriver` parle le protocole WebDriver en JSON sur HTTP — on le
> pilote en 30 lignes d'`urllib`, sans installer Selenium. Seul piège : Firefox en **snap**
> ne peut pas lire un `file://` sous `/tmp/claude-*` (confinement) → servir la page avec
> `python -m http.server`. Et les `const` de premier niveau d'un `<script>` (`MENAGES`,
> `SEGMENTS`) ne sont **pas** sur `window` : inatteignables depuis `execute/sync` ; les
> `function` de premier niveau, si (d'où l'appel direct à `renderAgentPage(...)`).

### ⚠️ Bug PRÉEXISTANT trouvé au passage (CORRIGÉ depuis, voir la dernière section)

La descente au niveau **fokontany** renvoie **0 ménage** : `db_source.source_db(..., fkt=)`
filtre encore sur `"num_fkt"`, colonne **supprimée de `den_menage`** par le questionnaire de
septembre 2026 (`fokontany` porte désormais le code à 8 chiffres). En SQLite, `WHERE
"num_fkt" = 63050604` sur une colonne absente ne lève **aucune erreur** : l'identifiant est
relu comme la chaîne `'num_fkt'` → la condition est toujours fausse. Vérifié :

```
SELECT COUNT(*) FROM den_menage WHERE "num_fkt"  = 63050604   ->  0
SELECT COUNT(*) FROM den_menage WHERE "fokontany" = 63050604   ->  5
```

`rapport_core` avait été rendu tolérant en septembre (`_col_opt`, `num_fkt` → `fokontany`),
mais **pas** `db_source.source_db` ni la route `/fokontany/<code>`. Correction à faire dans
la foulée, avec son propre test (toutes les sections, clés de cache).

## « Segment multiple » : définition RÉVISÉE (journal 2026-09-17)

**Nouvelle règle (demande utilisateur)** : un segment est **multiple** quand **un MÊME
AGENT** dénombre **plus d'une fois le MÊME code de segment dans un MÊME fokontany**.

Deux agents **différents** qui font chacun le S01 d'un même fokontany ne sont **PAS** un
segment multiple : c'est un **partage de travail**, pas un doublon. C'est exactement ce que
l'ancienne règle comptait à tort.

| | Clé de regroupement | Multiple si |
|---|---|---|
| Avant | `(fokontany, code)` | plus d'une ligne DEN_MENAGE |
| **Maintenant** | `(fokontany, code, **agent**)` | plus d'une ligne DEN_MENAGE |

L'agent entrant dans la clé, la colonne « **Agents concernés** » (un ensemble) devient une
colonne « **Agent** » (une valeur), et « Nombre » devient « **Nombre de fois dénombré** ».
Un segment sans code agent est regroupé sous `(agent inconnu)` — signalé plutôt que masqué.

### Où

- `templeteHtml/template_head.html` — la note de définition de la page.
- `templeteHtml/template_tail.html` — `renderMultiSection()` : clé `fk|code|agent`,
  colonnes et tris aux 3 niveaux, lignes de comptage.
- `export_rapport.py` — feuille **segment_multiple** : mêmes clé, colonnes et note.
- `manuel_roles.py` — la puce du manuel.

### Effet mesuré (district 6305, base réelle, 790 lignes DEN_MENAGE)

| | Cas détectés |
|---|---|
| Ancienne règle (fokontany × code) | 92 |
| **Nouvelle règle** (fokontany × code × agent) | 92 |

Même total, mais **ce ne sont pas les mêmes cas** : **47** anciens cas disparaissent — ce
n'étaient que des agents différents sur le même code (ex. fokontany 63051209, segment 1,
3 fois, par 3 agents distincts) — et les cas restants se **scindent par agent**, ce qui fait
remonter le compte. Exemple conservé, et bien plus parlant : fokontany 63051101, segment 1,
**18 fois par le seul agent EQ1_BTKS_0121**.

### Vérifications (Firefox headless + geckodriver, base copiée)

- `/vue/multi` (district) : 4 `<th>` / 4 `<td>`, colonnes *Fokontany · Segment · Agent ·
  Nombre de fois dénombré*, note de définition à jour.
- `/vue/multi/commune/630506` : idem, 2 cas.
- Rapport SPA complet, descente au **fokontany** AMBALAHAZO (63051101) : 3 `<th>` / 3
  `<td>`, **29 cas sur 97 couples segment × agent**, 197 segments dénombrés.
- Feuille Excel `segment_multiple` : mêmes chiffres que le tableau de bord (AMBALAHAZO
  segment 1 → EQ1_BTKS_0121 → 18), total « 92 cas ».

⚠️ La page **au niveau fokontany du dashboard web** affichait « 0 segment dénombré » à cause
du **bug `num_fkt`** — **corrigé depuis** (voir la section « Descente au fokontany »
ci-dessous) : `/vue/multi/fokontany/63050605` montre désormais le même cas que la vue
commune (segment 1, EQ1_BTKS_0225, 2 fois).

## Préchargement : règle d'acceptation d'un fichier d'exclusion (journal 2026-09-17)

**Signalement utilisateur** : sur `/traitement/prechargement`, le téléversement d'un
préchargement déjà généré serait *refusé quand la feuille `e_fokontany` ne contient rien* —
alors que cette feuille est **vide par construction** depuis septembre 2026 (plus de scan du
carnet e-Fokontany), et qu'un fichier réduit à la seule feuille **nouveau** est **juste**.

### Ce que le code faisait vraiment

`prechargement._keyden_precedents()` ne regardait **pas** les noms de feuilles : il
parcourait toutes les feuilles et gardait celles portant une colonne `interview_keyden`.
Trois variantes ont été fabriquées et testées — fichier complet (`e_fokontany` en-tête
seul), `e_fokontany` totalement vide (sans en-tête), **fichier réduit à la seule feuille
`nouveau`** — et **les trois étaient déjà acceptées**. Aucun refus lié à `e_fokontany`.

Le message que l'utilisateur voyait était en fait :

> « Tous les menages ont deja ete envoyes dans les prechargements precedents : rien de
> nouveau a exporter. »

C'est-à-dire : le fichier **a été lu**, et il couvrait déjà tous les ménages du district.
Rien dans le message ne le disait — d'où le diagnostic (« il refuse mon fichier »).

### Ce qui a été fait : rendre la règle EXPLICITE et les messages honnêtes

Le vrai défaut n'était pas la règle, c'était son **silence**. Trois corrections :

1. **Règle écrite dans le code** (constante `CLE_MENAGE` + commentaire de bloc) : un
   classeur est **valide dès qu'UNE de ses feuilles porte la colonne `interview_keyden`**.
   Ce sont les **clés ménage** qui comptent, jamais les noms de feuilles. Une feuille vide,
   ou sans cette colonne — `e_fokontany` au premier chef — est **ignorée sans pénalité** ;
   un fichier réduit à `nouveau` est valide.
2. **Un fichier vraiment inexploitable est REFUSÉ, en disant lequel et pourquoi.**
   `_keyden_precedents` renvoie désormais `(deja, rapport)`, avec par fichier : feuilles
   lues (+ clés apportées), feuilles ignorées (+ motif), ou motif de refus. Deux cas de
   refus seulement : classeur illisible, ou **aucune** feuille ne portant `interview_keyden`.
   Un seul fichier refusé arrête la génération : exclure **moins** que prévu renverrait sur
   le terrain des ménages **déjà envoyés**. Bénéfice immédiat : téléverser par erreur
   `charge_agents_*.xlsx` (ses 3 feuilles n'ont pas la colonne) était jusqu'ici **ignoré en
   silence** et reproduisait la base complète ; c'est maintenant dit.
3. **Le message « rien de nouveau » dit qu'il a LU le fichier** : nombre de ménages du
   district, nombre de clés lues, détail feuille par feuille, et « ce n'est pas un refus de
   format ». Le bandeau jaune de la page énonce la règle avant même le téléversement.
   Côté serveur, `_traitement_prechargement_post` convertit les `\n` du bilan en `<br>`
   (sinon le détail par fichier s'écrasait en un paragraphe illisible).

### Vérifications (base copiée, parcours HTTP réel en rôle Traitement)

| Fichier téléversé | Résultat |
|---|---|
| complet (Ensemble + nouveau + e_fokontany en-tête seul) | lu, 4059 clés |
| **seulement la feuille `nouveau`** | **lu, 4059 clés** |
| `e_fokontany` totalement vide (sans en-tête) | lu, 4059 clés, feuille ignorée signalée |
| `charge_agents_*.xlsx` (erreur courante) | **refusé**, motif + règle rappelés |
| pas un `.xlsx` | **refusé** (`BadZipFile`), motif donné |
| **partiel** : `nouveau` avec 2029 lignes | **ZIP produit**, 4059 − 2029 = **2030** ménages restants ✓ |

**À retenir** : quand un utilisateur dit « l'application refuse mon fichier », commencer par
reproduire — ici le code acceptait déjà tout ce qu'il fallait. Le bug n'était pas dans la
règle mais dans le message, qui laissait deviner la cause. Un refus doit toujours nommer le
fichier, le motif, et la règle attendue.

## Descente au FOKONTANY réparée : la colonne `num_fkt` n'existe plus (journal 2026-09-17)

Correction du bug repéré pendant les travaux précédents. **Toute la descente au niveau
fokontany renvoyait 0 ménage**, en silence.

### La cause : le piège SQLite des identifiants entre guillemets

Le questionnaire de septembre 2026 a supprimé `num_fkt` de `den_menage` ; le code
fokontany à 8 chiffres est désormais porté par `fokontany` lui-même (avec un jeu de value
labels pour le libellé). `rapport_core` avait été rendu tolérant en septembre
(`_col_opt`, `numfkt = d.col("num_fkt") if "num_fkt" in d.varnames else d.col("fokontany")`),
mais **deux endroits lisaient encore `num_fkt` en dur** :

```
SELECT COUNT(*) FROM den_menage WHERE "num_fkt"   = 63050604   ->  0     (faux)
SELECT COUNT(*) FROM den_menage WHERE "fokontany" = 63050604   ->  5     (vrai)
```

En SQLite, `"num_fkt"` sur une colonne absente **ne lève rien** : l'identifiant entre
guillemets doubles est relu comme la **chaîne** `'num_fkt'`. Donc :
- dans un `WHERE`, la condition est **toujours fausse** → 0 ligne, sans erreur ;
- dans un `SELECT`, la colonne renvoie **la chaîne `'num_fkt'`** sur chaque ligne.

### Les deux endroits corrigés

| Fichier | Symptôme |
|---|---|
| `db_source.source_db(..., fkt=)` (les 2 branches : `den`, et `roster`/`diagnostics` via `interview__key`) | **toutes** les pages `/vue/<section>/fokontany/<code>` et la route héritée `/fokontany/<code>` : 0 ménage |
| `serveur_app.preparer()` (construction d'`ARBRE`) | `SELECT "num_fkt"` renvoyait la chaîne `'num_fkt'` → l'arbre du menu n'avait plus qu'**UN** fokontany par commune |

La règle est maintenant **écrite une seule fois**, dans `db_source` :
`COL_FKT_ANCIEN` / `COL_FKT_ACTUEL`, `colonne_code_fokontany(varnames)` (lit `num_fkt` s'il
existe, `fokontany` sinon — même règle que `rapport_core`) et `colonnes_table(conn, table)`
(colonnes d'une table lues dans `_schema`). Les **anciennes bases archivées** continuent donc
de fonctionner.

### Avant / après (base copiée, district 6305)

| | Avant | Après |
|---|---|---|
| Arbre du menu (log de démarrage) | 144 communes, **144** fokontany | 143 communes, **672** fokontany |
| `/vue/*/fokontany/63050605` (6 sections) | **0** ménage | **28** ménages |
| Route héritée `/fokontany/63050605` | 0 ménage | 28 ménages |

*(144 → 143 communes est normal : une commune sans code fokontany valide entrait quand même
dans l'arbre, puisque la chaîne `'num_fkt'` n'est jamais `None`.)*

### Vérifications (Firefox headless)

- `/vue/general/fokontany/63050605` : 28 ménages, 28 présents, taille **1,75** · écart-type
  **0,95** · 49 personnes, 3 segments, blocs « par agent » affichés.
- `/vue/multi/fokontany/63050605` : **1 cas — segment 1, EQ1_BTKS_0225, 2 fois** — soit
  exactement ce que montrait la vue commune. Les deux niveaux concordent enfin.
- `/vue/agent/fokontany/63050605` : 3 onglets agents, fiche individuelle peuplée.
- `/vue/zone/fokontany/63050605` : 3 segments.
- **Non-régression** district/commune : les 8 sections au district, 3 au niveau commune, et
  l'export Excel — tous 200, tailles inchangées. (`/vue/gps` en 303 au district est le
  comportement voulu pour un rôle « communes » : la carte GPS exige un fokontany.)
- **Audit** : plus aucune lecture en dur de `num_fkt` hors d'un exemple de docstring
  (`lire_dta.py`). Toutes les autres colonnes lues en dur figurent dans `_REQUIS` (validé
  par `source_db`) ou passent par `_col_opt`.

⚠️ **Au déploiement** : les pages fokontany vides ont pu être **mises en cache** en mémoire
(`serveur_app._CACHE`, cache du dashboard MPA). Le redémarrage du service les vide — c'est
justement ce que fait la procédure de mise à jour.

**À retenir** : sur SQLite, une colonne disparue ne casse jamais une requête — elle devient
une chaîne. Quand une variable sort du questionnaire, chercher **toutes** ses occurrences,
`WHERE` compris, et faire passer la règle par **une seule fonction** (ici
`db_source.colonne_code_fokontany`) plutôt que de la réécrire à chaque appel.

## Journal de bord : retirer / ajouter des pièces jointes à la MODIFICATION (journal 2026-09-17)

**Demande** : pouvoir, en modifiant une entrée de journal, **supprimer** des photos/fichiers
déjà envoyés et en **ajouter** d'autres.

Le code semblait déjà tout faire (page de modification avec un bouton 🗑 par pièce jointe,
champs « Ajouter des photos / d'autres fichiers », route `POST /journal/fichier/supprimer`,
stockage disque + base). En curl, tout marchait. **Dans un navigateur, rien ne marchait.**

### La cause : un `<form>` DANS un `<form>`

La page de modification rendait, pour chaque pièce jointe, un petit formulaire de
suppression… **à l'intérieur** du formulaire de modification. Or un `<form>` imbriqué est
interdit en HTML : le parseur du navigateur **supprime la balise imbriquée**, et son
`</form>` orphelin **ferme le formulaire principal**. Vérifié dans Firefox, sur la page
telle qu'elle était servie :

| Élément | Formulaire auquel le NAVIGATEUR le rattache |
|---|---|
| 1er bouton 🗑 | **`/journal/modifier`** (au lieu de la suppression !) |
| `Ajouter des photos` (`#images`) | **(hors de tout formulaire)** |
| `Ajouter d'autres fichiers` (`#fichiers`) | **(hors de tout formulaire)** |
| bouton `Enregistrer les modifications` | **(hors de tout formulaire)** |

Conséquences réelles, dès qu'une entrée avait **au moins une** pièce jointe : cliquer 🗑 sur
la première **enregistrait l'entrée** au lieu de supprimer la pièce ; et les champs d'ajout
comme le bouton Enregistrer, sortis du formulaire, étaient **inertes**. D'où « on ne peut
ni supprimer ni ajouter ».

### La correction : des CASES À COCHER, une seule validation

Plus aucun formulaire imbriqué (`page_journal_modifier`). Chaque pièce jointe existante est
une **carte** : aperçu (vraie **vignette** pour les images affichables, lien 📎 sinon), nom +
taille, et une case **« Retirer »** (`name="supprimer"`, valeur = id de la pièce) qui vit
**dans** le formulaire de modification. Une seule validation applique donc, ensemble :
texte + date, **retraits**, **ajouts**.

`_journal_modifier_post` applique les **retraits d'abord**, les **ajouts ensuite** — on peut
ainsi remplacer une photo par une autre du même nom en une seule fois. Deux aides partagées
nouvelles : `_effacer_fichier_journal` (effacement disque, avec la garde anti-traversée) et
`_supprimer_fichiers_journal` (base + disque, en ne touchant que les pièces de l'auteur via
`journal.supprimer_fichier`). La route `POST /journal/fichier/supprimer` est **conservée**
(point d'entrée unitaire, et pages restées ouvertes) et réutilise ces aides.

Le retour indique ce qui a été fait : `/journal?maj=1&sup=N&add=M` →
« Votre entrée de journal a bien été modifiée — 2 pièce(s) jointe(s) ajoutée(s), 1 retirée(s). »

### Vérifications (Firefox headless + geckodriver, base copiée)

- **Structure** : la page ne porte plus qu'**UN** formulaire ; textarea, `#images`,
  `#fichiers`, bouton Enregistrer et **toutes** les cases « Retirer » y sont rattachés.
- **Scénario complet** dans le navigateur : cocher une pièce, joindre 1 image + 1 fichier,
  changer le texte, enregistrer → `?maj=1&sup=1&add=2`, message correct, et en base : texte
  à jour, pièce retirée **de la base ET du disque**, 2 nouvelles pièces rangées dans
  `Rapport_Images/<district>/<login>/` et `Rapport_Fichier/<district>/<login>/`.
- **Entrée sans pièce jointe** : pas de bloc « Pièces jointes actuelles », un seul
  formulaire, champs d'ajout et bouton présents.
- **Propriété** : un AUTRE Superviseur qui poste le même formulaire (même id d'entrée, même
  id de pièce) est refusé — `obtenir_activite` renvoie None, rien n'est touché.

> **Deux pièges d'outillage** rencontrés (à ne pas confondre avec des bugs de l'appli) :
> (1) le Firefox en **snap** n'a **pas** accès aux dossiers **cachés** de `$HOME` ; un
> `<input type=file>` pointé sur `~/.dossier/x.png` se soumet avec un corps **vide**
> (`Content-Length: 0`) — déplacer les fichiers de test dans un dossier non caché ;
> (2) les sessions expirent après **30 min d'inactivité** (`INACTIVITE_MAX`), ce qui, entre
> deux commandes espacées, fait retomber les tests sur `/login`.

**À retenir** : un formulaire imbriqué ne provoque aucune erreur visible — le navigateur
« répare » le HTML en silence, et ce sont des champs entiers qui cessent d'être envoyés.
Quand une page combine une action principale et des actions par élément, passer par des
**cases à cocher du formulaire principal** plutôt que par des mini-formulaires.

## Manuels par poste remis à jour (journal 2026-09-17)

Les manuels intégrés (`/manuel`, un guide PAR RÔLE : `manuel.py` + `manuel_roles.py` +
`manuel_ui.py`) décrivaient encore l'application d'avant les travaux du jour, et il leur
manquait une fonctionnalité majeure : le **journal de bord**, qui n'était documenté nulle
part alors que six postes s'en servent tous les jours.

### Corrections de ce qui était FAUX

| Où | Avant | Maintenant |
|---|---|---|
| Section « Qualité » du tableau de bord | « carnet, scan, complétude » | présence, **taille des ménages (moyenne + écart-type)**, électrification, statut des segments |
| Section « Vue générale » | « couverture, qualité, indicateurs clés » | + **taille moyenne des ménages et écart-type** |
| Section « Segments multiples » | « codes de segment répétés dans un même fokontany » | **un même agent** qui répète le même code dans un même fokontany ; deux agents ≠ doublon |
| Export Excel | « **quatre** feuilles » | **cinq** feuilles, avec le contenu réel de « Rapport global » (structure des ménages) et la nouvelle « Écart déclaration-serveur » ; encadré expliquant le retrait des colonnes carnet e-Fokontany |
| Accueil Traitement | « trois activités » | les **cinq** cartes réelles (dont Équipe technique et journal) |

### Ce qui a été AJOUTÉ

- **Journal de bord — section pour TOUS les postes.** Deux versions, choisies
  automatiquement : *écriture* (écrire l'entrée du jour, joindre photos/fichiers, et
  **modifier** : cocher « Retirer » sur une pièce jointe, en ajouter d'autres, tout
  s'appliquant en une seule validation) et *lecture* (filtres, suivi de complétude,
  rapport de mission). Le cas de l'**Admin** est traité à part : son espace n'a pas de
  cartes, le manuel donne donc les **adresses** (`/journal`, `/journal/suivi`,
  `/rapport-mission`) et précise que le menu « Journal » de sa barre est un AUTRE outil
  (le journal des *connexions*).
- **Superviseur Technique — « Saisir les déclarations des agents »** : à quoi ça sert
  (la feuille Écart du rapport), choix Dénombrement / VAD, **maquette du modèle Excel**
  (colonne 1 = code agent, colonnes 2..n = dates, cellule vide ≠ zéro), le fait que seul
  le **code** est demandé (le nom vient de la base des agents), le téléversement et la
  lecture du bilan, le refus **ligne par ligne** hors périmètre. Le poste gagne aussi une
  section « Votre poste en bref » (il n'en avait pas).
- **Traitement — préchargement** : la feuille `e_fokontany` vide **est normale** ;
  comment **ne pas renvoyer deux fois les mêmes ménages** ; et surtout la **règle
  d'acceptation** d'un fichier d'exclusion (valide dès qu'une feuille porte
  `interview_keyden` ; `e_fokontany` peut être vide ou absente ; un fichier réduit à
  `nouveau` est juste), les deux seuls cas de refus, et le fait que « Rien de nouveau à
  exporter » **n'est pas** un refus de format.
- **Traitement — base CE/Agents** : cette base est la **seule source** des noms d'agents
  dans toute l'application (rapports, export, déclarations des Superviseurs).

### Une duplication supprimée au passage

Les groupes de rôles du journal étaient **codés en dur dans `serveur_app`**. Le manuel en
avait besoin pour choisir la bonne version de sa section : plutôt que de recopier la liste
(deux sources de vérité qui divergent au premier changement), ils ont été **déplacés dans
`utilisateurs.py`** — la source de vérité documentée des groupes de rôles (§Groupes de
rôles) — sous les noms `ROLES_JOURNAL_ECRITURE`, `ROLES_JOURNAL_LECTURE` et
`ROLES_DECLARATION`. `serveur_app` les réexporte sous ses noms privés habituels, sans rien
changer à son code. `manuel_roles.sections_role()` ajoute la section journal **en un seul
endroit**, d'après ces groupes : aucun poste ne peut l'oublier, et un rôle déplacé d'un
groupe à l'autre bascule automatiquement sur la bonne version.

### Vérifications

- Les **9 manuels** se rendent sans erreur, sans balise HTML échappée visible et sans
  identifiant de section en double.
- Parcours réel (Firefox headless) : connexion en **Superviseur Technique** puis en
  **Traitement** → `/manuel` → sommaire et titres numérotés corrects, nouvelles sections
  présentes et à leur place.
- Captures d'écran relues : la maquette Excel des déclarations (avec sa cellule vide
  illustrant « ce n'est pas un zéro »), les encadrés du préchargement, et les étapes de
  modification du journal s'affichent comme prévu.
- ⚠️ `manuel_roles.py` évite désormais une f-string contenant une concaténation implicite
  (syntaxe **PEP 701**, Python ≥ 3.12 uniquement) : le libellé est préparé avant. La
  production tourne en 3.12, mais le fichier reste lisible par une version antérieure.

## Coefficient de variation de la taille des ménages (journal 2026-09-17)

Ajout d'un troisième indicateur de taille, au **tableau de bord** ET dans le **rapport
Excel** : le **coefficient de variation** (CV) = écart-type ÷ moyenne, **en pourcentage**.

**Pourquoi il complète l'écart-type** : l'écart-type est une dispersion ABSOLUE, donc
incomparable d'une zone à l'autre — 1,4 personne d'écart-type ne se lit pas pareil sur une
taille moyenne de 2,3 ou de 5,0. Le CV, lui, est **relatif** : il se compare directement
entre communes et fokontany. Exemple réel (commune ANKAZOMANGA OUEST) : le CV des fokontany
va de **19,2 %** à **70,6 %**, et celui de la commune entière monte à **79,5 %** — plus haut
que chacun de ses fokontany, parce que leurs tailles MOYENNES diffèrent aussi.

### Où

| | Avant | Maintenant |
|---|---|---|
| KPI « Taille moyenne des ménages » (vue générale, 3 niveaux) | `écart-type 1,37 · 615 personnes` | `écart-type 1,37 · **CV 57,8 %** · 615 personnes` |
| Page Qualité, sous-titre de l'histogramme | `Moyenne 2,37 · écart-type 1,37 · 260 ménage(s)` | + `· **CV 57,8 %**` |
| Export Excel, feuille « Rapport global », tableaux 2 ET 3 | 6 colonnes | **7** : nouvelle colonne *Coefficient de variation de la taille (%)* |

### Comment

`rapport_core._taille_stats` renvoie un champ de plus, `tailleCv`, et le gabarit
(`tailleStats()`) en fait autant — **calculé sur la moyenne et l'écart-type NON arrondis**,
puis arrondi à 1 décimale par `_r1()` / `r1()`, deux nouvelles fonctions jumelles
(`_js_round(x*10)/10` ↔ `Math.round(x*10)/10`) qui garantissent le MÊME nombre des deux
côtés. L'oracle JS des tests (`tests/test_agrege_oracle.js`) a été mis à jour en même temps,
et `test_agrege.py` affiche désormais le CV dans sa ligne de contrôle.

Côté export, `_ligne_struct()` garde la moyenne et l'écart-type non arrondis dans des
variables avant de calculer le CV (sinon on diviserait deux valeurs déjà arrondies).
Le CV vaut `—` quand il n'est pas calculable : aucun ménage, ou **un seul** (pas
d'écart-type, donc pas de CV).

### Vérifications (base copiée)

| Périmètre | Python (agrégat serveur) | JS (navigateur, données brutes) |
|---|---|---|
| District 6305 | moy 2,29 · σ 1,32 · **CV 57,8 %** | — |
| 5 communes du superviseur | moy 2,37 · σ 1,37 · **CV 57,8 %** | idem à l'écran |
| Commune 630506 | moy 2,18 · σ 1,09 · **CV 49,8 %** | **identique** |
| Fokontany 63050605 | moy 1,75 · σ 0,95 · **CV 54,3 %** | **identique** |

Contrôle indépendant sur le district : `100 × 1,3223 / 2,2891 = 57,7654 %` → **57,8**.
L'export Excel obtenu **par la route réelle** affiche la même valeur que le KPI pour le
même périmètre (2,37 / 1,37 / 57,8). Manuels mis à jour (sections « Vue générale »,
« Qualité » et export), avec une astuce expliquant comment lire un CV.

## VISITE À DOMICILE (VAD) : données, ingestion et tableau de bord (journal 2026-09-17/18)

La 2ᵉ phase du RSU entre enfin dans l'application. Jusqu'ici, « Visite à domicile »
n'était qu'une carte grisée « bientôt disponible ». Elle a désormais **ses tables, son
ingestion et son tableau de bord complet**.

### 1. Ce que contiennent les données (analyse de l'export)

Export Survey Solutions du questionnaire **RSUe_v26-0-0**, dossier
`rsuefkt_25_rN_pil_1_STATA_All_20260912T1036Z` (12/09/2026) :

| Fichier | Contenu | Volume |
|---|---|---|
| `rsuefkt_25_rN_pil.dta` | 1 ligne = 1 **ménage** interviewé | 336 lignes × 176 col. |
| `RMen.dta` | 1 ligne = 1 **membre** du ménage | 779 lignes × 111 col. |
| `interview__diagnostics.dta` | agent, statut, durée, erreurs | 336 lignes |

Points décisifs, trouvés à l'analyse et qui commandent tout le reste :

* **La géographie est portée par `CQ6..CQ9`** (région / district / commune /
  fokontany) — codes numériques AVEC value labels. Les colonnes
  `region`/`district`/`commune`/`fokontany` du questionnaire sont des valeurs
  **préchargées au format texte**, valant `##N/A##` dans 44 % des cas : inutilisables.
* **`##N/A##` est le marqueur « non renseigné »** de Survey Solutions. Traité comme
  vide PARTOUT (`vad_db.txt()`), sinon il remonterait comme une modalité de réponse.
* La durée d'interview s'écrit **`JJ.HH:MM:SS`** (`00.00:54:01`), pas `HH:MM:SS`.
* Les **29 biens** (AP1..AP4, colonnes `AP<q>__<code>` en 0/1) n'ont PAS de value
  labels : leurs libellés ont été extraits de l'aperçu français du questionnaire.
* Le questionnaire est **en malgache** : les modalités restent telles qu'elles ont été
  collectées, seuls les intitulés de section sont traduits.

### 2. Les tables (`vad_db.py`)

```
vad_menage       interview__key PK        1 ligne = 1 ménage interviewé
vad_membre       (interview__key, RMen__id)  1 ligne = 1 membre
vad_diagnostics  interview__key PK        agent, statut, durée, erreurs
```

Clés étrangères **déclarées** (`db_source.FK_ZONES` / `FK_AGENT`) :
`vad_menage.CQ6..CQ9a → zones`, `vad_diagnostics.responsible → agent(login_ae)` — la
MÊME table `agent` que le dénombrement, donc les noms saisis par l'Expert Traitement
servent aussi à la VAD. Tout code agent VAD inconnu y est auto-créé
(`vad_db.synchroniser_agents`), comme pour le dénombrement.

La transcription réutilise **`maj_db.maj_table`** : même mécanique d'UPSERT que le
dénombrement (ajoute / met à jour / ne supprime rien). Vérifié idempotent
(2ᵉ passage : `=1451` inchangées).

### 3. Ingestion — espace EXPERT SURVEY

⚠️ *Correction du 2026-09-18* : l'ingestion avait d'abord été placée dans l'espace
**Traitement** ; l'utilisateur a corrigé — c'est l'**Expert survey** qui téléverse et
transcrit les données VAD, comme il le fait déjà pour le dénombrement. Le Traitement
garde le **tableau de bord** VAD, pas l'ingestion.

La carte « Transcription — Visite à domicile » de `/transcription` n'est donc plus
« en cours de conception » : elle ouvre `/transcription/vad`, en **deux temps** comme
l'ingestion du dénombrement — on téléverse le DOSSIER d'export (écrit dans un
temporaire, validé, puis rangé dans `DATA_serveur/VAD/<district>/`) et on lit
l'**aperçu** ; on transcrit seulement ensuite (`/transcription/vad/transcrire`). Les
ménages d'un **autre district** sont écartés et signalés — refus seulement si rien ne
concerne le district. Le fichier des ménages est reconnu par son nom OU **par ses
colonnes**, pour qu'un export d'une nouvelle version du questionnaire passe quand même.

> **Mise à jour du 2026-09-18** : l'Expert survey a finalement accès aux **DEUX
> tableaux de bord** (dénombrement ET VAD), à la demande de l'utilisateur — il
> transcrit les données des deux phases, il doit pouvoir vérifier ce qu'elles donnent.
> Concrètement : il rejoint `_ROLES_VAD`, et la garde qui l'enfermait dans
> `/transcription` (redirection de `/choix`, `/suivi`, `/vue/…`, `/menu`,
> `/fokontany`, et du POST de sélection) a été **retirée**. Son périmètre reste borné
> à SON district par `perimetre()` / `_perimetre_vue` : une commune d'un autre
> district lui renvoie bien **403**. Sa page d'accueil (`/transcription`, devenue
> « Espace Expert survey ») porte désormais 4 cartes : les 2 transcriptions et les
> 2 tableaux de bord.

### 4. Le tableau de bord VAD (`vad_core.py` + `vad_web.py`)

Routes `/vad/<section>`, ouvertes à **Coordonnateur Nationale, Coordonnateur
régionale, Traitement, Superviseur Technique, Expert survey, Comités Techniques et
Admin** (`_ROLES_VAD` — tous les rôles qui atteignent la fenêtre de sélection, soit tous
sauf les deux Responsables Logistiques ; maj 2026-09-19),
chacun **borné à son périmètre par `perimetre()`** — la même source de vérité que le dénombrement.
Ce périmètre est **resserré sur le district CHOISI** dans la fenêtre de sélection
(`_vad_perimetre(u, district)`, cf. § « Choix du district » daté 2026-09-19).
Multi-pages : le serveur n'envoie que les agrégats de la section demandée.

| Section | Ce qu'elle montre |
|---|---|
| **Vue globale** | avancement quotidien + cumul, **couverture vs ménages dénombrés**, durée d'entretien, statut, consentements, type de ménage, récap par commune et par fokontany |
| **Démographie** | **pyramide des âges**, rapport de masculinité (global et par groupe), ratio de dépendance, chef de ménage (% femmes, âge), lien au chef, état matrimonial, niveau scolaire + taux de scolarisation des 6-17 ans, activité, **papiers d'identité** (acte, CIN, NUI) |
| **Habitation** | murs, sol, toit, éclairage, statut d'occupation, pièces, **personnes par pièce et surpeuplement** |
| **Biens & actifs** | taux de possession des **29 biens**, par famille, + nombre moyen de biens |
| **Eau & assainissement** | source d'eau, toilettes, ordures, part « améliorée », **défécation à l'air libre** |
| **Carte GPS** | un point par ménage (Leaflet), taux de capture, précision |
| **Listing d'erreurs** | **14 anomalies** typées `bloquant` / `à vérifier`, ménage par ménage, avec agent et date |
| **Par agent** | ménages, membres, jours, ménages/jour, taille moyenne, durée moyenne, anomalies |

### 5. Ce que le tableau de bord a immédiatement révélé (district 5201, 318 ménages)

- **Le préchargement du questionnaire est défectueux** : 170 ménages portent un code
  de dénombrement, mais **19 codes distincts seulement**. Le rapprochement
  VAD ↔ dénombrement est donc inexploitable en l'état — un bandeau le dit sur la Vue
  globale. C'est le constat le plus important de cette mise en service.
- Couverture **17,2 %** (318 visités sur 1 850 dénombrés) ; durée moyenne **55,8 min**.
- Démographie plausible : masculinité 113,9 ; âge moyen 25,8 ans ; dépendance 29,4 % ;
  **18,7 % de ménages dirigés par une femme** ; scolarisation des 6-17 ans **97 %**.
- Qualité : **125 GPS imprécis (> 100 m)**, 5 sans GPS, 5 ménages sans chef,
  10 entretiens réalisés malgré un refus de consentement RSU.

### 6. Deux défauts de MA conception, corrigés grâce aux données

1. **Performance** : `_lire()` appelait `col_decoded()` DANS la boucle sur les
   ménages. `DbDataset.col_decoded()` refait une requête sur `_value_labels` à chaque
   appel — les 7 352 libellés de fokontany étaient relus 336 fois et la page mettait
   des **minutes**. Colonnes hissées hors de la boucle → **0,10 s**.
2. **Règles d'anomalie fausses** : « aucun lien avec le dénombrement » était compté
   pour 148 ménages… qui sont des `Tokantrano vaovao` (nouveaux ménages), pour
   lesquels aucun lien n'est attendu. Et 170 ménages étaient déclarés « visités
   plusieurs fois » alors que le vrai diagnostic est le préchargement défectueux.
   Corrigé : le lien n'est exigé que pour un ménage annoncé « liste e-Fokontany », et
   au-delà de 3 répétitions d'un même code on parle de préchargement, pas de doublon.
   Anomalies bloquantes : **333 → 15**.

Également corrigé après relecture des captures : le rapport de masculinité par âge
(1 femme pour 17 hommes = 1 700 %, qui écrasait l'échelle) n'est plus calculé sous
5 femmes dans le groupe et est plafonné à 300 à l'affichage ; les tableaux de membres
comptent des « Personnes » et non des « Ménages ».

### 7. Vérifications

- Transcription : 336 + 779 + 336 lignes, **idempotente** ; FK en place.
- Parcours HTTP réel : **les 5 rôles × les 8 sections = 200** ; périmètres
  respectés — National 336 ménages, Traitement et Expert survey 318 (leur district),
  Superviseur 284 (ses 4 communes). L'Expert accède aussi au dashboard du
  dénombrement (`/vue/*` et `/export/rapport.xlsx` en 200) et reste bloqué **403**
  sur une commune hors de son district. Les **Logistiques** restent, eux, fermés aux
  deux tableaux de bord (303 vers `/logistique`).
- Téléversement du dossier réel (12 fichiers) via le formulaire, **en Expert
  survey** : aperçu correct, **18 ménages hors district écartés**, transcription OK,
  dossier rangé dans `DATA_serveur/VAD/5201/`. `/traitement/vad` renvoie bien **404**
  (la route a disparu de l'espace Traitement).
- Rendu Firefox headless des 8 sections : 13 graphiques dessinés, aucune erreur JS.
- Manuels mis à jour : section **« Le tableau de bord VAD »** pour les 4 rôles, et
  section **« Transcrire les données de la Visite à domicile »** pour l'**Expert
  survey** (vérifié : elle n'apparaît plus dans le manuel du Traitement).

### 8. CE QUI RESTE À FAIRE

**À décider / valider avec les statisticiens du RSU**
- [ ] **Valider les classements « améliorés »** eau (`EAU_AMELIOREE`) et
      assainissement (`SANIT_AMELIOREE`) : ce sont des propositions JMP (OMS/UNICEF)
      écrites par défaut, pas une règle du projet.
- [ ] Valider les **seuils** retenus : surpeuplement > 3 personnes/pièce, GPS
      imprécis > 100 m, effectif minimum de 5 femmes pour un rapport de masculinité.
- [ ] Décider du **score de bien-être (proxy means test)** à partir des 29 biens :
      la section affiche les taux bruts, pas encore de score.

**Côté données / terrain**
- [ ] **Réparer le préchargement** du questionnaire RSUe : sans `interview_keyden`
      fiable, impossible de dire quel ménage dénombré a été visité, ni de calculer
      une vraie couverture ménage par ménage (aujourd'hui elle est globale).
- [ ] Traiter les **14 membres sans sexe** et les **6 sans âge** (ils sortent de la
      pyramide).

**Développements restants**
- [ ] **Export Excel du VAD** (équivalent de `/export/rapport.xlsx`) : aucune
      exportation n'existe encore pour la VAD.
- [x] ~~**Descente commune → fokontany** dans le tableau de bord VAD (aujourd'hui le
      périmètre est celui du rôle, sans drill-down) ; la barre latérale a la place
      réservée.~~ **FAIT (2026-09-20)** pour la section **Carte GPS** : sous-menu
      Commune → Fokontany dans la barre latérale (cf. section datée).
- [ ] **Déclarations VAD** : elles sont saisies (table `declaration_agent`,
      type `VAD`) mais la feuille « Écart déclaration-serveur » ne compare que le
      dénombrement — maintenant que les données VAD existent, l'écart VAD peut être
      calculé.
- [ ] **Mise en cache** des agrégats VAD (aujourd'hui recalculés à chaque page ;
      0,1 s sur 336 ménages, à revoir à 100 000).
- [ ] Sections envisageables ensuite : **santé / handicap** (M12, M16a/b, M18),
      **emploi détaillé** (M19a..M19j), **programmes sociaux** (Inti, IdBenef),
      **suivi par chef d'équipe** (comme le dénombrement).
- [ ] La carte GPS charge **Leaflet depuis unpkg** (comme le rapport de
      dénombrement) : à embarquer dans `assets/` pour un fonctionnement hors-ligne.

# ═══════════════════════════════════════════════════════════════════════════
# BILAN DE LA SESSION DU 2026-09-17 / 18
# ═══════════════════════════════════════════════════════════════════════════

Synthèse des douze chantiers menés d'affilée, des **leçons** qu'ils ont laissées, et
de **ce qui reste**. Chaque chantier a sa section datée plus haut : on ne répète ici
que l'essentiel et les renvois.

## A. Ce que nous avons fait

| # | Chantier | Résultat |
|---|---|---|
| 1 | **Déclarations des agents** | Table `declaration_agent` + module `declarations.py`. Le **Superviseur Technique** saisit, depuis un modèle Excel pré-rempli (colonne 1 = code agent, colonnes 2..n = dates), le nombre de ménages que ses agents déclarent avoir dénombrés (DEN) ou interviewés (VAD). UPSERT, refus **ligne par ligne** hors périmètre. |
| 2 | **Carnet e-Fokontany retiré** | Supprimé de l'**export Excel** (tableaux 2 et 3) ET du **tableau de bord** (KPI, 2 graphiques, colonnes de tableaux, export CSV). La question n'existe plus au questionnaire depuis septembre 2026 : elle n'affichait que des « n/d ». |
| 3 | **Structure des ménages** | À la place : personnes dénombrées, **taille moyenne**, **écart-type**, **coefficient de variation**, % de ménages présents. Dans l'export, dans le KPI de la vue générale et sur la page Qualité. |
| 4 | **Écart déclaration-serveur** | 5ᵉ feuille de l'export Excel : par chef d'équipe, agent et date, le **déclaré** face au **reçu au serveur**, l'écart et l'écart en %. |
| 5 | **Segment multiple redéfini** | Clé `(fokontany, code, **agent**)` : deux agents différents sur le même code ne sont plus un doublon. Sur le district 6305, **47 faux cas** disparaissent et les vrais se scindent par agent. |
| 6 | **Préchargement** | Règle d'acceptation du fichier d'exclusion rendue **explicite** (valide dès qu'une feuille porte `interview_keyden` ; `e_fokontany` peut être vide ou absente) ; refus motivés, nommant le fichier ; message « rien de nouveau » qui dit qu'il a **lu** le fichier. |
| 7 | **Bug `num_fkt` corrigé** | Toute la descente au **fokontany** renvoyait 0 ménage, en silence, et l'arbre du menu n'avait qu'un fokontany par commune (**144 → 672**). Règle centralisée dans `db_source.colonne_code_fokontany`. |
| 8 | **Pièces jointes du journal** | On peut enfin **retirer** et **ajouter** photos/fichiers en modifiant une entrée : un `<form>` imbriqué faisait supprimer par le navigateur le formulaire de suppression ET sortait les champs d'ajout du formulaire principal. |
| 9 | **Manuels par poste** | Remis à jour et complétés : section **Journal de bord** pour TOUS les postes, **Déclaration des agents** (Superviseur), **Transcription VAD** (Expert survey), **Tableau de bord VAD** (5 rôles). Groupes de rôles déplacés dans `utilisateurs.py`. |
| 10 | **Ménage du dépôt** | `BASE_BRUTE/` supprimé (6 Mo, inutilisé) ; export Drive de la VAD rapatrié dans `rsu-web/`. |
| 11 | **VISITE À DOMICILE** | Analyse des `.dta`, **3 tables** (`vad_menage`, `vad_membre`, `vad_diagnostics`), **ingestion par l'Expert survey** (`/transcription/vad`), **tableau de bord en 8 sections** (`vad_core.py` + `vad_web.py`). |
| 12 | **Expert survey ouvert** | Il ingère les deux phases ET voit **les deux tableaux de bord**, bornés à son district. La garde qui l'enfermait dans `/transcription` a sauté. |

**Nouveaux fichiers** : `declarations.py`, `vad_db.py`, `vad_core.py`, `vad_web.py`.
**Modifiés** : `serveur_app.py`, `export_rapport.py`, `rapport_core.py`, `db_source.py`,
`prechargement.py`, `equipes.py`, `transcription.py`, `utilisateurs.py`,
`manuel_roles.py`, `templeteHtml/template_{head,tail}.html`, `tests/*`, `.gitignore`.

## B. Leçons apprises

**Sur SQLite et les questionnaires qui changent**
1. **Une colonne disparue ne casse pas une requête** : `WHERE "num_fkt" = 63050604`
   sur une colonne absente relit l'identifiant comme la **chaîne** `'num_fkt'` — la
   condition est toujours fausse, le `SELECT` renvoie le nom de la colonne, et
   **rien n'est signalé**. Quand une variable sort du questionnaire, chercher
   **toutes** ses occurrences, `WHERE` compris, et faire passer la règle par **une
   seule fonction**.
2. **Ne pas laisser un « n/d » s'installer.** Afficher `n/d` pendant six mois occupe
   la place d'un indicateur utile. Au bout d'un moment, il faut remplacer la colonne,
   pas la garder par nostalgie.
3. **`##N/A##` est une valeur, pas un vide.** Le marqueur de Survey Solutions doit
   être neutralisé à la lecture (`vad_db.txt()`), sinon il ressort comme une modalité
   de réponse — 148 ménages « de la région ##N/A## ».

**Sur le HTML et le navigateur**
4. **Un `<form>` dans un `<form>` est « réparé » en silence** : le parseur supprime
   la balise imbriquée et son `</form>` orphelin ferme le formulaire principal — des
   champs entiers cessent d'être envoyés, sans la moindre erreur. `curl` ne le
   reproduit pas : **il faut un vrai navigateur**.
5. Quand une page combine une action principale et des actions par élément, passer
   par des **cases à cocher du formulaire principal**, pas par des mini-formulaires.

**Sur la performance**
6. **Ne jamais appeler une fonction qui requête dans une boucle.**
   `DbDataset.col_decoded()` refait une requête sur `_value_labels` à chaque appel :
   appelée dans la boucle sur les ménages, elle relisait 7 352 libellés 336 fois et
   la page mettait des minutes. Colonnes hissées hors de la boucle → **0,10 s**.

**Sur les règles métier**
7. **Une règle d'anomalie doit être confrontée à la sémantique des données.**
   « Aucun lien avec le dénombrement » visait 148 ménages… qui sont des *nouveaux
   ménages*, pour lesquels aucun lien n'est attendu. Anomalies bloquantes :
   **333 → 15**. Une alerte qui se déclenche partout ne se déclenche nulle part.
8. **Distinguer deux diagnostics qui se ressemblent** : un code de dénombrement
   répété 2 fois = double visite ; répété 40 fois = préchargement défectueux.
9. **Ne pas présenter une classification dérivée comme une vérité** : les seuils
   « eau/assainissement améliorés » (JMP) sont signalés comme **propositions à
   valider**, dans le code, dans l'interface et dans le manuel.

**Sur la méthode**
10. **« L'application refuse mon fichier » → reproduire d'abord.** Le code acceptait
    déjà tout ce qu'il fallait : le défaut était dans le **message**, qui laissait
    deviner la cause. Un refus doit nommer le fichier, le motif et la règle attendue.
11. **Une liste de rôles recopiée dans deux modules est une bombe à retardement** :
    déplacée dans `utilisateurs.py`, source de vérité unique.
12. **Deux implémentations jumelles (Python / JS) se tiennent par leurs arrondis** :
    `_r1`/`_r2` ↔ `r1`/`r2`, et un test d'équivalence. Node.js étant absent du
    serveur, l'équivalence a été vérifiée **dans un vrai navigateur** — même
    résultat, autre chemin.

**Pièges d'outillage (à ne pas confondre avec des bugs de l'appli)**
13. Firefox en **snap** n'a pas accès aux dossiers **cachés** de `$HOME` : un
    `<input type=file>` pointé dessus se soumet avec un corps **vide**.
14. Les sessions expirent après **30 min d'inactivité** — entre deux commandes
    espacées, les tests retombent sur `/login`.
15. `geckodriver` se pilote en 30 lignes d'`urllib` (WebDriver = JSON sur HTTP),
    sans installer Selenium. Les `const` de premier niveau d'un `<script>` ne sont
    **pas** sur `window` ; les `function`, si.

## C. Ce qui reste à faire

### C.1 — À DÉCIDER par l'utilisateur (bloquant pour la suite)

- [ ] ⚠️ **Données VAD chargées dans la base de PRODUCTION par erreur.** Un test
      d'ingestion du 2026-09-18 à 04:47 (journalisé sous `TR_FENERIVEEST_01`,
      « Transcription VAD ») a écrit dans `rsu_local.sqlite` **au lieu de la copie de
      test** : la production contient `vad_menage` (318), `vad_membre` (737),
      `vad_diagnostics` (318) pour le district 5201, et le dossier
      `DATA_serveur/VAD/5201/`. Ce sont les **vraies** données fournies, et la
      transcription est idempotente — mais **ce n'était pas une décision de
      l'utilisateur**. À trancher : les **garder** (rien à faire) ou les
      **retirer** (`DROP TABLE vad_menage, vad_membre, vad_diagnostics` +
      suppression du dossier), avant que l'Expert survey ne fasse sa propre
      transcription. *(La table `declaration_agent` de production est, elle, VIDE :
      les déclarations de test sont bien restées dans la copie.)*
- [ ] **Valider les classements « améliorés »** eau (`EAU_AMELIOREE`) et
      assainissement (`SANIT_AMELIOREE`) — propositions JMP (OMS/UNICEF).
- [ ] **Valider les seuils** : surpeuplement > 3 personnes/pièce, GPS imprécis
      > 100 m, 5 femmes minimum pour un rapport de masculinité, 3 répétitions pour
      distinguer double visite et préchargement défectueux.
- [ ] Décider du **score de bien-être (proxy means test)** à partir des 29 biens.

### C.2 — Mise en production

- [ ] **Vérifier ce que sert le service en ligne.** Au 2026-09-18, `rsu-web` a
      redémarré à 05:34 et sert déjà les nouvelles routes (`/rsu-web/vad/general`,
      `/rsu-web/declaration` répondent) : le travail est **en ligne sans étape de
      déploiement explicite**. Refaire un passage propre (sauvegarde de la base,
      redémarrage, vérifications) et contrôler que les pages fokontany ne sont plus
      en cache.
- [ ] **Rien n'est commité** : `git add` / `commit` / `push` des 4 nouveaux modules
      et des 12 fichiers modifiés (le dépôt est public : les `.dta` sont ignorés,
      mais le sous-dossier `Questionnaire/` de l'export VAD, ~9,5 Mo, serait
      versionné — décider).
- [ ] **Copies à resynchroniser avec le projet exe** (`..\RSU_Rapport\`, absent de ce
      serveur) : `rapport_core.py`, `templeteHtml/`, `assets/` ont changé (carnet
      retiré, taille des ménages, CV, segment multiple).

### C.3 — Côté données / terrain

- [ ] **Réparer le préchargement du questionnaire RSUe** : 170 ménages portent un
      code de dénombrement pour **19 codes distincts** seulement. Sans
      `interview_keyden` fiable, pas de rapprochement VAD ↔ dénombrement ménage par
      ménage, donc pas de vraie couverture.
- [ ] Traiter les **14 membres sans sexe** et **6 sans âge** (ils sortent de la
      pyramide) ; les **125 GPS imprécis** (> 100 m) et **5 sans GPS**.
- [ ] Renseigner la base **Chefs d'Équipe / Agents** : beaucoup d'agents s'affichent
      encore par leur code faute de nom.

### C.4 — Développements restants

- [ ] **Export Excel du VAD** (équivalent de `/export/rapport.xlsx`) — rien n'existe.
- [x] ~~**Descente commune → fokontany** dans le tableau de bord VAD (la barre latérale
      a la place réservée).~~ **FAIT (2026-09-20)** sur la section Carte GPS ; les
      autres sections restent au périmètre du rôle.
- [ ] **Écart déclaration-serveur pour le VAD** : les déclarations VAD sont saisies
      (`declaration_agent`, type `VAD`) et les données VAD existent désormais — le
      calcul peut être branché.
- [ ] **Mise en cache** des agrégats VAD (0,1 s sur 336 ménages ; à revoir à 100 000).
- [ ] **Leaflet embarqué dans `assets/`** (la carte VAD et le rapport de dénombrement
      le chargent depuis unpkg : pas de carte hors-ligne).
- [ ] **`tests/test_agrege.py` est inexécutable ici** (Node.js absent du serveur) :
      installer Node, ou porter l'oracle en Python.
- [ ] Sections VAD envisageables : **santé / handicap** (M12, M16a/b, M18),
      **emploi détaillé** (M19a..M19j), **programmes sociaux** (Inti, IdBenef),
      **suivi par chef d'équipe**.
- [ ] Reste de la feuille de route §6 : **PostgreSQL** effectif (`RSU_DB_URL`),
      **FastAPI**, **HTTPS** (certificat Let's Encrypt au lieu du snakeoil),
      **changer le compte d'amorçage**.


# ═══════════════════════════════════════════════════════════════════════════
# RGPH-3 2018, LISTINGS D'ERREURS, TESTS DE QUALITÉ (session 2026-09-18)
# ═══════════════════════════════════════════════════════════════════════════

Trois chantiers enchaînés : brancher le **recensement RGPH-3 2018** comme référence
du tableau de bord, transcrire le **dofile d'erreurs de saisie** de l'INSTAT, et
ouvrir une section **Test de qualité** par agent.

## A. Ce que nous avons fait

| # | Chantier | Résultat |
|---|---|---|
| 1 | **Données RGPH-3 2018** | Deux fichiers SPSS INSTAT (échantillon au 10 %) déposés dans `rsu-web/` : `INSTAT_BD_SPSS_MENAGES_10pc` (608 235 ménages × 67 var.) et `..._RESIDENTS_10pc` (2 568 303 individus × 124 var.), 648 Mo. Les deux se joignent sur `IDMEN` avec **intégrité référentielle parfaite**. |
| 2 | **Table de passage géographique** | `rgph3/` : chaîne reproductible qui apparie les **1 727 communes** RGPH-3 aux **1 704** du référentiel RSU **par les libellés**. 100 % appariées, 0 collision. Livrable auditable : `table_passage_commune_RGPH3_2018_vers_RSU.csv`. |
| 3 | **Base recodée** | `rgph3_2018.sqlite` (1 Go) puis intégration dans `rsu_local.sqlite` : `rgph_menage`, `rgph_individu`, `rgph_passage_commune`. Chaque ligne porte `cp_rsu`/`cr_rsu`/`cd_rsu`/`cc_rsu`. **0 orphelin**, 1 704/1 704 communes et 120/120 districts joints. |
| 4 | **Agrégats** | `rgph_commune` (1 704 × 28 indicateurs de privation), `rgph_pyramide` (4 080 lignes), `comp_taille_menage` (1 824) et `comp_pyramide` (4 080) pour la comparaison RGPH ↔ RSU. Puis `rgph_age_commune` (240 990) et `rgph_men_commune` (1 704) pour la performance. **Les 9 tables sont en base.** |
| 5 | **Comparaison RGPH ↔ RSU** | Page `/vad/demographie` : pyramide des âges et rapport de masculinité **côte à côte**, et les 6 KPI portent leur référence RGPH du même périmètre. Vue globale : taille de ménage RGPH à côté de celle des ménages enregistrés ; tableau par commune : colonne « Taille RGPH 2018 ». |
| 6 | **Listings d'erreurs de saisie** | Transcription du dofile `do_listing_d_erreur_20_districts_08102025.do` en **deux sections** : `err_menage` (15 contrôles) et `err_individu` (11). Une **colonne par contrôle**, la cellule portant le message de correction — la forme même de l'export Excel du dofile. L'ancienne section « Listing d'erreurs » est supprimée. |
| 7 | **Chef d'équipe** | `charger_ce_vad.py` → table `vad_ce` (336 interviews, 125 CE), depuis `interview__actions` filtré sur `action == 0`, comme le dofile. Colonne et filtre CE dans les deux listings. |
| 8 | **Test de qualité** | Nouveau module `vad_qualite.py` et section `/vad/qualite`. Sélection **Commune → CE → AE**, puis les tests du document technique RSU dans **sa mise en page** (titre numéroté, principe, formule, encadré de résultat, encadré de seuils). **Niveau 1 livré** (6 indicateurs de la section 3). |

**Nouveaux fichiers** : `vad_qualite.py`, `charger_ce_vad.py`, `integrer_rgph_complet.py`,
`integrer_agregats_rgph.py`, `comparaison_rgph_rsu.py`, `rgph3/` (9 scripts + README),
`table_passage_commune_RGPH3_2018_vers_RSU.csv`, `rgph_commune.csv`, `rgph_pyramide.csv`,
`RSU_Tests_qualite_donnees_agents_v1.0.docx`, `do_listing_d_erreur_*.do`.
**Modifiés** : `vad_core.py`, `vad_web.py`, `serveur_app.py`, `.gitignore`.

**Dépendances** : `pandas` et `pyreadstat` ne sont **pas** dans le venv — nécessaires
seulement pour rejouer `rgph3/`. `numpy` y est ; `scipy` non, d'où les lois (normale,
χ²) implémentées dans `vad_qualite.py` et vérifiées contre les tables.

## B. Leçons apprises

**Sur les référentiels géographiques**
1. **Deux nomenclatures peuvent partager les codes et désigner autre chose.** Le code
   région 21 vaut HAUTE MATSIATRA au RGPH-3 (22 régions, pré-2021) et **DIANA** dans
   le référentiel RSU (23 régions). Une jointure sur `code_region` passe sans erreur
   et rend des résultats **silencieusement faux**. Apparier par **libellés**, jamais
   par codes, entre deux millésimes.
2. **Un taux d'appariement de 100 % doit rendre méfiant, pas satisfait.** Il a fallu
   une mesure **indépendante** (ménages RGPH ×10 contre `commune.nombreMenage`) pour
   voir que la fusion urbaine avait écrasé Toamasina I, où le référentiel a bien
   5 arrondissements. Pearson est passé de 0,9275 à **0,9989** après correction.
3. **Attention à la validation circulaire.** Ce contrôle par `nombreMenage` est
   partiellement circulaire : ces estimations proviennent elles-mêmes d'un appariement
   de noms comparable. Il établit que les deux tables désignent les mêmes communes,
   pas qu'elles sont justes dans l'absolu.
4. **Chercher l'appariement déjà fait avant d'en construire un.** La colonne
   `source_appariement` de `MENAGES_PAR_COMMUNE_2025.xlsx` contenait déjà le travail
   (`exact`, `flou`, `inclusion`, `arrondissement`, `agregation_ville`…). Les deux
   appariements concordent à **100 %** — mais l'un des deux était en trop.
5. **Ne jamais inventer un code.** Une première table d'exceptions a été écrite avec
   des codes RGPH **fabriqués de mémoire** : des communes RSU se sont retrouvées
   consommées par de mauvaises clés, cassant des appariements corrects. Tout code
   doit être **lu dans les données** avant usage.

**Sur les données manquantes et les pièges silencieux**
6. **`NaN == NaN` est faux.** Comparer deux colonnes avec `==` compte chaque paire de
   manquants comme un écart : 22 % de « divergence » annoncés entre deux fichiers…
   qui étaient identiques. Passer par un **tableau croisé** avant de conclure.
7. **Une colonne présente mais vide est pire qu'absente.** `M6_valid` existe et est
   `NULL` sur les 1 650 lignes : les trois contrôles CIN du dofile rendaient « 0
   erreur », ce qui se lit « tout va bien ». Vérifier qu'une dépendance est
   **renseignée**, pas seulement présente, et sinon retirer la règle de la liste.
8. **Deux colonnes du même export peuvent se contredire.** Dans `vad_menage`,
   `district` dit 6201 (Amboasary Sud) là où `CQ7` dit 5201 (Fenerive Est), sur
   170 ménages. Le tableau de bord fait autorité sur `CQ7` : une analyse bâtie sur
   `district` attribuait des ménages au mauvais district.
9. **Un encodage déclaré peut être faux.** `..._RESIDENTS_10pc.sav` fait échouer
   readstat sur l'encodage qu'il annonce ; il faut forcer `encoding="LATIN1"`.
10. **Pas de pondération = pas de niveau publiable.** Les fichiers INSTAT ne
    contiennent aucun poids de sondage. Le **classement relatif** des communes reste
    valide — c'est ce qui sert au ciblage — mais les niveaux (38,1 % d'électricité)
    peuvent s'écarter des publications officielles.

**Sur les statistiques appliquées**
11. **Comparer une unité au cumul de son ensemble vide le test de son sens.** Le
    document compare un agent à la **distribution entre agents** (« médiane de
    l'équipe : 9 ménages/jour »), pas au total de l'équipe. Confondre les deux
    revenait à comparer 2 ménages/jour à 83.
12. **Un résultat obtenu à un échelon supérieur n'est pas un verdict individuel.**
    Quand un test remonte agent → CE → commune faute d'effectif, l'alerte porte sur
    la commune. L'afficher comme une alerte d'agent accuse quelqu'un à tort : d'où
    l'encadré bleu et la mention explicite.
13. **Un seuil d'effectif vaut mieux qu'un chiffre.** Sur l'export pilote, un agent a
    1 à 7 ménages là où ces tests en supposent des dizaines. Chaque test déclare son
    `n_min` et dit « effectif insuffisant » plutôt que de rendre du bruit.

**Sur l'outillage**
14. **`pkill -f <motif>` tue le shell appelant** quand le motif figure dans sa propre
    ligne de commande (exit 144). Tuer par PID.
15. **Un `sed` de nettoyage peut emporter un import.** Supprimer les lignes
    `sys.path.insert(...)` a décapité trois scripts dont l'import était sur la même
    ligne. Vérifier la **syntaxe de chaque fichier** après une réécriture en masse.
16. **Chrome ne partage pas le `localhost` du serveur** : impossible de tester le
    JavaScript des pages depuis cette session. Les vérifications sont **statiques**
    (correspondance identifiants DOM / sélecteurs / clés de données), pas dynamiques.
17. **Calculer pour tout le monde ne passe pas à l'échelle.** Les tests des 371 agents
    faisaient une page de **751 Ko** (≈ 4 Mo une fois les 7 niveaux là). La sélection
    passe par l'URL (`?commune=&ce=&ae=`) et le serveur ne calcule que l'agent
    affiché : **53 Ko**.
18. **Pré-agréger, ou balayer 2,5 millions de lignes à chaque page.** `_sec_rgph`
    prenait 3,7 s en périmètre national, pour **toutes** les sections. Deux tables
    additives (`rgph_age_commune`, `rgph_men_commune`) ramènent à 0,24 s, et 0,00 s
    par district. Prévoir un **repli** sur les microdonnées si elles manquent.

## C. Ce qui reste à faire

### C.1 — Tests de qualité : les 7 niveaux sont livrés

Le module `vad_qualite.py` est structuré pour les accueillir : une fonction par
niveau, une ligne dans `NIVEAUX`, et chaque test déclare son `n_min` et sa façon de
compter. L'escalade agent → CE → commune est générique et s'applique sans code
supplémentaire.

- [x] **Niveau 2 — cohérence démographique** : Whipple, Myers, indice combiné
      âge-sexe (ONU), khi-deux du chiffre terminal, ICC / ANOVA à effet-agent,
      Kolmogorov-Smirnov, rapport de masculinité, cohérence du lien de parenté (M7).
- [x] **Niveau 3 — cycle de vie** : les 13 règles du répertoire (§5.1), le score
      composite d'incohérence, le test de Kruskal-Wallis.
- [x] **Niveau 4 — logement** : khi-deux agent × modalité, entropie de Shannon,
      Jaccard / Bray-Curtis, Grubbs sur H2, corrélation polychorique.
- [x] **Niveau 5 — biens** : échelle de Guttman et coefficient de reproductibilité,
      biais |Z| par item AP.
- [x] **Niveau 6 — fraude** : distance de Mahalanobis, loi de Benford, régression de
      la durée de passation, DBSCAN sur les GPS.
- [x] **Niveau 7 — non-réponse** : test MCAR de Little, matrice de missingness,
      taux de couverture ZD.
- [ ] **Chapitre 10 — score composite de risque** et **tableau de synthèse de tous
      les agents**, classés par risque. Sans cette vue, il faut ouvrir les 371 agents
      un par un. À livrer en dernier : le score combine des indicateurs des niveaux
      2 à 7.

### C.2 — À décider par l'utilisateur

- [ ] **Arbitrer `ANONTSIBE EST` → `ANONTSIBE CENTRE`** (district Manja), seul
      appariement de commune incertain : les orientations diffèrent. Repérable dans
      le CSV par sa méthode `flou-large/district`.
- [ ] **Choisir les indicateurs de `rgph_commune`** : les 28 actuels sont un choix
      par défaut (habitat, eau, assainissement, équipements, capital humain). Définir
      aussi les seuils de privation si un référentiel de ciblage existe.
- [ ] **Poids de sondage RGPH-3** : les demander à l'INSTAT si les niveaux doivent
      correspondre aux publications.
- [ ] **461 majeurs sans numéro CIN** sont détectables, mais le dofile les masque via
      `M6_valid`. Décider si l'on s'écarte du dofile pour les faire remonter.

### C.3 — Données et intégration

- [ ] **Effectifs par agent trop faibles** : 305 agents pour 546 ménages, médiane
      **1 ménage/agent**. Aucun test du document n'est interprétable au niveau agent
      avant la collecte de production. Les gardes d'effectif sont en place.
- [ ] **`interview__actions` hors ingestion** : `charger_ce_vad.py` est un chargeur
      séparé. Intégrer le CE à `vad_db` pour que chaque nouvel export l'alimente.
- [ ] **Variables absentes de l'export VAD**, qui désactivent 11 contrôles du
      dofile : `SR01`→`SR09` (sources de revenu), `PT01`→`PT03`, `typeculture`,
      `SR10` (agriculture), `Milieu`. Elles se réactiveront seules si un export les
      contient.
- [ ] **Encodage de `nom_cm`** : mojibake sur les accents (`Jean No\xef\xbf\xbdl`),
      hérité de l'import `.dta`. Touche aussi d'autres pages.

### C.4 — Dépôt et exploitation

- [ ] **Rien n'est commité.** Le `.gitignore` a été complété (`*.sav`, sorties
      intermédiaires de `rgph3/`) ; `rgph3_2018.sqlite` est couvert par `*.sqlite`.
      Restent à versionner : les scripts, le README, la table de passage et les CSV
      d'agrégats (608 Ko au total).
- [ ] **Serveur non redémarré** : le processus du port 8000 (`serveur_app.py`) tourne
      sur l'ancien code. Aucune des modifications de cette session n'est visible en
      ligne.
- [ ] **`rsu_local.sqlite` est passée de 38 Mo à 1,10 Go** après intégration des
      microdonnées RGPH. Sauvegarde préalable : `rsu_local.sqlite.avant_rgph.bak`
      (instantané de 10 h 22, **sans** les lignes opérationnelles ajoutées depuis —
      ne pas restaurer tel quel). Réversible par `DROP TABLE rgph_*` + `VACUUM`.
- [ ] **`/vad/erreurs` renvoie 404** depuis la suppression de l'ancienne section.
      Ajouter une redirection si des signets existent.
- [ ] **Tester le JavaScript dans un vrai navigateur** : filtres des listings,
      cascade Commune → CE → AE, tableaux à colonnes figées. Jamais exécuté.

---

## TABLEAU DE BORD VAD : « à côté du dénombrement », AVEC LE CHOIX DU DISTRICT (journal 2026-09-19)

**Demande** : *activer la fonctionnalité pour revoir le dashboard de VAD qui est à côté
du dénombrement, avec le choix du district, pour tous ceux qui ont accès à cette fenêtre.*

« Cette fenêtre » = la **page de sélection** (`page_selection`) : zone géographique
(Province → Région → District) puis **type de suivi**, où la vignette **Visite à domicile**
est **à côté** de **Dénombrement**. Jusqu'ici cette vignette menait à un cul-de-sac : le
vrai tableau de bord VAD existait depuis le 2026-09-18 (`/vad/<section>`), mais il n'était
atteignable que par les **cartes des espaces de rôle** — la sélection, elle, affichait
encore l'écran « pas encore disponible ».

### Ce qui change (`serveur_app.py`)

| Avant | Après |
|---|---|
| `/suivi` avec `suivi=vad` → `page_vad_indisponible` | **redirige vers `/vad/general`** |
| `/vue/...` avec `suivi=vad` → « pas encore disponible » | redirige vers `/vad/general` (ces vues SONT le dénombrement) |
| `/export/rapport.xlsx` avec `suivi=vad` → « pas encore disponible » | redirige vers `/vad/general` (pas encore d'export VAD) |
| `_ROLES_VAD` = 5 rôles | **+ Comités Techniques** = tous les rôles de la fenêtre de sélection |
| Périmètre VAD = tout le périmètre du rôle | **resserré sur le district choisi** |
| `page_vad_indisponible` (~60 lignes) | **SUPPRIMÉE** (plus aucun appelant) |

### Choix du district

Le tableau de bord VAD se lit **district par district**, comme celui du dénombrement.
Le district retenu vit dans **`sess["vad_district"]`**, volontairement **à part de
`sess["selection"]`** (qui sert au dénombrement) pour que les deux suivis ne se
marchent pas dessus :

- **écriture** : `/suivi` en mode VAD y recopie `sel["code_district"]` avant de rediriger.
  Cela couvre les **deux** chemins d'accès — Coordonnateurs (`<menu>?op=vad` → sélection
  du district → POST `/suivi`) et **Superviseur Technique** (district FIXE, `?op=vad`
  prépare la sélection et passe par `/suivi`) ;
- **lecture** : `_vad_perimetre(u, district)` ne retient le code que s'il est **autorisé**
  (`districts is None or code in districts`) — `perimetre()` reste la **source de vérité
  de l'accès**, jamais l'URL. Un district hors affectation est **ignoré ET non mémorisé** ;
- **navigation** : conservé d'une section à l'autre, puisqu'il est en session et non dans
  l'URL. `?district=<code>` le change, **`?district=tout`** revient à tout le périmètre ;
- **barre latérale** (`_vad_liens_zone`, passé en `liens_zone` à `vad_web.page`) : liens
  **« ⇄ Changer de district »** (vers `<menu>?op=vad`, ou `/choix` pour un rôle sans menu)
  et **« 🌐 Tout mon périmètre »**. Rien pour un rôle **mono-district** (Traitement,
  Expert survey, Superviseur) : il n'a aucun choix à faire.

### Manuels (`manuel_roles.py`)

- `_ROLES_VAD` et `_PERIMETRE_VAD` alignés sur `serveur_app` (+ Comités Techniques :
  « vous voyez le district que vous avez choisi, parmi vos districts »).
- Section « Choisir la zone et le type de suivi » : la Visite à domicile n'est plus
  « en cours de conception », elle **ouvre le tableau de bord VAD du district choisi**.
- `_LIB_OP["vad"]` devient **« Tableau de bord (visite à domicile) »**, symétrique du
  dénombrement, sur la page de sélection à opération imposée.

### Testé (HTTP réel, sur une COPIE de la base, port 8099)

Copie de `rsu_local.sqlite` dans le dossier de travail temporaire, 4 comptes de test
créés **dans la copie** — la production n'a **pas** été touchée. Données VAD présentes
pour les districts **1106 (228)**, **3306 (276)**, **3307 (70)**, **5201 (318)**.

| Rôle testé | Parcours | Résultat |
|---|---|---|
| **Comités Techniques** (1106 + 3306) | `/choix` (vignettes den/vad) → district 1106 + VAD | `/vad/general` **200**, « District ANTANANARIVO AVARADRANO », **228 ménages** |
| | `/vad/demographie` | district **conservé** |
| | `?district=tout` | **504 ménages** (1106 + 3306) |
| | `?district=5201` (hors affectation) | **ignoré**, reste à 504 |
| | `/vue/general` en mode VAD | → `/vad/general` |
| **Coordonnateur Nationale** | `/coordonat?op=vad` → sélection → district 3306 | « District VOHIBATO », **276 ménages** ; `?district=tout` → **892** |
| **Superviseur Technique** (3 communes de 5201) | `/suptech?op=vad` (district fixe) | **26 ménages** (ses communes), **pas** de « Changer de district » |
| **Traitement** (5201) | `/vad/general` | **318 ménages**, pas de « Changer de district » |

Manuels vérifiés par appel direct : `sections_role("Comités Techniques")` →
`['selection', 'dashboard', 'vad', 'journal']`, phrase de périmètre VAD présente, et plus
aucun « en cours de conception » dans la section de sélection.

⚠️ **Redémarrage du service requis** pour que ce code soit servi en ligne (le processus
du port 8000 tourne sur l'ancien code).

### Reste à faire (inchangé par cette session)

- [ ] **Export Excel du VAD** : `/export/rapport.xlsx` en mode VAD **redirige** vers le
      dashboard, faute d'export VAD. À écrire (équivalent de `export_rapport.py`).
- [x] ~~**Descente commune → fokontany** dans le tableau de bord VAD : le choix du district
      est maintenant en place, mais les niveaux inférieurs ne sont pas navigables.~~
      **FAIT (2026-09-20)** sur la Carte GPS (sous-menu de la barre latérale).
- [ ] **`/vad/erreurs` renvoie 404** (ancienne section supprimée) : redirection à ajouter.

### Correctif du même jour : l'ADMIN était exclu (2026-09-19)

**Symptôme signalé** : depuis `https://rse.instat.mg/rsu-web/choix`, un **Admin** qui
choisit un district et **Visite à domicile** ne voyait pas le dashboard s'ouvrir.

**Cause** : `_ROLES_VAD` avait été ouvert à « tous les rôles de la fenêtre de sélection »
mais **sans l'Admin**, au motif qu'il a son propre espace. C'était faux : l'Admin n'est ni
dans `_MENU_CHEMINS`, ni logistique, ni Expert survey, ni Traitement — `/choix` lui rend
donc `page_selection` **avec les vignettes den/vad**, exactement la fenêtre visée. Le POST
`/suivi` mémorisait bien son district et redirigeait vers `/vad/general`, mais `_vad_get`
le trouvait hors `_ROLES_VAD` et le **renvoyait à `/admin`** : de son point de vue, « le
dashboard ne s'ouvre pas ». Le dénombrement, lui, marchait (aucune garde de rôle sur
`/vue`), d'où l'asymétrie.

**Correctif** : `Admin` ajouté à `_ROLES_VAD` (`serveur_app.py` **et** `manuel_roles.py`,
+ sa phrase de périmètre : *« vous voyez le district que vous avez choisi »*). Son
`perimetre()` est `(None, None)` — aucune restriction — donc le resserrement sur le
district choisi fonctionne tel quel, et « ⇄ Changer de district » pointe vers **`/choix`**
(il n'a pas de menu d'opération). **Seuls les deux Responsables Logistiques** restent hors
`_ROLES_VAD`, vérifié par assertion sur `utilisateurs.RESPONSABILITES`.

**Testé** (HTTP réel, copie de la base, port 8099, compte Admin de test) : login →
`/admin` ; `/choix` rend bien les deux vignettes ; les **4 districts porteurs de données
VAD** ouvrent le dashboard avec le bon effectif — **5201 : 318**, **1106 : 228**,
**3306 : 276**, **3307 : 70** ; libellé « District FENERIVE EST » pour 5201 ; les sections
*démographie, habitation, GPS, par agent, qualité* conservent le district ;
`?district=tout` → **892** (toute la zone) ; le **dénombrement** de l'Admin répond
toujours `/vue/general`. Manuel Admin : `['poste', 'tableau', 'utilisateurs', 'vad',
'journal']`.

### Correctif du même jour : la carte VAD des menus contournait le choix du district (2026-09-19)

**Demande** : *pour la visualisation du dashboard VAD par le Coordonnateur régionale, on
devrait passer par le choix du district comme pour le dashboard de dénombrement
(`/coordoreg?op=den`).*

**Cause** : dans `page_menu_operation`, la carte « Tableau de bord — Visite à domicile »
avait été câblée en **lien direct `/vad/general`** lors de la mise en service du 2026-09-18
(« le périmètre est déduit du rôle »). Le Coordonnateur régionale atterrissait donc sur
**ses 3-4 districts agrégés d'un coup**, alors que la carte « Dénombrement » pointe, elle,
sur `<menu>?op=den` → sélection du district → `/suivi`. Deux chemins asymétriques pour
deux tableaux de bord jumeaux.

**Correctif** : la carte VAD pointe maintenant sur **`<menu>?op=vad`**, comme sa jumelle
(`href_vad`), avec la même mention **« Choisir le district → »** et une description alignée
sur `d_lieu` (`d_vad`). Aucune logique de routage à toucher : `_menu_operation_get` gérait
déjà `op=vad` — district à choisir pour les Coordonnateurs, traversée directe pour un rôle
à district FIXE (Superviseur). Les espaces **Traitement** et **Expert survey** gardent leur
lien direct `/vad/general` : mono-district, ils n'ont aucun district à choisir.

**Testé** (HTTP réel, copie de la base, port 8099, compte régional de test sur les districts
**1101, 1106, 5201, 5206** — ceux d'un COORDOREG réel) :

- `/coordoreg` : carte VAD → `?op=vad`, **plus aucun `/vad/general`** en dur dans le menu,
  mention « Choisir le district » sur les deux tableaux de bord ;
- `?op=den` **et** `?op=vad` rendent la **même** page de sélection, `<select>` restreint à
  ses **4 districts** — vérifié sur le `<select>` et non sur la page entière, car
  `ARBRE_GEO` (120 districts) y est injecté en JSON pour la cascade ;
- district **5201** + VAD → **318 ménages** (« District FENERIVE EST »), **1106** → **228** ;
- « ⇄ Changer de district » → `/coordoreg?op=vad` ; `?district=tout` → **546** (ses seuls
  districts porteurs de données) ;
- district **3306, hors ses affectations** → **400** avec l'opération conservée ;
- dénombrement inchangé (`/vue/general`).

**Non-régression** re-jouée sur les autres rôles : Admin (4 districts VAD, 892 au total),
Comités Techniques (228 / 504), Coord. Nationale (276 / 892), Superviseur (26, pas de lien
« changer »), Traitement (318, idem).

---

## TEST DE QUALITÉ : du choix d'un agent à la MATRICE CE × AE (journal 2026-09-19)

**Demande** : *on ne va pas choisir un agent. Afficher un tableau : 1ʳᵉ colonne le CE,
2ᵉ l'AE, puis les différents tests. Si le test est incalculable, « nd ». Des couleurs
différentes selon le résultat — rouge si mauvais/alertant, vert si pas d'anomalie, etc.*

**Avant** : `/vad/qualite` ouvrait une cascade Commune → CE → AE. Il fallait choisir un
agent pour que le serveur calcule ses 6 tests et déroule 6 fiches documentaires. Tant
qu'on n'avait choisi personne, la page ne disait rien — donc pour trouver l'agent à
problème, il fallait les ouvrir un par un (420 agents).

**Après** : la page ouvre directement un **tableau de tous les agents du périmètre**.

### Décisions prises avec l'utilisateur

| Question | Choix retenu |
|---|---|
| Agent sans effectif suffisant | **« nd » strict, niveau agent** — jamais la valeur du CE à sa place |
| Échelle de couleurs | **3 niveaux + gris** : rouge (alerte), orange (vigilance), vert (conforme), gris (nd) |
| Fiche détaillée existante | **conservée, au clic sur une ligne** |

### `vad_qualite.py`

- `resultat()` gagne `vigilance=` et expose **`gravite`** ∈ {`nd`, `ok`, `vigilance`,
  `alerte`}. `alerte` (booléen historique) est conservé : la fiche détaillée s'en sert.
- **`SEUILS_VIGILANCE`** / `VIGILANCE_PAR_TEST` : un palier intermédiaire par test, pris
  sur **la même statistique que l'alerte**, à mi-chemin —
  3.1 `z > 2` ou 1,5 × la médiane des pairs (alerte : `z > 3` ou 2 ×) ·
  3.2 sous le **1ᵉʳ quartile** (alerte : sous le 5ᵉ percentile) ·
  3.3 complétude **< 98 %** (alerte : < 95 %) ·
  3.4 moyenne **+ 1 σ** (alerte : + 2 σ) ·
  3.5 « Hafa » **> 10 %** (alerte : > 15 %) ·
  3.6 **|Z| > 1,96** (alerte : > 2,58).
  ⚠️ **Ces paliers ne viennent PAS de la documentation technique RSU** — seuls les seuils
  rouges en viennent. C'est écrit dans le code, sur la page et dans le manuel : ils
  alertent plus tôt, donc avec plus de faux positifs, et sont réglables d'un seul endroit.
- **`_echelon_agent()`** : un échelon UNIQUE, l'agent. C'est la différence de fond avec la
  fiche détaillée, qui garde l'escalade agent → CE → commune. Dans la matrice, si l'agent
  n'atteint pas `n_min`, `_escalade` ne trouve rien de plus large, `resultat()` marque
  `insuffisant` et la case vaut **nd**. Y mettre la valeur de son CE remplirait une équipe
  entière de verdicts identiques qui ne sont le verdict de personne. La **référence** de
  comparaison, elle, reste la commune : on compare bien l'agent à ses pairs.
- **`colonnes()`** dérive les colonnes en faisant tourner les niveaux sur un échelon VIDE :
  la liste des tests reste définie au seul endroit qui la connaît, le code des niveaux.
- `calculer()` renvoie en plus **`matrice`** = {colonnes, lignes, résumé} ; `resultat`
  (la fiche) ne change pas et reste calculé à la demande, car c'est lui qui pèse.

### `vad_web.py`

- `_p_qualite` a deux états : **sans** `?commune=&ce=&ae=` → la matrice ; **avec** → la
  fiche existante, précédée d'un « ← Retour au tableau ». Agent introuvable → matrice +
  avertissement, jamais une page vide.
- Tableau : en-tête figé en haut, **colonnes CE et AE figées à gauche** (sur 200 lignes et
  6 colonnes, sans cela on ne sait plus quelle ligne on lit), sous-titre de commune,
  effectif de l'agent, puis une case par test. Infobulle = conclusion + effectif ; pour un
  **nd**, « n = 2, minimum requis 10 » — on sait s'il manque 2 ménages ou 25.
- `_qa_test` (fiche) gagne l'état **orange « à surveiller »**.
- ⚠️ Piège rencontré : `gravite` vaut `"alerte"`/`"vigilance"` mais les classes CSS sont
  `.al`/`.vg` — la première version rendait `class="c alerte"`, sans style, et le tableau
  sortait **sans aucune couleur rouge** alors que le calcul en trouvait 7. Corrigé par une
  table de correspondance explicite dans `_qm_cellule`.
- **JS divisé** : la cascade (2,5 Ko, et l'arbre Commune→CE→AE envoyé au navigateur) est
  remplacée par un filtre texte + case « Alertes seulement » + clic sur la ligne. La
  section n'envoie **plus aucune donnée** au navigateur (`_data_section` → `{}`) ; le
  tableau reste lisible et cliquable sans JavaScript. CSS `.qa-sel` supprimé (mort).

### Testé (HTTP réel, copie de la base, port 8099, compte Traitement du district 5201)

- `/vad/qualite` rend le tableau **sans rien choisir** : **174 Ko en 0,4 s**, **168 lignes**,
  6 colonnes (3.1 → 3.6), colonne 1 = CE puis colonne 2 = AE, plus aucune trace de cascade ;
- les quatre états sont présents : **7 alertes, 2 à surveiller, 45 conformes, 954 nd** ;
- infobulle de nd au format attendu ; légende, filtre et « Alertes seulement » en place ;
- clic sur une ligne → fiche détaillée (45 Ko) avec retour ; agent inexistant → tableau +
  avertissement ; sections `general`, `demographie`, `agents` intactes.
- Coût du calcul mesuré hors HTTP : **0,15 s pour 168 agents** (5201), **0,22 s pour 203**
  (1106) — la crainte initiale (« plusieurs mégaoctets pour 371 agents ») ne valait que
  pour les fiches détaillées, pas pour une case valeur + couleur.

### Ce que ce tableau montre aujourd'hui, et pourquoi

**954 cases nd sur 1 008** au district 5201. Ce n'est pas un défaut du tableau :
**420 agents pour 892 ménages, médiane 1,5 ménage par agent** (maximum 13), alors que les
`n_min` vont de 5 à 30. L'escalade masquait ce fait en affichant des valeurs de commune ;
le tableau le rend visible. Les couleurs se rempliront avec les volumes de production.

Deuxième constat, visible dès la première colonne : **`vad_ce` ne couvre que le district
5201** (122 CE). Pour **1106, 3306 et 3307**, toute la colonne CE vaut « (CE inconnu) » —
c'est le chargeur séparé `charger_ce_vad.py`, déjà inscrit au reste à faire.

### Reste à faire

- [ ] **Intégrer le CE à `vad_db`** (`charger_ce_vad.py`) : sans lui, la 1ʳᵉ colonne du
      tableau est vide sur 3 districts sur 4.
- [ ] **Niveaux 2 à 7** du document (cohérence démographique, cycle de vie, logement,
      biens, fraude, complétude) : ils s'ajouteront comme **colonnes supplémentaires**
      sans toucher à la mise en page — `colonnes()` les découvrira seule.
- [ ] **Ajuster les paliers de vigilance** à l'usage, une fois de vrais volumes collectés :
      ils sont aujourd'hui posés a priori, pas calibrés sur des données de production.
- [ ] **Export Excel du tableau** : le même contenu, colorisé, pour le suivi hors ligne.

---

## NIVEAU 2 — cohérence démographique : 9 tests de plus dans la matrice (journal 2026-09-19)

**Demande** : *ajouter les tests de niveau 2 dans d'autres colonnes de la matrice. Tous
les tests du niveau 2.*

La matrice passe de **6 à 15 colonnes**. Les neuf tests de la **section 4** du document
(*Tests de cohérence démographique*) sont transcrits dans `vad_qualite.niveau2()` et
s'affichent comme les autres, avec les mêmes quatre états. L'en-tête du tableau gagne un
**premier rang groupant les colonnes par niveau** — sur 15 colonnes, sans lui on ne sait
plus ce qu'on lit. `colonnes()` les a découverts seule, comme prévu.

| Test | Ce qu'il mesure | Alerte (document) | Vigilance (ajoutée) | n min |
|---|---|---|---|---|
| **4.1** Whipple | attraction des âges vers 0 et 5, tranche 23–62 | ≥ 125 | ≥ 110 | 50 |
| **4.2** Myers | attraction vers **chacun** des dix chiffres terminaux | > 30 | > 20 | 80 |
| **4.3** IPAS (ONU) | précision âge-sexe d'une **zone** | > 40 | > 20 | **800** |
| **4.4** χ² chiffre terminal | préférence de chiffre due au hasard ou non (9 ddl) | p < 0,05 | p < 0,10 | 50 |
| **4.5** Effet-agent / ICC | `nbmembre` rempli au jugé ? (ANOVA + dispersion) | < 40 % des pairs | < 60 % | 10 |
| **4.6** Kolmogorov-Smirnov | distribution des âges vs référence | D > D(5 %) | D > D(10 %) | 30 |
| **4.7** Rapport de masculinité | hommes pour 100 femmes, 15–64 ans | hors [90 ; 108] | hors [95 ; 105] | 30 |
| **4.8.1** χ² sur M7 | codage du lien au chef de ménage | p < 0,05 | p < 0,10 | 30 |
| **4.8.2** M7 × M4 | enfant plus âgé que le chef, parent trop jeune | > 3 % | > 2 % | 20 |

### Outillage ajouté

- **Loi de Fisher** : `betainc_reg` (bêta incomplète régularisée, fraction continue de
  Lentz) + `f_sf`, pour la p-value du test F de l'ANOVA. Comme `chi2_sf`, sans scipy.
  ⚠️ Première version **récursive** : avec `a = b` et `x = 0,5`, les deux côtés du
  développement se renvoyaient l'un à l'autre → `RecursionError`. Le côté est désormais
  choisi **une seule fois**, avec une comparaison stricte.
- Contrôles contre les tables statistiques : χ²(0,05 ; 9) = 16,92 → **p = 0,0500** ;
  F(0,05 ; 5, 20) = 2,711 → **0,0500** ; F(0,05 ; 20, 20) = 2,124 → **0,0500** ;
  F(1 ; 10, 10) → **0,5000** exactement.

### Trois points où le document a dû être interprété

1. **4.8.2, règle sur le parent du chef.** Le document écrit qu'un parent (M7 = 4)
   « devrait avoir un âge supérieur à celui du chef de ménage **moins 12 ans** ». Pris au
   mot, cela autorise un parent **plus jeune de 11 ans que son enfant**. La règle codée est
   la lecture conservatrice symétrique de celle des enfants : **un parent doit avoir au
   moins 12 ans de plus que le chef**. ⚠️ **À faire arbitrer par les statisticiens du RSU.**
2. **4.3, définition de l'IPAS.** Le document définit les composantes « répartition par
   âge » comme l'écart absolu moyen des **différences successives** entre pourcentages de
   groupes quinquennaux. C'est cette définition qui est transcrite. L'indice classique des
   Nations Unies utilise, lui, des *age ratios* (2·P_g/(P_{g−1}+P_{g+1}) comparés à 100) :
   les deux variantes ne donnent pas les mêmes valeurs, et les seuils 20/40 du document
   valent pour la variante du document.
3. **4.8.1, χ² d'indépendance réduit à un agent.** Le document décrit un χ² M7 × agent sur
   tout le tableau agents × modalités. Une **ligne de matrice** ne peut pas porter une
   statistique de tableau : la colonne compare donc la répartition M7 de l'agent à celle de
   la référence (χ² d'ajustement) — c'est la contribution de sa colonne au χ² d'ensemble.
   Modalités d'effectif attendu < 5 regroupées (règle de Cochran).

Même logique pour **4.5** : l'ICC est une statistique de **groupe**. La colonne porte donc
le diagnostic **individuel** que décrit la figure 3 du document — la dispersion de l'agent
rapportée à celle de ses pairs, un agent qui invente produisant des valeurs anormalement
peu dispersées. L'ICC, le F et leur p-value du groupe sont rappelés dans le calcul.

### Une erreur d'arithmétique dans le document (4.6)

L'exemple K-S donne `D_critique(0,05) = 1,36 × √[(180+2400)/(180×2400)] ≈ 1,36 × 0,0806
≈ 0,110`. Or √(2580/432 000) = **0,0773**, pas 0,0806 (0,0806² = 0,006496 au lieu de
0,005972) : la valeur critique est **0,1051**. La conclusion de l'exemple ne change pas
(D observé 0,114 dépasse les deux), mais le code applique la formule, pas le nombre imprimé.

### Le plancher de l'IPAS relevé à 800 — mesuré, pas supposé

Fixé d'abord à 200, l'indice a été calculé sur la commune la plus fournie (FENERIVE VILLE,
251 ménages, **560 individus**) : **IPAS = 474**, pour une grille qui s'arrête à
« > 40 = douteux ». Avec 16 groupes quinquennaux × 2 sexes, les cases tombent à quelques
unités et le rapport de masculinité par groupe part dans tous les sens. Ce n'était pas un
diagnostic, c'était du bruit — d'où **`n_min` = 800**, et une colonne qui restera « nd »
jusqu'aux volumes de production. Le document le disait : cet indice se lit au niveau de la
**zone**, pas de l'agent.

### Testé

**Contre les exemples chiffrés du document** : Whipple agent B (96/300) → **160,0** ✓ ·
Myers, pourcentages de l'exemple → **18,6** ✓ · χ² = 58,4 à 9 ddl → p ≈ 0 ✓ ·
ICC (CM_inter 3,85 / CM_intra 0,78 / n₀ 40) → **0,0896** contre 0,090 annoncé ✓ ·
F = 4,94 (7 ; 312) → p < 0,001 ✓.

**Sur données réelles**, à l'échelon où les effectifs suffisent (commune FENERIVE VILLE,
251 ménages) : Whipple **167** (« grossières » → alerte), Myers **24,7** (vigilance),
χ² terminal **197** (alerte), rapport de masculinité **110,2** (alerte), K-S **0,01** (ok),
effet-agent **143 %** des pairs (ok), χ² M7 **1,85** (ok), M7 × M4 **0,68 %** (ok).
👉 **Constat de fond : les âges de cette commune sont fortement arrondis** — trois tests
indépendants le disent. C'est exactement ce que le niveau 2 devait détecter.

**Sur un jeu synthétique** (4 agents corrects de 60 ménages + 1 agent qui estime : âges
arrondis à 5, `nbmembre` toujours égal à 3, enfants plus âgés que le chef, aucune femme) —
l'agent fautif ressort **rouge sur 4.1 (500), 4.2 (80), 4.4 (889), 4.5 (0 % de dispersion),
4.6 (D = 0,23), 4.7 et 4.8.2 (10 %)**, les agents corrects restant verts.

**HTTP réel** (copie de la base, port 8099, Traitement du district 5201) : 15 colonnes dans
l'ordre attendu, en-tête groupé 6 + 9, **15 cases par ligne**, page **296 Ko en 0,6 s** pour
**168 agents × 15 tests = 2 520 cases**, fiche détaillée déroulant les deux niveaux, et les
sections `general`, `demographie`, `agents` intactes.

### Détails d'implémentation notables

- **Cas « aucune femme »** (4.7) : le rapport n'est pas définissable. Le classer « nd »
  l'aurait caché derrière un « effectif insuffisant » alors que c'est l'anomalie la plus
  grave du test. La case est donc **rouge et vide**, l'infobulle disant « aucune femme
  déclarée sur N adultes ».
- **Poids de la page** : les cases « nd » ne transportent plus leur conclusion (toujours la
  même phrase, reconstruite à l'affichage) — 2 466 cases × ~90 caractères économisés, soit
  **285 Ko au lieu de ~500**.

### Reste à faire

- [ ] **Arbitrer la règle 4.8.2 sur le parent du chef** (cf. ci-dessus) avec les
      statisticiens du RSU.
- [ ] **Trancher la variante de l'IPAS** : celle du document ou celle des Nations Unies.
- [ ] **Niveaux 3 à 7** + score composite (sections 5 à 10) : ils s'ajouteront de la même
      façon, en colonnes, sans toucher à la mise en page.
- [ ] Les seuils de **vigilance** restent posés a priori ; à recalibrer sur des volumes de
      production.

---

### Correctif : le nombre affiché n'expliquait pas la couleur (2026-09-19)

**Question posée** : *pourquoi le test de non-réponse est-il en % ?*

**Réponse** : parce qu'il mesure un TAUX — la part des questions du module emploi où
l'agent a coché « Tsy mahalala ». Le % est la grandeur actionnable ; un Z de 6,09 ne dit
rien à un superviseur. **Mais la couleur, elle, vient du |Z|** comparé à la référence de
la COMMUNE de l'agent, pas du %. D'où une colonne illisible, constatée sur le district
5201 :

| agent | affiché | réf. de sa commune | Z | couleur |
|---|---|---|---|---|
| EQ1_FNRVE_0149 | 0,0 % | 8,5 % | −1,81 | **vert** |
| EQ1_FNRVE_0071 | 0,0 % | 11,3 % | −2,14 | **orange** |
| EQ1_FNRVE_0215 | 0,0 % | 33,3 % | −3,67 | **rouge** |
| EQ1_FNRVE_0143 | 13,3 % | 11,0 % | 0,48 | **vert** |
| EQ1_FNRVE_0279 | 15,6 % | 3,8 % | 2,73 | **rouge** |

Le même « 0,0 % » en vert, en orange et en rouge ; 13,3 % vert et 15,6 % rouge.

**Deux défauts corrigés** :

1. **Phrase fausse dans un cas sur deux.** Le test du document est **bilatéral** (`|Z|`),
   donc un agent qui répond « ne sait pas » beaucoup **moins** souvent que ses pairs est
   signalé lui aussi — et c'est justifié : il n'a peut-être jamais proposé la modalité et
   a rempli une réponse à la place. Mais la conclusion écrivait « éludée significativement
   **plus** souvent » dans tous les cas : faux pour un agent à 0 % face à une référence à
   33 %. La conclusion dit désormais **dans quel sens** va l'écart, et le seuil affiché
   précise que le test est bilatéral.
2. **Repère absent.** `resultat()` gagne un champ **`repere`** : une phrase courte qui rend
   la couleur explicable, ajoutée à l'infobulle de la case. Renseigné pour **les quinze
   tests** — référence et Z pour 3.6, médiane des pairs et z pour 3.1, percentiles pour
   3.2, seuil des pairs pour 3.4, taux de référence pour 3.5 et 4.8.2, grille ONU pour
   4.1/4.2/4.3, p-value pour 4.4 et 4.8.1, dispersion des pairs et ICC du groupe pour 4.5,
   D critique pour 4.6, plage plausible et effectifs par sexe pour 4.7. Les cases « nd »
   n'en portent pas (elles gardent « n = x, minimum requis y »).

Le problème était **général, pas propre à 3.6** : pour 3.1, 3.2, 3.4, 3.6 et 4.6, la valeur
affichée est une mesure et le seuil est relatif à la référence — le nombre seul ne pouvait
pas expliquer la couleur. Page inchangée en poids (287 Ko) : seules 54 cases calculées sur
2 520 portent un repère.

**Tranché par l'utilisateur** : la case porte **les deux** — la mesure puis la statistique
de test entre parenthèses, `« 46,7 % (Z = 7,69) »`. `resultat()` gagne donc, à côté de
`repere`, un champ **`stat`** : la statistique qui DÉCIDE de la couleur, affichée dans la
case en plus petit.

| Test | Mesure affichée | Statistique affichée |
|---|---|---|
| 3.1 Productivité | ménages/jour | `z = 3,40` |
| 3.2 Durée | minutes | `rang 3,2 %` (position dans la distribution de référence) |
| 3.4 Règles | déclenchements | `z = 2,60` |
| 3.6 Non-réponse | % | `Z = 7,69` |
| 4.4 χ² terminal | χ² | `p = 0,0001` |
| 4.5 Effet-agent | % des pairs | `ICC 0,090` (du groupe) |
| 4.6 Kolmogorov-Smirnov | D | `p = 0,0003` |
| 4.8.1 χ² sur M7 | χ² | `p = 0,0210` |

Les tests à seuil **absolu** (3.3, 3.5, 4.1, 4.2, 4.3, 4.7, 4.8.2) n'en portent pas : la
mesure suffit à expliquer la couleur.

Ajouts techniques : **`ks_p`** (p-value asymptotique de Kolmogorov-Smirnov,
`Q(λ) = 2 Σ (−1)^(j−1) e^(−2j²λ²)` avec la correction usuelle de λ — contrôlée : au D
critique 0,1051 elle rend **0,046**) et **`rang_percentile`** pour 3.2. Côté page,
**`_qm_nb`** formate selon l'ordre de grandeur (167 · 46,7 % · 0,012 · 0) au lieu des deux
décimales fixes qui donnaient « 34,55 % » et « 0,000 % ».

---

## NIVEAU 3 — cohérence « cycle de vie » : 14 colonnes de plus (journal 2026-09-19)

**Demande** : *ajouter les tests de niveau 3.*

La matrice passe de **15 à 29 colonnes**. La section 5 du document se compose d'un
**répertoire de 13 règles logiques** (5.1) et d'un **score composite** qui les résume
(5.2) : les quatorze sont implémentées dans `vad_qualite.niveau3()`.

Chaque règle devient une colonne portant le **taux de violation** de l'unité, comparé à la
référence par un test Z de proportion — le document dit exactement cela : *« calculer, pour
chaque règle, un taux de violation par agent, puis tester si ce taux diffère
significativement de la moyenne de l'équipe »*.

⚠️ **Test UNILATÉRAL, contrairement à 3.6.** Pour une règle de cohérence, seul un EXCÈS de
violations est un défaut ; un agent qui en commet moins que ses pairs est soigneux, pas
suspect. (En 3.6 le bilatéral se justifie : ne jamais coder « ne sait pas » est en soi un
signal.)

| n° | Règle | Compté sur | Contrainte formulaire |
|---|---|---|---|
| 5.1.1 | Roster complet (liste = `nbmembre`) | ménages | Oui (V1) |
| 5.1.2 | Taille minimale ZD (`nbmembre` ≥ `taille_men_efkt`) | ménages | Oui (V1) |
| 5.1.3 | Chef de ménage unique (un seul M7 = 1) | ménages | Oui (W1) |
| 5.1.4 | Durée de résidence (M2a ≤ M4) | membres | Oui (V1) |
| 5.1.5 | Âge / année de naissance (M4 vs M4b, ± 1 an) | membres | Oui (M2) |
| 5.1.6 | CIN et âge légal (M6 seulement si M4 ≥ 18) | membres | Oui (filtre E) |
| 5.1.7 | Date de délivrance CIN (M6b ≤ CQ3) | membres | Oui (V1) |
| 5.1.8 | Scolarisation vs âge (1900 < M15a ≤ année d'enquête) | membres | Oui (V1) |
| 5.1.9 | Niveau scolaire vs âge (université avant 17 ans) | membres | **Non — ajouté ici** |
| 5.1.10 | Emploi vs âge (M19 seulement si M4 > 15) | membres | Oui (filtre E) |
| 5.1.11 | Incapacités vs âge (AUEM17a-c seulement si M4 > 5) | membres | Oui (filtre E) |
| 5.1.12 | Alphabétisation vs scolarisation (jamais scolarisé lisant « Tsara ») | membres | **Non — ajouté ici** |
| 5.1.13 | Emploi agricole / biens | ménages | **Non — ajouté ici** |
| **5.2** | **Score composite d'incohérence** | toutes règles | — |

Les trois règles marquées « ajouté ici » sont celles que le document signale lui-même comme
**« Non — à ajouter »** : elles n'existaient dans aucune contrainte de saisie.

### Le score composite (5.2)

`Score = Σ violations / Σ cas applicables × 100`, jugé par la **règle de Tukey** sur la
distribution des pairs — `Q3 + 1,5×IQR` = outlier modéré (orange), `Q3 + 3×IQR` = outlier
extrême, audit prioritaire (rouge). Le **Kruskal-Wallis** du groupe (H, ddl, p) est rappelé
dans le calcul de la fiche, comme l'ICC l'est pour 4.5 : c'est une statistique de groupe,
elle ne peut pas colorer une ligne.

**`kruskal_binaire()`** exploite le fait que les observations sont binaires (règle violée ou
non) : tous les ex æquo sont connus d'avance, les zéros partageant le rang (n₀+1)/2 et les
uns le rang n₀+(n₁+1)/2. La somme des rangs d'un agent se calcule donc **sans jamais
trier** — O(k) au lieu de O(N log N), ce qui rend le test calculable pour chacun des
400 agents. Correction des ex æquo appliquée (deux paquets seulement).

Le document contient ici une **incohérence interne** : son texte parle de « médiane + 3 IQR »
et ses seuils de « Q3 + 3×IQR ». C'est la version des seuils qui est retenue, la seule
chiffrée. Son exemple applique par ailleurs Kruskal-Wallis aux 10 *scores* (une observation
par agent, cas dégénéré) alors que sa propre définition pose *« N = nombre total
d'observations, ici de règles évaluées, tous agents confondus »* — c'est la définition qui
est implémentée. Contrôle : sur les scores de l'exemple, la règle de Tukey désigne bien
**13,5 % et 16,2 %**, les deux agents que le document veut voir signalés.

### 5.1.13 : le périmètre du document vidait la règle de son sens

Le document vise « AP09–AP25 », soit toute la famille « Agriculture & élevage ». Mesuré sur
le district 5201, ce périmètre dénonçait **64,6 % des ménages** — parce qu'il inclut la
bêche (136 ménages sur 318), le poulet gasy (165) et le puits (103), que presque tout le
monde possède. Une règle qui accuse deux ménages sur trois n'est pas une règle de cohérence.

Restreinte aux **moyens de production** — charrue, charrette, herse, stockage agricole,
champ ou rizière, irrigation, culture d'exportation — elle tombe à **24,7 %** et redevient
un signal. Élevage et petit outillage exclus. La liste est modifiable d'une ligne
(`CODES_AGRI`) si les statisticiens du RSU en jugent autrement.

### Le cache qui donnait de faux résultats

Les treize règles sont évaluées sur la même référence pour chacun des ~200 agents d'une
commune : sans mémorisation, la référence est reparcourue 200 fois par règle — **2,2 s**
pour le district 1106.

Un cache indexé par `id(liste)`, vidé à chaque commune, a ramené cela à **0,75 s** — mais
**trois cases avaient changé d'état**. Cause : les listes d'unités sont reconstruites à
chaque chef d'équipe ; une liste libérée voit son `id` réattribué à la suivante, et le cache
rendait alors les comptages du mauvais agent. Le cache est désormais **refusé par défaut**
(`cache=False`) et n'est accordé qu'à la RÉFÉRENCE et aux PAIRS, seules listes vivantes
pendant toute la commune ; l'unité, quelques ménages, est de toute façon peu coûteuse à
recompter. **Vérifié** : résultats identiques avec et sans cache
(`{alerte 7, vigilance 3, ok 91, nd 4771}` au district 5201), pour **0,47 s au lieu de
1,24 s**.

👉 **Leçon** : un cache indexé sur `id()` n'est valide que pour des objets dont on garantit
la durée de vie. Ici, seule la moitié des listes l'était.

### Testé

**Sur données réelles** (commune FENERIVE VILLE, 251 ménages, 0,02 s) : roster 0,80 % ·
chef unique 0,40 % · niveau scolaire 0,21 % · alphabétisation 0,19 % · agricole 24,7 % ·
les autres à 0 % · **score composite 3,00 % sur 4 895 cas applicables**.

**Sur un jeu synthétique** (4 agents corrects de 40 ménages + 1 qui viole chaque règle) :
l'agent fautif ressort **rouge sur 9 des 13 règles et sur le score composite (61,9 % contre
un seuil de Tukey à 11,1 %)**. Les 4 règles restées vertes le sont à cause du jeu d'essai,
pas du code — deux d'entre elles n'avaient aucune référence à laquelle se comparer (les
agents corrects n'ayant aucun cas applicable), une était violée par tous, et la dernière
testait un âge hors du filtre.

**HTTP réel** (Traitement du district 5201) : **29 colonnes** dans l'ordre attendu, en-tête
groupé **6 + 9 + 14**, 29 cases par ligne, page **396 Ko en 0,7 s** pour **168 agents × 29
tests = 4 872 cases**, fiche détaillée de **76 Ko** déroulant les trois niveaux, sections
`general`, `demographie` et `agents` intactes.

**Poids** : l'infobulle des cases « nd » a été rendue télégraphique (`3.1 · n = 1 / 10
requis`). Répétée 4 771 fois, la phrase complète pesait à elle seule ~100 Ko :
**396 Ko au lieu de 487**.

### Ce que le niveau 3 montre aujourd'hui

- **5.1.2 « Taille minimale ZD » est « nd » partout** : `taille_men_efkt` est **entièrement
  NULL** dans l'export VAD. C'est une conséquence directe du défaut de préchargement déjà
  documenté — la règle s'activera d'elle-même quand la colonne sera renseignée.
- Au niveau agent, seul le **score composite** se calcule (47 agents sur 168) : il agrège
  les treize règles, donc il atteint son effectif minimal bien avant chacune prise
  isolément. C'est la colonne à regarder en premier tant que les volumes sont faibles.

### Reste à faire

- [ ] **Niveaux 4 à 7** (logement H1–H10, biens AP1–AP4, fraude et duplication,
      non-réponse) + le **score composite de risque** de la section 10.
- [ ] **Arbitrer `CODES_AGRI`** (5.1.13) avec les statisticiens du RSU.
- [ ] À 29 colonnes, le défilement horizontal s'allonge. Si cela gêne, replier les 13
      règles derrière la colonne 5.2, dépliables au clic.

---

## NIVEAU 4 — caractéristiques du logement : 6 colonnes de plus (journal 2026-09-19)

**Demande** : *ajouter les tests niveau 4.*

La matrice passe de **29 à 35 colonnes** (en-tête groupé **6 + 9 + 14 + 6**).

Le fil conducteur de la section 6 : *dans une même zone, les matériaux et les
infrastructures varient peu d'un ménage à l'autre*. Tout écart marqué entre un agent et sa
zone sur ces variables est donc, par construction, un **effet-agent** et non un effet de
terrain.

### Une colonne par MÉTHODE, pas par variable

Le document décrit **cinq méthodes**, dont les trois premières s'appliquent « séparément »
aux **huit** variables catégorielles (H1, H4, H5, H6, H7, H8, H9, H10). Une colonne par
(méthode × variable) ferait **27 colonnes pour ce seul niveau**. Chaque méthode occupe donc
UNE colonne, qui porte **la variable la plus défavorable des huit**, la fiche détaillée
donnant le détail des huit. H2 (nombre de pièces), numérique, garde ses deux tests propres.

| n° | Test | Colonne | Alerte |
|---|---|---|---|
| **6.1** | χ² agent × modalité | nb de variables H significatives / 8 | ≥ 2 (Bonferroni ×8) |
| **6.2** | Entropie de Shannon | % de H_max de la variable la plus concentrée | < 50 % **et** zone ≥ 75 % |
| **6.3** | Distance de Bray-Curtis | BC max des 8 variables | > 0,5 |
| **6.4.1** | Grubbs sur H2 | G | > G_critique(0,05 ; n) |
| **6.4.2** | Concentration de H2 | part de la valeur dominante | Z > 2,58 (unilatéral) |
| **6.5** | Cohérence H1 × H5 | corrélation de rang | Fisher z, p < 0,05 |

### Outillage ajouté

- **`t_sf` / `t_quantile`** (Student et son quantile par dichotomie) puis
  **`grubbs_critique`**. Contrôles : t(0,05 ; 10) = **1,812** et t(0,025 ; 20) = **2,086**,
  exactement les valeurs des tables ; G critique à n = 10 → **2,290**, idem.
- **`entropie`** (Shannon, bits), **`bray_curtis`**, **`spearman`** (ex æquo par rangs
  moyens) et **`fisher_z_diff`**.
- `_chi2_m7` devient **`_chi2_ajustement`** : le χ² d'ajustement d'une répartition
  catégorielle à la référence n'a rien de propre à M7, il sert aussi aux huit variables H.

### Trois écarts au document, assumés et documentés

1. **6.2 — la phrase entière, pas seulement le seuil.** Le document écrit : *« H(agent) <
   50 % de H_max, **alors que les agents voisins de la même zone sont proches de H_max** »*.
   La seconde condition est indispensable et elle est implémentée : sans elle, une zone
   réellement homogène — ce que le document pose lui-même comme la norme — ferait virer
   **tout le monde** au rouge. Vérifié sur données réelles : à FENERIVE VILLE, H5 (toit)
   tombe à **40 % de H_max**, sous le seuil du document, mais la zone n'est elle-même qu'à
   **47 %** : tout le monde a un toit en tôle. Aucune alerte, à juste titre.
2. **6.5 — Spearman au lieu de polychorique.** Le document demande une corrélation
   polychorique estimée par **maximum de vraisemblance**. Une estimation ML par agent et par
   commune est hors de portée du budget de calcul d'une page ; c'est une **corrélation de
   rang (Spearman)** sur les mêmes échelles ordinales qui est calculée, avec le test de
   différence de Fisher z que le document prescrit. ⚠️ **Écrit noir sur blanc dans la fiche,
   à arbitrer.**
3. **Les échelles ordinales de « standing » sont un choix.** Le document ne donne qu'un
   exemple, pour H1 : *« vato/parpaing > biriky > torchis > bois/feuilles > bozaka »*. Cet
   ordre est respecté ; la place des modalités qu'il ne cite pas (tôle, planches, matériaux
   de récupération) et les échelles de H4, H5 et H6 sont un **classement de bon sens**
   (`ORDRE_H`). ⚠️ **À faire arbitrer.** « Hafa » est exclu : cette modalité n'a pas de rang.

### Une troisième erreur d'arithmétique dans le document

Après le D critique de Kolmogorov-Smirnov (4.6), deux nouveaux écarts :

| Document | Calcul vérifié |
|---|---|
| Grubbs, n = 45 : « G_critique ≈ **3,29** » | **3,09** — les tables donnent 3,036 à n = 40 et 3,128 à n = 50 ; 3,29 correspond à n ≈ 100 |
| Entropie de l'agent D : « ≈ **0,85** bit » | **1,02** bit — le 0,85 semble recopié de la modalité à 85 % |

Le code applique les formules, jamais les nombres imprimés. Les conclusions des exemples du
document restent vraies dans les deux cas.

### Testé

**Sur un jeu synthétique** — 4 agents qui observent (réponses variées, murs et toit
corrélés) contre 1 agent qui recopie (même modalité partout, 3 pièces pour tous, un 12
pièces isolé, murs et toit incohérents) : l'agent fautif ressort **rouge sur les six
tests** (8/8 variables significatives · entropie 0 % de H_max · BC 0,815 · G 6,93 ·
concentration 98 % · corrélation −1,000), l'agent honnête restant vert partout sauf un
6.1 à « 1/8 significative » — le faux positif résiduel que laisse Bonferroni sur huit
comparaisons.

**Sur données réelles** (FENERIVE VILLE, 251 ménages, 0,01 s) : 6.1 aucune variable
significative, 6.2 40 % (zone 47 % → pas d'alerte, cf. ci-dessus), 6.3 0,529, Grubbs 4,575,
concentration de H2 42 %, corrélation H1×H5 0,447.

**HTTP réel** : **35 colonnes**, 35 cases par ligne, page **455 Ko en 1,0 s** pour
**168 agents × 35 tests = 5 880 cases**, fiche de **84 Ko** déroulant les quatre niveaux,
autres sections intactes.

⚠️ **Piège de test rencontré** : la fiche testée était celle du premier agent du tableau,
dans une commune de **7 ménages** — même après escalade, tout le niveau 4 y est « nd » et
la fiche n'a rien à montrer. Le test pointe désormais un agent de la commune la plus
fournie. Ce n'était pas un défaut du code, mais le test ne prouvait rien.

### Ce qu'il faut savoir avant la production

- **Tout le niveau 4 est « nd » par agent** sur l'export pilote (1,5 ménage par agent contre
  des planchers de 10 à 30). Comme pour les niveaux 2 et 3, les colonnes se rempliront avec
  les volumes.
- **Grubbs (6.4.1) sera bavard.** H2 ne prend ici que les valeurs 1 à 6 (289 · 366 · 73 ·
  30 · 4 · 1) : l'écart-type est petit, et tout agent ayant déclaré un logement de 5 ou 6
  pièces dépassera le seuil. C'est le comportement correct du test — et le document lui-même
  conclut « soit une erreur de saisie, soit un logement réellement atypique à documenter » —
  mais il faudra s'attendre à du rouge peu spécifique tant que la distribution reste aussi
  resserrée.
- **6.3 escaladé à la commune compare des communes entre elles**, ce qui sort de la
  prémisse « au sein d'une même ZD ». Sur la fiche, le bandeau « ce résultat décrit cet
  ensemble, pas l'agent » le dit déjà ; dans la matrice, la question ne se pose pas
  puisque le calcul y est strictement au niveau agent.

### Reste à faire

- [ ] **Niveaux 5 à 7** (biens AP1–AP4, fraude et duplication, non-réponse) + le **score
      composite de risque** de la section 10.
- [ ] **Arbitrer `ORDRE_H`** et la substitution Spearman ↔ polychorique (6.5).
- [ ] À 35 colonnes, le défilement horizontal devient long. Replier chaque niveau derrière
      sa colonne de synthèse, dépliable au clic, devient la piste la plus utile.

---

## NIVEAU 5 — biens du ménage : 5 colonnes de plus (journal 2026-09-19)

**Demande** : *ajouter le test de niveau 5.*

La matrice passe de **35 à 40 colonnes** (en-tête groupé **6 + 9 + 14 + 6 + 5**). Les
29 items binaires du module « FANANAN'NY TOKANTRANO » servent à construire l'indice de
bien-être matériel : leur cohérence interne est un enjeu de mesure, et un agent qui coche
en bloc plutôt qu'il n'observe la dégrade de façon mesurable.

| n° | Test | Colonne | Alerte |
|---|---|---|---|
| **7.1** | Échelle de Guttman | coefficient de reproductibilité | Rep < 0,85 **et** excès d'erreurs vs zone |
| **7.2** | Alpha de Cronbach, leave-one-agent-out | ΔAlpha | > +0,03 |
| **7.3** | Indice de richesse (ACP) | score factoriel moyen | Mann-Whitney \|z\| > 2,58 |
| **7.4** | Biais global sur les 29 items | moyenne des \|Z\| | > 2 |
| **7.5** | Cohérence sectorielle (φ) | φ biens agricoles × activité | Fisher z, p < 0,05 |

### Outillage ajouté

- **`acp_premier_axe`** — ACP **sans numpy**, par puissance itérée sur la matrice de
  corrélation 29×29 : quelques dizaines de tours suffisent, pour un coût très inférieur à
  une diagonalisation complète et sans ajouter de dépendance au projet. Items sans variance
  écartés (ils rendraient la corrélation indéfinie).
- **`guttman_erreurs`** — comptage « par réponses », celui du document (14 erreurs sur
  240 réponses), et non le comptage par paires d'items : un ménage possédant *s* biens
  devrait posséder exactement les *s* plus répandus ; chaque écart est une erreur.
- **`cronbach`**, **`phi_2x2`**, **`mann_whitney_z`** (ex æquo corrigés).
- **`_memo`** : la mémorisation par zone, généralisée depuis le niveau 3 — l'ACP, les
  prévalences et l'alpha de la zone sont calculés **une fois par commune** et non une fois
  par agent. `_CACHE_N3` devient `_CACHE_ZONE`, mêmes règles de sûreté.

### Une correction en amont : la pêche manquait

La section 7.5 précise « activité agricole, d'élevage ou de **pêche** en M19 (modalités
**11, 12, 13**) ». Le code 13 (*Pêcheur*) manquait à la règle **5.1.13** du niveau 3, qui
comptait donc en violation les ménages de pêcheurs possédant du matériel de pêche. Corrigé,
et le matériel de pêche (AP17) ajouté aux moyens de production : **5.1.13 passe de 24,7 % à
20,9 % de violations**.

### φ non définissable : deux situations opposées derrière un même « pas de valeur »

Le test synthétique a révélé une case **verte et vide**. φ n'est pas définissable dès
qu'une marge de la table 2×2 est vide, et deux cas très différents se cachaient derrière :

- des ménages possèdent des moyens de production agricole et **aucun** n'a d'actif du
  primaire → c'est l'incohérence que le test cherche, poussée à son maximum : **alerte**,
  case rouge sans valeur, l'infobulle disant « 40 ménages … et AUCUN n'a d'actif » ;
- aucun ménage ne possède ni bien ni activité agricole → il n'y a rien à corréler :
  **« nd »**, et surtout pas une case verte.

Même principe que le « aucune femme déclarée » du test 4.7.

### Testé

**Sur un jeu synthétique** — 4 agents qui observent (ménages hiérarchiques, du bien le plus
répandu au plus rare) contre 1 qui coche au hasard : le fautif ressort **rouge sur 7.1
(Rep 0,505 contre 0,994), 7.3 (z = 3,65) et 7.4 (biais 3,94 contre 1,12)**, et orange sur
7.2 (ΔAlpha = +0,025, juste sous le seuil de +0,03 du document — le seuil fonctionne comme
spécifié).

**Sur données réelles** (FENERIVE VILLE, 251 ménages, 0,03 s) : Rep 0,806 · ΔAlpha +0,027 ·
score ACP moyen −0,237 (z = −5,06) · biais global 1,74 · φ 0,399.

**HTTP réel** : **40 colonnes**, 40 cases par ligne, page **504 Ko en 1,4 s** pour
**168 agents × 40 tests = 6 720 cases**, fiche de **90 Ko** déroulant les cinq niveaux.

### Ce que le niveau 5 apprend sur l'INSTRUMENT lui-même

Calculé sur le district 5201 entier (263 ménages aux 29 items renseignés) :

| Indicateur | Valeur | Norme | Verdict |
|---|---|---|---|
| Reproductibilité de Guttman | **0,793** | ≥ 0,90 | **échoue** |
| Alpha de Cronbach | **0,750** | ≥ 0,70 | passe |
| Variance du 1er axe (ACP) | **21,1 %** | 20–35 % | passe |

L'échelle est donc **cohérente** (alpha, ACP) mais **non hiérarchique** (Guttman) : les
29 items ne se rangent pas du plus courant au plus rare de façon stricte — ce qui est
attendu pour un module mêlant mobilier, énergie, transport et agriculture, où l'on peut
posséder une rizière sans téléviseur. Conséquence pratique : **le seuil Rep < 0,85 du
document sera franchi par beaucoup d'agents**, et c'est la comparaison à la zone (déjà
exigée par le document) qui fait le tri, pas le seuil absolu.

⚠️ Comme au niveau 4, un résultat **escaladé à la commune** compare une commune aux autres,
hors de la prémisse « même ZD ». Vérifié : à FENERIVE VILLE (urbaine), 7.3 et 7.4 sont
rouges — champ ou rizière 25 % contre 55 %, téléviseur 58 % contre 27 %, panneau solaire
21 % contre 45 %. C'est un contraste **urbain/rural réel**, pas un défaut d'agent. Dans la
matrice la question ne se pose pas : le calcul y est strictement au niveau agent.

### Reste à faire

- [ ] **Niveaux 6 et 7** (fraude et duplication, non-réponse et complétude) + le **score
      composite de risque** de la section 10.
- [ ] À 40 colonnes, replier chaque niveau derrière une colonne de synthèse dépliable
      devient nécessaire, pas seulement souhaitable.


## NIVEAU 6 — fraude et duplication : 4 colonnes de plus (journal 2026-09-19)

**Demande** : *ajouter les tests de niveau 6.*

La matrice passe de **40 à 44 colonnes** (en-tête groupé **6 + 9 + 14 + 6 + 5 + 4**).
Changement de question : les niveaux 2 à 5 cherchent un agent **qui mesure mal**, celui-ci
cherche un agent **qui n'est pas allé sur place**. Les quatre signaux sont indépendants —
c'est leur convergence sur un même agent qui fait un dossier, pas une case rouge isolée.

| n° | Test | Colonne | Alerte |
|---|---|---|---|
| **8.1** | Distance de Mahalanobis | % de paires de ménages suspectes | excès vs la zone, Z > 2,58 |
| **8.2** | Premiers chiffres (Benford) | χ² à la référence retenue | p < 0,05 |
| **8.3** | Régression de la durée | % de questionnaires trop rapides | un résidu standardisé < −3 |
| **8.4** | DBSCAN sur les GPS | % de relevés agglutinés | > 20 % des relevés |

### Outillage ajouté

- **`inverse_matrice`** — Gauss-Jordan à pivot partiel, sans numpy. Rend `None` sur une
  matrice singulière : une dimension constante dans la zone (toutes les maisons du même
  standing) rend Σ non inversible, et la distance de Mahalanobis n'est alors pas définissable.
- **`covariance`**, **`mahalanobis2`**, **`paires_mahalanobis`** (échantillon systématique
  au-delà de 20 000 paires : le nombre de paires croît en n², la précision d'une moyenne
  non).
- **`chi2_benford`**, **`chi2_homogeneite`** — les deux regroupent les classes de droite
  jusqu'à un effectif attendu de 5.
- **`regression`** (simple, avec σ des résidus et R²), **`distance_m`** (haversine),
  **`dbscan_agglutines`** (DBSCAN en O(n²), suffisant : n est le nombre de ménages d'un
  agent).
- **`M6a`** ajouté à `COLS_MEM` : le numéro de CIN n'était pas lu jusqu'ici.

### Trois écarts au document, assumés

**1. Le seuil de Mahalanobis porte sur D, pas sur D².** Le document écrit « D² » dans sa
formule mais chiffre son exemple en distance : *« distance moyenne entre paires de la
zone : 2,8 (écart-type 0,9) »*. Sur quatre variables, la moyenne de D² vaut 8 et celle de
D vaut √8 = **2,83**, d'écart-type ≈ **0,9** — ce sont exactement ses chiffres. Pris au pied
de la lettre sur D², son seuil « moyenne − 2 σ » vaudrait 8 − 11,3 < 0 : **aucune paire ne
pourrait jamais l'atteindre** et le test serait mort-né. On travaille donc sur D.

**2. Benford n'a aucune variable éligible dans ce questionnaire.** Le document vise « les
variables numériques à forte plage (le cas échéant, superficies, cheptel…) » : le
questionnaire VAD n'en a **aucune** — biens et logement sont binaires ou catégoriels. Le
seul nombre de grande plage que l'agent **saisit lui-même** est le numéro de CIN (M6a), et
un numéro inventé est précisément la fraude visée. Mais mesuré sur tout le périmètre,
**rien ne suit Benford** :

| Variable | n | χ² vs Benford | Verdict |
|---|---|---|---|
| Numéro de CIN (M6a) | 1 006 | **562** | rejette |
| Durée de passation | 892 | **280** | rejette |
| Précision GPS | 880 | **121** | rejette |
| Numéro de téléphone | 735 | **5 148** | rejette (tous en 3) |

Appliquer le seuil du document tel quel peindrait **tous** les agents en rouge, là où
aucune hypothèse de fraude ne porte. Le test **choisit donc sa référence** : Benford si la
zone s'y conforme (p ≥ 0,05), **sinon la distribution observée chez les collègues de la
zone** — on cherche l'agent qui s'écarte des autres, pas celui qui s'écarte d'une loi que
personne ne suit ici. La colonne dit laquelle des deux a décidé de la couleur. Même
raisonnement qu'au niveau 5 pour Guttman : *c'est la comparaison à la zone qui fait le tri,
pas le seuil absolu*.

**3. Le modèle de durée est ajusté SANS l'unité jugée.** Sur le jeu synthétique, le
fraudeur passait d'abord au vert sur 8.3 : en expédiant ses 40 entretiens il tirait à lui la
droite de régression et gonflait σ — **il devenait son propre étalon**. Le modèle est donc
ajusté sur la zone privée de l'unité (même *leave-one-out* qu'aux tests 7.1 et 7.2). Le
fraudeur ressort alors à 100 %.

### Un palier de vigilance qui ne valait rien

« Au moins un résidu < −2 » paraissait naturel pour le palier orange de 8.3. Sous le
modèle, **2,3 % des questionnaires passent ce seuil par hasard** : un agent de 40 entretiens
a deux chances sur trois d'en avoir un, et sur le jeu synthétique **sans aucun fraudeur, la
moitié des agents s'allumait**. Le palier teste maintenant si l'unité en compte **plus que
le hasard n'en donne** (Z > 1,96). L'alerte rouge, elle, garde le seuil du document (un
résidu < −3), qui se déclenche par hasard sur ~5 % des agents à 40 entretiens — taux assumé
pour un test de fraude, et la fiche donne le compte exact.

### Testé

**Sur jeu synthétique** — agents honnêtes (ménages tirés, durées conformes au modèle, GPS
dispersés, CIN en 1/2/3) contre un fraudeur qui recopie un même questionnaire, invente ses
CIN, expédie ses entretiens et ne bouge pas. Les deux premiers scénarios sont figés dans
**`tests/test_niveau6.py`** (graine fixe, `python tests/test_niveau6.py`) :

| Scénario | Résultat |
|---|---|
| 9 honnêtes + 1 fraudeur | le fraudeur **rouge sur les 4 tests** (8.1 : 100 % de paires suspectes, Z = 163 · 8.2 : χ² = 400 · 8.3 : 100 % · 8.4 : 100 %), les **9 autres verts partout** |
| 9 honnêtes, aucun fraudeur | **aucune alerte**, une seule vigilance (8.3) — le bruit attendu des seuils. Le test permanent tolère 1 alerte : à 40 entretiens, le seuil rouge du document se déclenche par hasard sur ~5 % des agents |
| 4 honnêtes + 1 fraudeur | 8.2 allume **aussi les honnêtes** : à 20 % de fraudeurs, la référence « reste de la zone » est elle-même contaminée. Limite inhérente à tous les tests comparatifs du module, visible seulement à ces proportions-là |

**Sur données réelles** (892 ménages VAD, 534 agents) : **3,3 s** pour les 44 colonnes, soit
**23 496 cases**. Le niveau 6 est « nd » pour 531 agents sur 534 — ils ont 1 à 9 ménages là
où ces tests en demandent 10 à 30. Rien d'anormal : c'est la règle du module depuis le
niveau 1, et la fiche détaillée, elle, remonte au CE ou à la commune et calcule.

**HTTP réel** : page de **1 590 Ko en 4,2 s** (534 agents × 44 tests), fiche d'agent de
**101 Ko** déroulant les six niveaux.

### Ce que 8.4 a trouvé dès le premier passage

Deux agents sur les trois assez fournis pour être testés sortent **rouges**, et l'examen des
coordonnées confirme :

- **EQ1_VHBT_0063** — **6 de ses 13 relevés portent des coordonnées STRICTEMENT identiques**
  (−21,4647131 / 47,111396), dont un dans un **autre fokontany** (ANDRAINJATO au lieu
  d'AMBATOSOA I), plus deux autres relevés identiques entre eux. L'agent s'est bien déplacé
  par ailleurs (un ménage à 2 km), donc ce n'est pas un GPS en panne.
- Ce **même point** apparaît chez un autre agent (EQ1_VHBT_0127) : il ressemble à un relevé
  de repli réutilisé plutôt qu'à une position réellement acquise.
- **EQ1_VHBT_0129**, en revanche, reste **vert** malgré deux relevés à 1,7 m : MinPts = 3
  empêche une paire de maisons mitoyennes de déclencher l'alerte. Le test distingue donc
  bien l'habitat dense de la réutilisation systématique.

⚠️ À vérifier sur le terrain avant toute conclusion : une alerte désigne un dossier à
ouvrir, pas une fraude établie. La cause peut aussi être un appareil qui ressert son
dernier point.

### Reste à faire

- [ ] **Niveau 7** (non-réponse et complétude) + le **score composite de risque** de la
      section 10, qui combine des indicateurs des niveaux 2 à 7.
- [ ] **8.2 ne se calcule jamais au niveau agent** sur l'export actuel (30 numéros de CIN
      exigés, un agent en a ~6). Il ne vivra que par escalade tant que la production n'aura
      pas augmenté — ou avec une autre variable si le questionnaire en gagne une.
- [ ] **Arbitrer les rangs de `ORDRE_H`** : le « score de standing H » de 8.1 les réutilise,
      avec la même réserve qu'au niveau 4.
- [ ] À 44 colonnes, replier chaque niveau derrière une colonne de synthèse dépliable
      n'est plus optionnel.


## NIVEAU 7 — non-réponse et complétude : 3 colonnes de plus (journal 2026-09-19)

**Demande** : *ajouter les tests de dernier niveau : au niveau 7.*

La matrice passe de **44 à 47 colonnes** (en-tête groupé **6 + 9 + 14 + 6 + 5 + 4 + 3**).
**Les sept niveaux du document sont livrés.** Ce dernier ne juge plus ce qui a été répondu
mais ce qui ne l'a pas été : un blanc n'est inoffensif que s'il est aléatoire ; dès qu'il
dépend de l'agent, il devient un biais qui se propage à toutes les analyses en aval.

| n° | Test | Colonne | Alerte |
|---|---|---|---|
| **9.1** | MCAR de Little | d² (et sa p-value) | p < 0,05 : non-réponse structurée |
| **9.2.1** | χ² non-réponse × agent | nb de variables clés sur 21 | ≥ 2 variables en excès (p corrigée) |
| **9.3** | Taux de couverture | % de personnes recensées / attendues | < 90 % |

La **matrice de missingness** de la section 9.2 n'est pas une colonne : c'est purement
descriptif. Elle est livrée dans la **fiche détaillée**, sous 9.2.1 — une ligne par
variable, avec le taux de l'unité, celui de la zone et le χ².

### Outillage ajouté

- **`little_mcar`** — groupe les ménages par MOTIF de manquants, compare la moyenne des
  variables observées de chaque motif à la moyenne générale, pondérée par l'inverse de la
  covariance restreinte à ces mêmes variables. Réutilise `covariance` et `inverse_matrice`
  du niveau 6. Cinq variables suivies : nombre de membres, taille au dénombrement, nombre
  de pièces, rang des murs, rang du toit.
- **`chi2_2x2`** — χ² d'indépendance (unité, reste) × (manquant, renseigné), invalidé dès
  qu'un effectif attendu descend sous 5.
- **`resultat(raison=…)`** — un « nd » dit désormais POURQUOI. Deux causes très
  différentes se cachaient derrière la même phrase sur l'effectif : trop peu
  d'observations, ou une statistique non définissable malgré un effectif suffisant (rien à
  quoi comparer, matrice non inversible). Les cinq « nd » possibles des niveaux 6 et 7
  portent maintenant leur motif exact.

### Trois écarts au document, assumés

**1. Le dénominateur de 9.3 n'existe pas.** Le document calcule la couverture sur
`taille_men_efkt`, préchargée depuis les données Fokontany. Cette colonne est
**entièrement NULL** dans l'export VAD — le même défaut de préchargement qui laisse déjà
la règle 5.1.2 du niveau 3 « nd » partout. Le test retient donc la colonne d'attendu qui
apparie le **plus** de ménages, à égalité celle du document : `taille_men`, préchargée elle
aussi, mais depuis la taille relevée au **dénombrement** (`taille_menD` de
`prechargement.py`). Même nature — un attendu connu avant la visite — et c'est bien l'écart
à cet attendu que la section 9.3 cherche. La fiche nomme la source retenue.

**2. μ̂ et Σ̂ de Little sont estimées sur les ménages complets**, là où le test d'origine
passe par un algorithme EM. L'écart reste faible tant que les ménages complets dominent
(32 sur 36 sur l'unité testée), et cela évite d'embarquer un EM dans un module qui se passe
de numpy. Une variable constante sur les ménages complets est retirée avant l'estimation :
sinon Σ n'est pas inversible et le test entier meurt — découvert sur jeu synthétique.

**3. Les questions filtrées ne sont pas des non-réponses.** Chaque variable clé porte sa
condition d'applicabilité : consentement RSU pour le logement et les biens, âge pour la
CIN, l'activité et les incapacités, scolarisation pour l'année de fin d'études. Sans ces
filtres, la mesure est dominée par du bruit structurel :

| Variable | Non-réponse brute | Avec filtre d'applicabilité |
|---|---|---|
| H1 Matériau des murs | 14,3 % | **1,0 %** (`Perm_rsu` = oui) |
| M19 Activité principale | (filtrée) | **0,3 %** (âge > 15) |
| M6 Possède une CIN | (filtrée) | **1,1 %** (âge ≥ 18) |
| M15a Année de fin d'études | — | **32,1 %** (a été scolarisé) |

Les 120 ménages qui ont refusé le module RSU ou n'ont pas été sollicités compteraient
sinon comme 120 non-réponses sur **chaque** variable H et AP, et l'agent qui tombe sur des
refus paraîtrait fautif.

### Testé

**Sur jeu synthétique** — figé dans **`tests/test_niveau7.py`** (graine fixe,
`python tests/test_niveau7.py`). Le fautif cumule les trois signatures : il saute le module
logement **précisément chez les ménages nombreux**, laisse vides les modules longs, et
inscrit deux à trois personnes de moins que l'attendu.

| Scénario | Résultat |
|---|---|
| 9 honnêtes + 1 fautif | le fautif **rouge sur les 3 tests**, les 9 autres **verts partout** |
| 9 honnêtes, aucun fautif | **aucune alerte**. 9.2.1 y sort « nd » : sans presque aucun manquant, il n'y a rien à tester — et « nd » vaut mieux qu'un vert qui affirmerait |

Un piège trouvé par ce jeu : tant que `taille_men` valait exactement `nbmembre`, les deux
variables étaient **parfaitement colinéaires**, Σ n'était pas inversible et 9.1 sortait
« nd » pour tout le monde. D'où la garde sur les variables constantes, et un jeu
synthétique où l'écart au dénombrement varie.

**Sur données réelles** (892 ménages VAD, 534 agents) : **4,5 s** pour les 47 colonnes,
soit **25 098 cases**. **Non-régression vérifiée** : les 23 496 cases des niveaux 1 à 6 sont
identiques au calcul précédent, seules s'ajoutent les 1 602 cases du niveau 7.

**HTTP réel** : page de **1 681 Ko en 5,4 s**, fiche d'agent de **107 Ko** déroulant les
**sept** niveaux.

### Ce que 9.3 montre sur la couverture

Sur les 23 agents ayant au moins 5 ménages appariés :

| Indicateur | Valeur |
|---|---|
| Taux de couverture médian | **84,0 %** |
| Étendue | **35,3 % à 104,5 %** |
| Agents sous le seuil de 90 % du document | **15 sur 23** |
| Ensemble du périmètre | **85,7 %** (183 ménages listent moins que l'attendu, 21 plus) |

Le seuil absolu du document allumera donc **les deux tiers des agents** : l'écart au
dénombrement est la règle, pas l'exception, et c'est en soi un constat à porter aux
coordonnateurs. Mais l'étendue montre que la colonne **discrimine** — 35 % et 100 % ne
décrivent pas le même travail. ⚠️ Un écart peut être réel (départs, décès depuis le
dénombrement, qui date de plusieurs semaines) : l'alerte désigne une zone à revisiter, pas
une faute établie.

**Convergence à noter** : `EQ1_VHBT_0063`, déjà rouge en **8.4** (6 relevés GPS
strictement identiques), sort aussi rouge en **9.3** (80,6 %). Deux signaux indépendants —
des questionnaires relevés sans déplacement, et des ménages listés incomplets — sur le même
agent. C'est exactement ce que le score composite de la section 10 est censé agréger.

### Reste à faire

- [ ] **Score composite de risque** (section 10) et **tableau de synthèse des agents classés
      par risque** : dernière pièce du document, et la seule qui manque désormais. Sans
      elle, il faut lire 47 colonnes sur 534 lignes pour repérer les convergences comme
      celle de `EQ1_VHBT_0063`.
- [ ] **Faire renseigner `taille_men_efkt`** au préchargement : 9.3 et la règle 5.1.2
      basculeraient alors sur le dénominateur du document.
- [ ] À 47 colonnes, replier chaque niveau derrière une colonne de synthèse dépliable est
      la condition pour que le tableau reste lisible.

---

## JOURNAUX D'INGESTION : pastille verte, deux journaux, district nommé (journal 2026-09-20)

**Signalement** : depuis le compte Admin, le journal des téléversements et des
transcriptions affichait « Succès » **en rouge** — l'Admin en a conclu à un problème de
collecte alors que tout s'était bien passé.

### La cause, à un mot près

Le serveur consignait les opérations VAD avec le statut **« Succès »** ; l'affichage, lui,
testait `statut == "Réussi"` pour choisir la pastille (`admin.py`, `transcription.py`).
Toute opération VAD tombait donc dans le `else` → **rouge**. Les 12 téléversements et
transcriptions VAD de la base étaient tous des succès.

### Ce qui a été fait

- **La couleur ne dépend plus d'une égalité de chaîne** : `journal.reussi(statut)` —
  est un succès tout ce qui ne dit pas « Échec », tolérant à la casse et aux accents.
  Le libellé affiché est normalisé (« Réussi » / « Échec »), sans réécrire les lignes
  déjà en base. Côté écriture, les deux appels VAD consignent désormais « Réussi ».
- **Deux journaux séparés** : `journal.transcriptions(..., phase=)` filtre sur
  `PHASE_DEN` / `PHASE_VAD`, la phase se déduisant du suffixe « VAD » de l'événement.
  L'Admin voit *Ingestion — Dénombrement* et *Ingestion — Visite à domicile* ;
  l'Expert survey ne voit que le dénombrement sur sa page dénombrement, et la page
  `/transcription/vad` gagne **son propre historique**, qu'elle n'avait pas du tout.
- **Colonne District nommée** (« FARATSIHO (1406) ») au lieu du code nu, résolue en une
  requête (`journal.noms_districts`), sur la vue Admin **et** sur les historiques de
  l'Expert.
- **Les refus de téléversement VAD sont consignés** (fichier ménages absent, mauvais
  district). Ils ne l'étaient pas : l'Expert voyait un bandeau rouge et l'historique
  restait muet, alors que le dénombrement consignait déjà ses refus.

**Vérifié** sur une copie : 64 lignes DEN / 12 VAD, aucun mélange de phase, les 12 lignes
VAD en `pill ok` (avant : 12 rouges), 19 vertes et 4 rouges sur le tableau de bord Admin —
les 4 rouges étant les vrais échecs d'Ambohidratrimo et Vavatenina.

**À retenir** : deux modules qui écrivent le même journal doivent partager le **vocabulaire
du statut**, ou mieux, ne jamais faire dépendre un affichage d'une égalité de chaîne
littérale. Ici « Succès » et « Réussi » voulaient dire la même chose pour un humain et
l'inverse pour le code.

---

## CARTE GPS DE LA VAD : le style du dénombrement (journal 2026-09-20)

**Demande** : *le GPS de la VAD n'est pas satisfaisant, utilise le style du dénombrement
(`/vue/gps`).*

La carte VAD était un fond OpenStreetMap avec des points bleus tous identiques et une
bulle réduite au code et au fokontany. Elle reprend maintenant le fonctionnement de celle
du dénombrement.

### Ce qu'elle a gagné

- **Fonds satellite** : Bing Aérien, Google Satellite, Google Hybride, Esri, plus
  OpenStreetMap — mêmes sources et mêmes `maxNativeZoom` que `/vue/gps` —, calque
  « Noms de lieux », échelle, rendu `preferCanvas`.
- **Couleur et filtres, avec la règle du dénombrement transposée** : celui-ci colore par
  agent au fokontany et par date au-dessus. Ici, **≤ 12 agents → couleur par agent** avec
  une case par agent dans le sélecteur de calques ; **au-delà → couleur par date**, les
  boutons de date portant leur pastille. Un district compte plus de 100 agents (123 à
  Fenerive Est) : une liste de cases par agent y serait illisible. Le filtre par date
  fonctionne dans les deux cas et **se cumule** avec le filtre agent.
- **Bulle complète** : ménage, chef de ménage, date de l'entretien, code agent,
  fokontany · commune, nombre de membres · précision GPS. L'agent vit dans
  `vad_diagnostics`, pas dans la table des ménages : `_sec_gps(menages, diag)` reçoit
  désormais les diagnostics, et `_lire` lit `nom_cm`.
- **Hauteur de carte** calquée sur `#map` du dénombrement (plein écran, repli à 60 vh
  sous 860 px).

### Les contours sont servis À PART (et allégés)

La page `/vue/gps` du dénombrement embarque ses contours : elle pèse **8,9 Mo**. Pour la
VAD, ils sont chargés après l'affichage par **`GET /vad/contours.json`** (route placée
avant `/vad/<section>`, périmètre pris de la session, jamais de l'URL), et **allégés par
Douglas-Peucker** (`limites_db.contours_zones`, `TOLERANCE_CARTE = 0.0002°` ≈ 22 m) :

| District | Brut (district + communes) | Allégé |
|---|---|---|
| 1106 | 926 Ko | **79 Ko** |
| 5201 (côte très découpée) | 2 306 Ko | **187 Ko** |

À 0,0001 (≈ 11 m), 5201 pesait encore 767 Ko ; à 0,0005 (≈ 56 m) le tracé commence à
couper les méandres. La page GPS VAD reste à ~116 Ko et la carte est utilisable avant
l'arrivée des contours. Nouveau `Handler._json()` : réponse JSON avec cache **privé** 1 h
(contours administratifs, pas de données nominatives, mais dépendants du périmètre).

⚠️ **Seuls quatre districts ont des limites en base** (1101, 1106, 5201, 5206, cf.
`limites_db`). Pour 1406, 3303, 3306 et 3307 la carte s'affiche sans contour — vérifié,
sans erreur, le sélecteur ne propose alors que « Noms de lieux ».

### Le cadrage se fait sur la ZONE, pas sur les points

Constat en cours de route : **5 ménages du district 5201 portent des coordonnées quasi
identiques (−18,12303 / 49,38212), à 82 km au sud du district**, pour 4 fokontany et
5 agents différents — une coordonnée de repli d'appareil, pas une position relevée (même
famille que l'alerte 8.4 déjà documentée). Un seul point de ce genre suffit à étirer
`fitBounds` au point que le district n'est plus qu'une tache. La carte se cadre donc sur
le **contour de la zone** dès qu'il arrive ; le point aberrant reste atteignable en
dézoomant.

---

## DESCENTE District → Commune → Fokontany sur la carte VAD (journal 2026-09-20)

**Demande**, en trois temps : d'abord « la hiérarchisation pour le choix du GPS à
afficher » a disparu (elle n'avait jamais existé côté VAD, c'était un reste à faire) ;
puis « ça ne s'instaure pas » à Fianarantsoa et Faratsiho ; puis « les communes ne
s'affichent pas en bas quand on clique sur Carte GPS ».

### Filtrage SERVEUR, périmètre du rôle inchangé

- `vad_db._clause_perimetre(conn, districts, communes, fokontany=None)` : du plus fin au
  plus large, **CQ9 prime sur CQ8, qui prime sur CQ7**.
- `vad_db.zones_disponibles(conn, districts, communes)` : les communes et fokontany **où
  il y a des données VAD**, tirés de `vad_menage` et nommés par le référentiel `zones`
  (CQ8/CQ9 en sont des clés étrangères). On ne propose pas les 213 fokontany d'un
  district, dont la plupart ouvriraient une carte vide.
- `vad_core.agrege(..., commune=, fokontany=)` : `districts`/`communes` restent le
  **périmètre du rôle**, `commune`/`fokontany` sont la descente ; le périmètre effectif
  est le plus fin des deux. Les indicateurs du haut décrivent donc bien ce que la carte
  montre.
- `serveur_app._vad_zone_choisie()` **valide** la zone contre `zones_disponibles`, qui est
  déjà borné par `perimetre()`. Testé : une commune d'un autre district (`?commune=330301`
  depuis Fenerive Est) est ignorée, la page reste au district ; un fokontany inventé est
  ignoré, la page reste à la commune. `?fokontany=` seul suffit — la commune est retrouvée
  pour garder la cascade cohérente.
- La **portée affichée** (en-tête + barre latérale) suit la descente :
  « District FENERIVE EST › FENERIVE VILLE › AMPARATANANA ».

### Où la mettre : deux essais avant le bon

1. **Barre de listes déroulantes en haut de page** — refusée : ce n'est pas la forme du
   dénombrement, et sur les districts où **une seule commune porte toutes les données**
   (Fianarantsoa : 176 ménages sur 176 ; Faratsiho : 81 sur 82), choisir la commune ne
   changeait **rien à l'écran** — d'où « la descente ne s'instaure pas ». La liste des
   fokontany, verrouillée tant qu'aucune commune n'était choisie, rendait alors le seul
   niveau utile inaccessible.
2. **Sous-menu de la barre latérale**, sous l'entrée de la section — la forme du
   dénombrement (`nav-sub` / `nav-sub-item commune|fkt`, CSS partagé de `rapport.css`).
   C'est la version retenue.

### Flèches de dépliage

- Un bandeau **« ▾ COMMUNES (n) »** replie toute la liste ; l'état est mémorisé
  (`localStorage rsu_vad_drill`).
- Chaque commune porte sa **flèche ▸/▾**, bouton distinct du lien : ouvrir une commune
  pour voir ses fokontany **ne change pas de page**. Tous les fokontany du périmètre sont
  écrits, repliés (30 à Lalangina, 69 au maximum à Vohibato) : regarder ce que contient
  une commune ne demande aucun aller-retour serveur. La commune courante s'ouvre d'elle-même.
- Le libellé, lui, reste un **lien** : c'est le serveur qui recalcule les agrégats.

### Contours et cadrage suivent le niveau

`limites_db.contours_zones` renvoie `{niveau, principal, sous}` : **rouge = le niveau
affiché, bleu = ses enfants** — district → communes, commune → fokontany, fokontany seul.
Le poids suit : **187 Ko au district, 6 Ko à la commune, 2 Ko au fokontany**.

### Bouton ☰ : masquer la barre des sections

Le dénombrement avait déjà ce bouton (`body.rsu-nav-col`, script global
`serveur_app._STYLE_RESPONSIVE`) mais il exigeait un `.topbar`, que le tableau de bord VAD
n'a pas. Le script retombe désormais sur **`.page-head`** : même bouton, même CSS, et la
**préférence est partagée** entre les deux tableaux de bord (clé `rsu_nav_col`). Sur un
écran de 1 500 px, la carte passe de 1 255 à **1 445 px** de large. Le bouton est présent
sur **toutes** les sections VAD, pas seulement la carte.

### Vérifié (Firefox headless, copie de la base)

Les trois niveaux sur Fenerive Est, Fianarantsoa, Faratsiho et Lalangina ; le changement
de commune qui remet le fokontany à zéro ; « ↺ Tout le district » ; l'ouverture d'une
commune sans navigation ; les libellés de calques par niveau ; le ☰ des deux tableaux de
bord ; les 10 sections VAD en 200. Exemple de descente (Lalangina) : district 70 ménages /
88,10 m de précision → commune 19 / 93,44 m → fokontany 9 / 100,33 m.

**À retenir** : quand l'utilisateur dit « ça ne s'instaure pas », vérifier d'abord **ce
que la descente change réellement à l'écran**. Ici le code fonctionnait ; c'est le jeu de
données qui rendait le premier niveau muet, et la forme choisie qui cachait le second.

---

## AUDIT DES 47 TESTS DE QUALITÉ VAD : contradictions et utilité (journal 2026-09-20)

Les 47 tests ont été exécutés sur les **6 districts** porteurs de données VAD — 675 agents,
31 725 cellules — puis rejoués en fiche détaillée (avec escalade agent → CE → commune) sur
l'agent le plus fourni de la commune la plus fournie de chaque district.

**403 cellules seulement sont calculées (1,3 %)** : 38 alertes, 12 vigilances, 353
conformes. **23 des 47 tests ne se calculent jamais au niveau agent** sur cet export.
Quatre tests portent 84 % des cellules calculées : 5.2 (148), 3.5 (89), 3.6 (74), 3.3 (28).

### Huit familles de contradictions, mesurées

1. **Les seuils absolus du niveau 2 condamnent le recensement lui-même.** Calculé sur les
   microdonnées RGPH-3 2018 **déjà intégrées dans l'application**, l'indice de Whipple vaut
   **134,0 au niveau national** et **151,3 à Fenerive Est** — « âges grossiers » sur la
   grille du document, dont le seuil d'alerte (4.1) est 125. De même pour 4.7 : **505 des
   1 704 communes (30 %)** ont un rapport de masculinité RGPH hors de la plage [90 ; 108]
   que le test déclare invraisemblable — alors que la page Démographie affiche ce même
   rapport RGPH comme **référence locale**.
2. **Même phénomène, verdicts opposés, parce que la référence contient l'unité.** Dans les
   6 districts : 4.1 et 4.4 en alerte, 4.6 (Kolmogorov-Smirnov) au vert, avec un
   **D = 0,000 exact** dans quatre cas — signe que l'unité testée EST sa référence après
   escalade.
3. **Le complément vide rend l'alerte maximale.** 6.3 (Bray-Curtis) vaut **exactement 1,0**
   — « aucune modalité en commun » — dans 4 districts sur 6, alors que l'unité est
   *identique* à sa zone : `vad_ce` ne couvrant que le district 5201, une commune n'a
   souvent qu'un seul CE, et « le reste de la zone » est vide. En face, 6.1 trouve
   **0 variable significative sur 8**.
4. **Une statistique indéfinissable s'affiche en VERT.** 7.2 et 7.4 sortent « conforme »
   **sans aucune valeur** dans 4 districts. La cause est générale : la condition s'écrit
   `v is not None and v > seuil`, donc une valeur indéfinie retombe sur « ok ». **Seuls
   5 tests sur 35 (8.1, 8.2, 8.3, 9.1, 9.2.1) portent la garde `raison`** qui distingue
   « pas assez d'observations » de « statistique non définissable ».
5. **Complétude récompensée par un test, punie par l'autre.** 3.6 étant bilatéral,
   **13 des 27 agents signalés le sont pour avoir coché MOINS de « Tsy mahalala » que leur
   zone** (jusqu'à 0,0 % contre 33,3 %, Z = −3,67) — ces mêmes agents étant au vert sur 3.3,
   qui compte ces réponses comme remplies. L'inverse existe : 3.3 à **39,7 % (rouge)** avec
   3.6 vert à Lalangina.
6. **9.1 en alerte** (manquants structurés, d² = 90,1) avec **9.2.1 au vert** (0 variable
   sur 21) dans la même fiche.
7. **Diagnostics opposés qui s'allument ensemble** : à Fenerive Ville, 8.1 « questionnaires
   quasi identiques » **et** 6.3 « trop différent de la zone » sont rouges simultanément.
   Par construction, 6.4.1 (valeur aberrante de H2) et 6.4.2 (valeurs trop concentrées)
   peuvent coexister.
8. **La fiche d'un agent ne parle presque jamais de lui.** Tests calculés sur l'agent
   lui-même : **3 sur 45 (7 %) à Fenerive Ville, 0 sur 42 à Avaradrano, 0 sur 41 à
   Faratsiho**. Deux lignes voisines d'une même fiche décrivent donc deux populations
   différentes ; le bandeau « ce résultat décrit cet ensemble » existe mais est plus
   discret que le rouge qu'il nuance.

Neuvième cas, mineur : **5.1.2 est « nd » partout** (`taille_men_efkt` NULL) pendant que
**9.3 mesure la même idée** sur `taille_men` et sort 79,9 % (rouge).

### Tous ces tests sont-ils utiles ?

Non — et pour trois raisons distinctes :

- **Ce ne sont pas des tests d'agent, et le volume n'y changera rien.** L'IPAS (4.3)
  demande 800 personnes et se lit « au niveau de la zone » de l'aveu du document ; l'ICC
  (4.5), l'alpha de Cronbach (7.2), la reproductibilité de Guttman (7.1) et le MCAR de
  Little (9.1) sont des statistiques **de groupe ou d'instrument**. 7.1 mesure que le
  module « biens » n'est pas hiérarchique (Rep = 0,79 sur tout le district), pas qu'un
  agent travaille mal. Les mettre en colonne d'agent **oblige à escalader**, et l'escalade
  produit les contradictions ci-dessus.
- **Redondance mesurée.** Sur les 8 communes ayant au moins 60 âges : Whipple alerte
  7 fois, **χ² terminal 8 fois sur 8** — un test qui se déclenche partout ne hiérarchise
  rien —, Myers 3 fois ; réunis, ils désignent les 8 mêmes communes. Même recouvrement
  entre 6.1 et 6.3, et dans le quatuor 7.1/7.2/7.3/7.4.
- **Inopérants faute de données.** 5.1.2 (`taille_men_efkt` NULL), 8.2 (aucune variable
  éligible ; le repli sur le numéro de CIN demande 30 numéros par agent, qui en a 6),
  6.5 et 7.5 (dépendants de classements posés a priori, `ORDRE_H` et `CODES_AGRI`, non
  arbitrés).

**Proposition, non appliquée — décision de méthode** : ramener la **matrice** à une
quinzaine de colonnes réellement individuelles (3.1–3.6, 5.2, 6.4.1, 7.3, 7.4, 8.1, 8.3,
8.4, 9.3, plus une colonne « règles de cohérence » remplaçant les 13 colonnes 5.1.x, déjà
agrégées par 5.2) ; déplacer les autres dans un **diagnostic de zone** calculé une fois par
commune (4.1–4.4, 4.7, 6.1–6.3, 7.1, 7.2, 9.1) ; garder la **fiche détaillée à 47 tests**
telle quelle, puisqu'elle documente le protocole. Gain accessoire : la page passe
aujourd'hui à **1,68 Mo et 5,4 s** pour 534 agents, dont l'essentiel est du « nd ».

⚠️ Deux réserves : ce diagnostic porte sur un **pilote à 1,5 ménage par agent en médiane**,
donc les tests « actifs mais rares » se rempliront en production ; et cette réduction
**s'écarte du document technique RSU**, qui demande les sept niveaux.

### Reste à faire (issu de cet audit)

- [ ] **Généraliser la garde `raison`** aux 30 tests qui ne l'ont pas : une statistique
      indéfinissable doit sortir « nd », jamais « conforme ». Mécanique, sans risque.
- [ ] **Traiter le complément vide** (6.3, 4.6, 7.2, 7.3, 7.4, 8.1) comme le fait déjà
      9.2.1 : « l'unité couvre toute sa zone de référence » → nd.
- [ ] **Recalibrer les seuils absolus du niveau 2** sur le RGPH-3 (Whipple national 134,
      rapport de masculinité hors [90 ; 108] dans 30 % des communes) plutôt que sur la
      grille générique.
- [ ] **Trancher avec les statisticiens du RSU** : caractère bilatéral de 3.6, plage de
      4.7, règle 4.8.2 sur le parent du chef, variante de l'IPAS, `ORDRE_H`, `CODES_AGRI`.
- [ ] **Charger `vad_ce` pour tous les districts** (`charger_ce_vad.py` ne couvre que
      5201) : sans CE, une commune n'a qu'un seul « CE inconnu », ce qui déclenche
      précisément l'artefact du complément vide.
- [ ] Décider de la **réduction de la matrice** ci-dessus.

---

## BILAN DE LA SESSION DU 2026-09-20

| # | Chantier | Résultat |
|---|---|---|
| 1 | **Journaux d'ingestion** | Pastille verte rendue à `journal.reussi()`, **deux journaux séparés** DEN/VAD (Admin et Expert), district **nommé**, refus VAD enfin consignés, historique ajouté à `/transcription/vad`. |
| 2 | **Carte GPS VAD** | Style du dénombrement : fonds satellite, couleur par agent ou par date, filtres cumulables, bulle complète, contours rouge/bleu, cadrage sur la zone. |
| 3 | **Contours allégés** | `limites_db.contours_zones` + Douglas-Peucker (22 m) : 2,3 Mo → 187 Ko, servis par `/vad/contours.json` (cache privé 1 h) au lieu d'être écrits dans la page. |
| 4 | **Descente Commune → Fokontany** | Filtrage serveur borné au périmètre du rôle, sous-menu de la barre latérale avec **flèches de dépliage**, portée affichée en chaîne complète. |
| 5 | **Bouton ☰ mutualisé** | Le script global retombe sur `.page-head` : le VAD gagne le masquage de la barre des sections, préférence partagée avec le dénombrement. |
| 6 | **Audit des 47 tests** | 8 familles de contradictions mesurées, triage d'utilité, liste de correctifs — **rien n'a été modifié dans `vad_qualite.py`**, ce sont des décisions de méthode. |

**Modifiés** : `journal.py`, `admin.py`, `transcription.py`, `vad_web.py`, `vad_core.py`,
`vad_db.py`, `limites_db.py`, `serveur_app.py`, `CLAUDE.md`. **Aucun nouveau fichier.**

### Leçons de cette session

1. **Ne jamais faire dépendre un affichage d'une égalité de chaîne littérale** : « Succès »
   et « Réussi » voulaient dire la même chose pour un humain et l'inverse pour le code.
   Un prédicat (`journal.reussi`) vaut mieux qu'un `==`.
2. **Un journal qui n'enregistre que les succès est aveugle** là où il sert le plus : les
   refus de téléversement VAD n'étaient nulle part.
3. **« Ça ne marche pas » → reproduire d'abord, et regarder ce que ça change à l'écran.**
   La descente fonctionnait ; sur deux districts, une commune unique portait toute la
   collecte, donc le premier niveau ne changeait rien — le défaut était dans le choix du
   niveau offert, pas dans le code.
4. **Copier une interface, c'est copier ses règles, pas seulement son apparence.** La carte
   du dénombrement colore par agent au fokontany et par date au-dessus : reprendre la
   couleur par agent sans le seuil aurait donné 123 cases dans le sélecteur de calques.
5. **Un seul relevé aberrant suffit à rendre une carte inutilisable** (`fitBounds`). Cadrer
   sur la zone, pas sur les points ; le point aberrant reste visible en dézoomant — et il
   est signalé par ailleurs (test 8.4).
6. **Alléger une géométrie est un calcul, pas un réglage au jugé** : Douglas-Peucker borne
   l'écart au tracé d'origine, ce qui permet d'annoncer « 22 m au maximum » plutôt que
   « ça a l'air pareil ».
7. **Un test qui alerte sur tout le monde ne teste rien** (χ² terminal : 8 communes sur 8).
   Vérifier le **pouvoir discriminant** d'un indicateur avant de lui donner une colonne.
8. **Une case verte est une affirmation** : si la statistique n'a pas pu être calculée, le
   verdict doit être « nd », jamais « conforme ».
9. **Comparer une unité à une référence qui la contient** ne peut que rendre « conforme » :
   c'est ainsi que K-S sort D = 0,000 pendant que Whipple crie à l'arrondi.
10. **Piège d'outillage** : le pilotage WebDriver maison enveloppe le script dans
    `return (...)` — un script à plusieurs instructions y lève une `SyntaxError` silencieuse
    et donne l'illusion d'un bouton qui ne réagit pas. Utiliser une IIFE.
11. **Toujours libérer le port avant de relancer une instance de test** : `kill` d'un PID de
    shell laisse l'ancien serveur répondre, et l'on teste l'ancien code en croyant tester le
    nouveau (vécu deux fois dans cette session).

---

## SESSION DU 2026-09-21 — ÉCART DÉCLARATION ↔ SERVEUR, PAR AGENT

**Demande** : ajouter *l'écart entre ce que l'agent déclare et ce qui arrive au serveur,
par agent*, **dans le tableau de bord** et **dans l'export Excel du rapport**.

L'écart existait déjà dans l'export, mais **seulement par agent ET par date**, noyé dans
un tableau par chef d'équipe — et **nulle part dans le tableau de bord**. Il manquait la
lecture la plus simple : *cet agent-là, sur toute la période, déclare-t-il plus qu'il
n'envoie ?*

### Ce qui a été fait

| Où | Quoi |
|---|---|
| `rapport_core.ecart_declaration(menages, declare, chefs)` | **Le calcul, une seule fois**. Prend les ménages du périmètre et `{(agent, date): déclaré}` ; rend une ligne par agent (jours déclarés, déclaré, reçu, écart, % du déclaré, détail par date) + un total. Trié par **écart décroissant** : le plus gros manquant d'abord, les agents sans déclaration en fin de liste. |
| `declarations.par_agent_date_perimetre()` | Le **bornage au périmètre** (agents ayant des données ici + ceux rattachés à un chef d'équipe du périmètre) était écrit dans `export_rapport` ; il est remonté dans `declarations.py`, utilisé par l'export **et** par le serveur. |
| `db_source.agents_du_perimetre()` | Les codes agent présents au serveur pour un district / des communes, en **une requête** — sans charger les ménages. `declaration_agent` n'a pas de colonne géographique : c'est le rattachement à un chef d'équipe qui borne. |
| `serveur_app.rapport_vue()` | Pour `section == "agent"` **au niveau district uniquement** : lit les déclarations du périmètre, les reclé sur le **nom** de l'agent (même convention que les ménages), passe `declarations=` et `chefs_agents=` au moteur. |
| `rapport_core.generer_rapport()` | Nouveaux paramètres `declarations` / `chefs_agents` -> écrit `const ECART_DECL` dans la page. Absents (exe hors-ligne) : rien n'est écrit, gabarit inchangé. |
| Gabarits | Page **« Par agent »** : 3 KPI (déclarés / arrivés au serveur / écart), graphique horizontal des **12 plus grands écarts**, tableau **un agent = une ligne** — au clic, le **détail par date** se déplie. Aux niveaux commune / fokontany, un rappel renvoie (lien) vers la page du district. |
| `export_rapport.py` | Nouvelle feuille **« Écart par agent »** (synthèse, avant le détail), alimentée par le **même** `ecart_declaration`. L'ancienne feuille devient explicitement le **détail par date**. `_ecart_donnees()` mutualise reçu / déclaré / périmètre entre les deux feuilles. |
| `serveur_app` (cache) | `_vider_cache()` après un **import de déclarations** réussi : la page « Par agent » est en cache, elle doit repartir avec les déclarations qui viennent d'arriver. |
| `manuel_roles.py` | Les puces de l'export et l'encadré du Superviseur Technique disent où lire l'écart (tableau de bord **et** Excel). |

**Modifiés** : `rapport_core.py`, `declarations.py`, `db_source.py`, `serveur_app.py`,
`export_rapport.py`, `templeteHtml/template_head.html`, `templeteHtml/template_tail.html`,
`manuel_roles.py`, `CLAUDE.md`. **Aucun nouveau fichier.**

### Décisions de méthode

1. **L'écart ne se ventile pas par zone.** Un agent déclare *un nombre par jour*, pas un
   nombre par fokontany : rapporter sa déclaration entière aux ménages d'une seule commune
   fabriquerait un écart faux. D'où le calcul **au périmètre entier** (district, ou « mes
   communes affectées » pour un Superviseur Technique) et le **rappel** aux niveaux
   inférieurs plutôt qu'un chiffre trompeur.
2. **« — » n'est pas un zéro.** Aucune déclaration saisie pour un agent (ou un jour)
   laisse `déclaré`, `écart` et `%` à `None` ; le pied de tableau compte à part les agents
   « données reçues mais **aucune** déclaration ». C'était déjà la règle de l'export, elle
   est maintenant tenue par le calcul lui-même.
3. **Un seul calcul, deux sorties.** Le tableau de bord et l'Excel affichent exactement les
   mêmes nombres parce qu'ils appellent la même fonction — vérifié sur le district 6305
   (BETIOKY SUD) avec des déclarations de test : 3 707 déclarés / 4 059 reçus / −352 des
   deux côtés.
4. **Les ménages sans date valide sont exclus** : ils ne sont comparables à aucune
   déclaration (même règle que la feuille existante).

### Leçon

**Ajouter une donnée à une page en cache, c'est aussi choisir quand le cache tombe.**
L'écart venait jusque-là d'un export généré à la demande ; sur une page mise en cache,
la même donnée serait restée figée jusqu'au prochain téléversement de dénombrement.


### Complément du 2026-09-21 — la MÊME chose pour la VISITE À DOMICILE

La demande visait la **VAD** ; le dénombrement (ci-dessus) l'avait déjà en partie, la
visite à domicile n'avait rien. Le calcul étant commun, l'ajout a consisté à le
brancher sur les données VAD.

| Où | Quoi |
|---|---|
| `vad_core._sec_ecart_declaration()` | Branche `rapport_core.ecart_declaration` sur les ménages VAD (`vad_menage`, date `CQ3`) et les déclarations de type **VAD**. Exposé dans `agrege()` sous la clé **`ecart`**. Les codes agent BRUTS sont relevés **avant** que `agrege` ne les remplace par les noms — c'est sur eux que porte `declaration_agent`. |
| `vad_web._p_ecart()` | Sur la page **« Par agent »** : note de lecture, 3 KPI (déclarés / arrivés au serveur / écart), graphique horizontal des 12 plus grands écarts (rouge = arrivé moins que déclaré), puis le tableau agent par agent. |
| `export_vad._feuille_ecart()` | 6ᵉ feuille du classeur VAD, **« Écart par agent »** — mêmes colonnes, mêmes nombres (vérifié : 366 déclarés / 318 reçus / +48 des deux côtés sur le district 5201). |
| `declarations.codes_perimetre()` / `dates_perimetre()` | **Conscientes de la phase.** Elles ne regardaient que le dénombrement : le modèle Excel VAD proposait les dates du dénombrement, et cinq agents du district 5201 — présents en VAD, jamais en dénombrement — auraient été **refusés à l'import**. VAD = agents des deux phases (un agent peut déclarer une VAD dont rien n'est arrivé), dates de la VAD. |
| `serveur_app._declaration_contexte(…, top)` | La phase déclarée descend jusqu'au périmètre : modèle, page et import. |

**Deux garde-fous repris du dénombrement** : pendant une **descente** commune /
fokontany, l'écart n'est pas calculé mais expliqué (la déclaration est journalière et
globale, elle ne se ventile pas par zone) ; **sans aucune déclaration saisie**, une
phrase le dit au lieu d'un tableau de « — ».

**Leçon** : *une donnée n'est utilisable que si la saisie qui l'alimente l'est aussi.*
Afficher l'écart VAD n'aurait rien donné tant que le modèle de saisie proposait les
dates du dénombrement et refusait les agents propres à la VAD.

---

## TÉLÉVERSEMENT DU DÉNOMBREMENT : la structure est RÉCONCILIÉE, plus exigée à l'identique (journal 2026-09-21)

**Demande** : *accepter le téléversement et la transcription des données de dénombrement
quand elles ont la structure de ce dossier* (export Survey Solutions
`DEN_MENAGE_1_STATA_All_20260921T1104Z`, questionnaire **« DENOMBREMENT RSU »**, généré le
21/09/2026, district **5206 VAVATENINA** — 12 segments, 60 lignes de roster).

### Ce qui bloquait : UNE colonne

Le dossier contient bien les 3 `.dta` requis à la racine (plus `interview__actions`,
`interview__comments`, `interview__errors`, `assignment__actions`, `export__readme.txt`,
`manifest.json` et `Questionnaire/`), et **toutes** les colonnes exigées par
`rapport_core._REQUIS`. Le refus venait d'ailleurs — `maj_db.maj_table`, qui comparait les
colonnes du `.dta` au **schéma enregistré en base** (`_schema`) et exigeait l'**égalité
stricte, ordre compris** :

| Table | Base | Ce dossier | Écart |
|---|---|---|---|
| `interview__diagnostics` | 11 | 11 | — |
| `segment_roster` | 20 | 20 | — |
| `den_menage` | 413 | **414** | **`nbr_max_men`**, inséré en 10ᵉ position |

Une colonne en plus, et tout le dossier était refusé avec « structure différente : […] un
changement de questionnaire nécessite un rechargement complet » — c'est-à-dire, en
pratique, la perte des données déjà transcrites (c'est ce qui avait été fait le
2026-09-11, au prix de 5 882 segments).

### La règle maintenant appliquée

`maj_table` **réconcilie** les deux structures au lieu de les comparer, dès lors que le
fichier reste un export de dénombrement :

- colonne du `.dta` **absente de la base** → `ALTER TABLE ADD COLUMN` (type déduit comme à
  la création, clés étrangères déclaratives comprises) ; les lignes déjà transcrites y
  restent **NULL** — on n'invente pas de valeur pour une question qui n'était pas posée ;
- colonne de la base **absente du `.dta`** → **conservée** : les lignes anciennes gardent
  leur valeur, les nouvelles la laissent NULL. Vérifié : elles ne ressortent pas non plus
  en « modifiées », la comparaison ne portant que sur les colonnes que le `.dta` apporte ;
- **ordre différent** → sans effet, tout se fait par NOM ;
- l'ordre de `_schema` reste celui de la base, les nouvelles colonnes venant **à la
  suite** : ce qui était déjà lu ne se décale pas. `_ecrire_meta(…, ordre)` fusionne au
  lieu de réécrire, et ne remplace que les **jeux de value labels portés par le `.dta`**
  (ceux des colonnes absentes du fichier restent en place).

### Le garde-fou qui remplace l'égalité stricte

Sans ce contrôle, n'importe quel `.dta` renommé passerait. `maj_db.REQUISES` dérive de
`rapport_core._REQUIS` via `db_source.FICHIERS` : les colonnes sont exigées **par TABLE**,
pas par nom de fichier — un fichier mal nommé ne contourne donc rien. Vérifié : le fichier
ménages de la VAD renommé `DEN_MENAGE.dta` est refusé (« n'a pas les colonnes
indispensables au rapport : segment »). Les tables VAD n'y figurent pas : `vad_db.
trouver_fichiers` fait déjà ce contrôle de son côté, et son ingestion est inchangée
(re-vérifiée : 336 / 779 / 336, mêmes chiffres qu'avant).

### Le piège du DDL qui échappe au rollback

L'aperçu (`dry_run=True`) se termine par un `rollback`… qui annule les écritures de
`_schema` mais **pas** le `CREATE`/`ALTER TABLE`, passé en autocommit côté `sqlite3`. Sans
précaution, « Téléverser » (aperçu) puis « Transcrire » (application) échouait sur une
colonne en double. D'où `_colonnes_sql(conn, table)` — les colonnes **réelles** de la table
— et deux gardes : `_ajouter_colonnes` n'ajoute que ce qui manque physiquement, et une
table qui existe **sans** `_schema` (aperçu créateur puis rollback) repart de ses colonnes
réelles au lieu d'être recréée. Effet de bord utile : sur une base **neuve**, l'enchaînement
aperçu → application ne plante plus (il levait « table den_menage already exists »).

⚠️ `_colonnes_sql` interroge le **catalogue** (`PRAGMA table_info` / `information_schema.
columns`), jamais la table : un `SELECT` sur une table absente lève, et **sous PostgreSQL
une requête en erreur avorte la transaction en cours** — tout ce qui suivrait échouerait.

### Vérifié (sur une COPIE de `rsu_local.sqlite`, jamais la vraie base)

| Scénario | Résultat |
|---|---|
| Aperçu puis application du dossier | `+72 ajoutées / ~0 / =12 inchangées`, colonne `nbr_max_men` ajoutée (12 lignes renseignées, 4 088 à NULL) |
| Rejoué une 3ᵉ fois | `+0 / ~0 / =84` — **idempotent** |
| Colonne de la base retirée du `.dta` | conservée, **379 lignes intactes**, aucune fausse « modification » |
| Fichier VAD renommé `DEN_MENAGE.dta` | **refusé**, motif nommant la colonne manquante |
| Base neuve : aperçu puis application | passe (levait « table already exists » avant) |
| Chaîne de rapport + export Excel, district 5206 | 379 segments / 1 253 ménages, taille moyenne 2,72 · σ 1,45 ; `.xlsx` valide |
| Ingestion VAD (partage `maj_table`) | inchangée |
| Export **sans** `nbr_max_men` sur la base **avec** (cas réel : `DATA_serveur/1106`, 413 colonnes) | accepté, `+0 / ~0 / =905`, colonne conservée, 249 lignes du district intactes |

### Au passage : les données du district 5206 étaient INCOHÉRENTES en base

`interview__diagnostics` portait les **12 interviews** de ce dossier alors que
`den_menage` et `segment_roster` n'en avaient **aucune** trace. Explication : lors d'une
tentative précédente, `maj_depuis_dossier` a transcrit les diagnostics (1ʳᵉ table de
`CLES`) **avant** d'échouer sur `den_menage` — et le `journal.consigner` du gestionnaire
d'erreur, qui **commit**, a validé au passage la transcription partielle restée en attente.
La réconciliation fait disparaître ce cas précis (les 3 tables passent ensemble), mais **le
défaut reste** : toute `ErreurMaj` survenant après la 1ʳᵉ table laisse une transcription
partielle en base. À corriger — consigner sur une **autre connexion**, ou `rollback` avant
de journaliser.

### Reste à faire

- [ ] **Transcription partielle en cas d'échec** (ci-dessus) : `journal.consigner` valide
      ce que la transcription laissait en attente.
- [ ] `nbr_max_men` (nombre maximal de ménages du segment) n'est **lu par rien** : le
      rapport et l'export l'ignorent. À exploiter si l'indicateur a un usage de suivi.
- [ ] Les **4 088 lignes déjà en base** ont `nbr_max_men` à NULL et le resteront :
      seules celles (re)transcrites depuis un export du nouveau questionnaire portent la
      colonne. Tout calcul qui s'appuierait dessus doit traiter le NULL comme « non
      collecté », pas comme un zéro.

### La colonne a été ajoutée à `den_menage` tout de suite (2026-09-21)

La réconciliation aurait ajouté `nbr_max_men` au moment de la transcription ; elle a été
mise en place **à l'avance**, dans la table de son fichier — `DEN_MENAGE.dta` →
**`den_menage`** (`db_source.FICHIERS`) — par un nouveau script **`ajouter_colonne.py`** :

```
python ajouter_colonne.py <dossier_dta> [--dry-run]
```

Il fait la même chose que `maj_db` (`_ajouter_colonnes` + `_ecrire_meta`) **sans transcrire
la moindre ligne** : les 4 088 lignes déjà en base restent à NULL. Une seule différence,
voulue : l'ordre écrit dans `_schema` devient **celui du `.dta`** — `nbr_max_men` se place
à **SA** position (10ᵉ, entre `segment` et `segment_men__0`) au lieu d'être ajoutée en fin
de liste ; les colonnes que la base garde et que le questionnaire ne collecte plus
resteraient, elles, à la suite. Cet ordre ne sert qu'à **lister** les colonnes
(`DbDataset.varnames`) : tout le code lit par NOM. `--dry-run` n'exécute **rien** (un
`ALTER TABLE` passé en autocommit ne se `rollback` pas, cf. `maj_db._colonnes_sql`).

⚠️ **Effet de bord à connaître** : `_schema` étant désormais **exactement** la liste du
nouveau questionnaire, l'ancien code (comparaison stricte) aurait accepté ce dossier-ci
mais **refusé les exports SANS `nbr_max_men`** — 413 colonnes contre 414 — soit ceux des
districts encore sur l'ancien questionnaire (1106, 5201, 6305…). Ajouter la colonne sans
déployer la réconciliation aurait donc **déplacé le blocage** au lieu de le lever. Sans
objet ici : le service a été **redémarré à 18:33**, après la modification de `maj_db.py`
(18:29) — il sert la réconciliation, et les deux formes d'export passent (vérifié
ci-dessous).

**Appliqué sur la base de production** après **sauvegarde à chaud** (API `backup` de
SQLite, pas un `cp` : le service tient la base) →
`deploy/backups/rsu_local-avant-colonne-nbr_max_men-20260921-183814.sqlite` (1,10 Go).
Réversible : `ALTER TABLE "den_menage" DROP COLUMN "nbr_max_men"` (SQLite 3.45) + retrait
de sa ligne dans `_schema`.

**Vérifié après coup, sur la production** : `_schema` = 414 colonnes, **identique à la
liste du `.dta`** ; colonne physique présente ; **4 088 lignes intactes, toutes à NULL** ;
`segment_roster` 18 494 et `interview__diagnostics` 4 115 inchangés ; rapports des districts
**5206** (367 segments / 1 193 ménages / taille 2,71) et **1106** (249 / 405 / 3,82)
identiques à avant ; export Excel valide ; l'aperçu de transcription du dossier n'annonce
**plus aucun changement de structure** (`+72 / ~0 / =12`) ; le service en ligne répond
toujours (HTTP 200).

### Suppression des données de VAVATENINA (5206) — 2026-09-21

**Demande** : supprimer toutes les données de Vavatenina, VAD **et** dénombrement.

**La VAD n'avait rien à supprimer** : aucun ménage `CQ7 = 5206` en base, aucun dossier
`DATA_serveur/VAD/5206`. Les données VAD couvrent 5201 (318), 3306 (276), 1106 (228),
3303 (176), 1406 (82) et 3307 (70) — et pas Vavatenina. Vérifié avant d'écrire quoi que
ce soit, et sur `CQ7` (la colonne `district` du questionnaire VAD n'est pas fiable, cf.
session du 2026-09-18).

**Supprimé** (script `deploy/supprimer_vavatenina.py`, exécuté après une **sauvegarde à
chaud** → `deploy/backups/rsu_local-avant-suppression-vavatenina-20260921-185253.sqlite`,
1,10 Go) :

| Cible | Lignes |
|---|---|
| `segment_roster` | −1 193 |
| `interview__diagnostics` | −379 |
| `den_menage` | −367 |
| `agent` (codes sans données ailleurs) | −103 |
| `DATA_serveur/5206/` | dossier entier (12 fichiers, 4,4 Mo) |

Les **379 clés** visées réunissent celles du district **en base** (367) et celles du
**dossier téléversé mais jamais transcrit** (12) — sans quoi les diagnostics orphelins de
la transcription partielle (cf. section précédente) seraient restés. Les 2 agents ayant
aussi des données dans un autre district sont conservés ; les 103 supprimés n'avaient
**aucun nom saisi** (auto-créés, nom = code) et seraient recréés seuls à la prochaine
transcription.

**Conservés, volontairement** : les 11 comptes affectés à 5206, les 8 lignes du journal
des transcriptions (la trace des opérations, y compris les échecs), le journal de bord,
le référentiel `zones` (111 fokontany) et tout le reste des districts.

**Vérifié** sur une copie d'abord, puis sur la production : `den_menage` 5206 = **0**,
`vad_menage` 5206 = **0** ; districts témoins **identiques** au chiffre près — 1106
(249 segments / 405 ménages / 3,82), 5201 (328 / 1 850 / 2,63), 6305 (790 / 4 059 / 2,29) ;
un rapport demandé sur 5206 rend des sections vides **sans planter** ; service en ligne
HTTP 200.

Pas de `VACUUM` : quelques centaines de Ko libérés ne valent pas la réécriture d'une base
de 1,10 Go (dont l'essentiel est le RGPH-3). ⚠️ Le **cache de pages** du service
(`serveur_app._CACHE`) peut encore servir des pages Vavatenina calculées avant la
suppression : un redémarrage le vide.

---

## EXPORT VAD : les listings d'erreurs retrouvent UNE COLONNE PAR CONTRÔLE (journal 2026-09-21)

**Signalement** : dans l'export du rapport VAD, « toutes les colonnes des erreurs ne sont
pas exportées » — or les équipes ont besoin de **toutes** les colonnes des erreurs ménage
et individu pour corriger les données.

### Le constat

Le **tableau de bord** affiche les deux listings dans la forme du dofile INSTAT — une
**colonne par contrôle**, la cellule portant le message de correction. L'**export Excel**,
lui, écrasait tout cela en **deux colonnes** : « Anomalie(s) » (les libellés concaténés)
et « Détail de la règle ». Impossible d'y filtrer sur un contrôle, de trier par nombre
d'anomalies, ou de répartir le travail par type d'erreur.

| Feuille | Avant | Après |
|---|---|---|
| Erreur ménage | 11 colonnes | **27** (10 d'identification + Nb + Anomalie(s) + **15 contrôles**) |
| Erreur Individu | 14 colonnes | **27** (14 + Nb + Anomalie(s) + **11 contrôles**) |

### Ce que la feuille porte maintenant

- **Une colonne par contrôle**, intitulée `Libellé (code_de_la_règle)` — le code sert à
  retrouver la règle dans le dofile, le libellé à la comprendre sans dictionnaire des
  variables. La cellule porte le **message de correction** sur fond rouge quand l'anomalie
  est présente, et reste **vide** sinon.
- **Nb anomalies** (tri : les ménages les plus abîmés d'abord) et **Anomalie(s)** (les
  libellés concaténés, l'ancienne colonne — gardée pour lire une ligne d'un coup d'œil).
- Identification complète : clé d'interview, chef de ménage, géographie, **agent**, **chef
  d'équipe**, date, **statut**, et pour une personne le membre, sa ligne, son âge et le
  **motif d'absence saisi** (c'est lui qu'on relit pour trancher `err_membre`).
- En bas de feuille, la **légende** : code · colonne · message · ce que le contrôle
  vérifie. Puis les **contrôles NON calculables** sur cet export, avec les variables qui
  manquent (sources de revenu, superficies, CIN…) — sans cette liste, une colonne absente
  se lirait comme un contrôle réussi.

**Deux défauts corrigés au passage** : le **filtre automatique** portait sur la ligne 7,
**vide** (les en-têtes sont en ligne 8) — les menus déroulants ne filtraient rien ; et
`freeze_panes` figeait les lignes 1 à 7, donc la ligne d'en-tête **disparaissait** au
défilement. Le filtre est désormais posé sur la vraie ligne d'en-tête, et le gel garde
l'en-tête **et** les 2 (ou 3) colonnes d'identification à l'écran — indispensable à
27 colonnes.

### Vérifié

Comparaison **cellule par cellule** avec le listing du tableau de bord (district 5201) :
pour chacune des 34 lignes ménage et 22 lignes individu, l'ensemble des colonnes remplies
est **exactement** l'ensemble des règles déclenchées, et « Nb anomalies » vaut le compte
de la ligne — 38 et 40 cellules d'anomalie. Sur tout le périmètre (1 150 ménages) :
96 lignes ménage, 118 lignes individu, classeur de **144 Ko en 9,1 s**. Les 9 manuels se
rendent sans erreur.

Le **manuel** décrivait encore l'ANCIENNE section « Listing d'erreurs » (gravités
« bloquante / à vérifier »), supprimée le 2026-09-18 : remplacé par la description des deux
sections actuelles, de leurs colonnes, des filtres et des feuilles Excel correspondantes.

⚠️ **Redémarrage du service requis** pour que l'export soit servi dans cette version.

### Trois blocs RETIRÉS du classeur, le même jour

Sur demande, après relecture du classeur produit :

| Feuille | Bloc retiré |
|---|---|
| Erreur ménage · Erreur Individu | « **Les contrôles, colonne par colonne** » (la légende des règles) **et** « **Contrôles NON calculables sur cet export** » |
| Test qualité données globale | le bloc « **Synthèse** » (ménages retenus, personnes, communes, indicateurs en alerte / à surveiller / conformes / non calculés) |
| Test qualité données par Agent | le bloc « **Synthèse** » (agents testés, tests par agent, cases en alerte / à surveiller / conformes / non calculées) |

Les deux feuilles d'erreurs ne portent donc plus **que le tableau** (27 colonnes) suivi de
sa ligne de source ; les deux feuilles de test de qualité **ouvrent directement** sur leur
détail. Ce qui n'a **pas** bougé : la « Synthèse » de la feuille **Global** (avancement de
la collecte) et la « **Légende des tests** » de la matrice par agent — deux blocs
différents, qui n'étaient pas visés.

⚠️ La liste des **contrôles non calculables** ne figure donc plus dans le classeur. Elle
reste consultable sur le tableau de bord, mais le classeur seul ne dit plus qu'un contrôle
absent n'est **ni réussi ni échoué**. Le code du contrôle reste dans chaque intitulé de
colonne, ce qui permet de retrouver la règle dans le dofile.

### Reste à faire

- [ ] Le message du contrôle `H2_aberante` est littéralement **« oui »** (repris du
      dofile) : dans une feuille destinée à la correction, il ne dit pas quoi faire.
      À réécrire avec les statisticiens du RSU, comme les autres messages.
- [ ] Les **11 contrôles non calculables** le restent tant que l'export ne porte pas
      `SR01..SR09`, `PT01..PT03`, `typeculture`, `SR10`, `Milieu` et `M6_valid` : c'est
      une question de questionnaire, pas de code.


---

## L'ADMIN PEUT ENVOYER DES CONSIGNES, comme les Coordonnateurs (journal 2026-09-22)

**Demande** : *permettre à l'Admin d'envoyer des consignes comme pour le cas des
Coordonnateurs.*

Les consignes (`consignes.py`, `/consignes[/nouvelle|/modifier|/supprimer]`, cf. la
section datée 2026-08-31) n'avaient que **deux émetteurs** : le Coordonnateur Nationale et
le Coordonnateur régionale. L'Admin les **recevait** (bulle + page, comme tout le monde)
mais ne pouvait pas en écrire.

### Le changement tient en une constante… et un lien

| Fichier | Quoi |
|---|---|
| `serveur_app.py` | **`_ROLES_CONSIGNE_ENVOI` gagne `"Admin"`**. C'est la seule garde : les 5 points de contrôle (GET/POST `nouvelle`, GET/POST `modifier`, POST `supprimer`) et le bouton « Écrire une consigne » de la page de réception la lisent tous. Le filtre « Poste de l'émetteur » de `/consignes` propose donc aussi **Admin**. |
| `admin.py` | Lien **« Consignes »** dans la barre de l'espace Admin (`_entete`), vers `/consignes/nouvelle` — l'Admin n'a pas de menu à cartes, c'est son point d'entrée pour **écrire**. Le lien du bandeau (`/consignes`, tous rôles) reste, lui, celui de la **réception**. |

**Rien d'autre n'a été nécessaire**, et c'est le point à retenir :

- les routes `/consignes*` sont placées **AVANT les gardes de rôle** dans `do_GET`/
  `do_POST` (elles l'étaient déjà pour être ouvertes à tous en réception) : l'Admin, que
  les gardes renverraient sur `/admin`, les atteint donc sans exception à écrire ;
- `perimetre()` rend `(None, None)` pour l'Admin (`_ROLES_ZONE_ENTIERE`) : il vise **tous
  les districts** (`districts_cibles='TOUS'`), comme le Coordonnateur Nationale, sans une
  ligne de code de plus — c'est `_consignes_cibles` qui en décide, à partir du périmètre ;
- « ← Retour à mon espace » passe par `accueil_role(role)` → **`/admin`** ;
- les droits sur SES consignes (modifier / supprimer / réinitialisation des accusés de
  lecture) sont ceux de l'auteur, vérifiés dans `consignes.modifier`/`supprimer` par
  `auteur_login` — **pas par le rôle** : un Coordonnateur ne peut pas toucher une consigne
  de l'Admin, ni l'inverse.

`_ROLES_CONSIGNE_CIBLES` est **inchangé** : les rôles *destinataires* restent tous les
rôles **sauf Admin**. (Comme avant, « Tout le monde » = `roles_cibles='TOUS'` atteint
malgré tout l'Admin, `_concerne` court-circuitant la liste sur cette sentinelle.)

La carte « Suivi des rapports journaliers » de `page_menu_operation` est gardée par la
même constante : sans effet ici, l'Admin ne voyant pas cette page (il n'est pas dans
`_MENU_CHEMINS`). La route `/journal/suivi`, elle, lui était **déjà** ouverte
(`_ROLES_JOURNAL_LECTURE`).

### Vérifié (HTTP réel, sur une COPIE de la base, port 8097 — jamais la vraie)

Trois comptes de test créés **dans la copie** (Admin, Traitement affecté à 5201,
Coordonnateur régionale de 5201) :

| Parcours | Résultat |
|---|---|
| Barre de `/admin` | lien **Consignes** présent |
| `GET /consignes/nouvelle` en Admin | **200**, formulaire complet, case **« Tous les districts »** (et non « Tous mes districts ») |
| Envoi ciblé *rôle Traitement · tous districts* | **303 ?ok=1** ; le Traitement la voit sur `/consignes`, émetteur affiché « Admin de test » |
| Envoi *Tout le monde* puis session neuve du destinataire | bulle **« 1 consigne à lire »** |
| Envoi ciblé *district 5201* | reçue par le Traitement de 5201 |
| Filtre « Poste de l'émetteur » de `/consignes` | propose **Admin** |
| Modification par l'Admin | **303 ?modifie=1**, message à jour |
| Modification / suppression par un **Coordonnateur** de la consigne de l'Admin | **303 sans écriture** (garde auteur) ; la consigne reste intacte |
| Suppression par l'Admin (auteur) | **303 ?supprime=1** |
| Rôle **non émetteur** (Traitement) | `GET` → **303 vers /consignes** ; `POST` → **403** |
| Non-régression Coordonnateur régionale | envoi **303 ?ok=1**, carte « Consignes & instructions » toujours sur `/coordoreg` |

⚠️ **Redémarrage du service requis** pour que ce code soit servi en ligne (cf.
« Redémarrer sans sudo » : `kill` du process du port 8000, systemd relance).

### À retenir

**Une autorisation bien placée s'ouvre en ajoutant un nom à une liste.** Ici les cinq
gardes, l'affichage du bouton et le filtre de la page de réception lisaient tous la même
constante, et le périmètre de ciblage se déduisait déjà de `perimetre()` : il n'y avait
aucune règle à dupliquer pour un rôle de plus. Le seul vrai travail restant était de
donner à ce rôle un **point d'entrée visible** — son espace n'ayant pas de menu à cartes.

### Piège d'outillage rencontré

`utilisateurs.ajouter()` **ne commit pas** (c'est l'appelant qui le fait, comme les autres
écritures du module) : des comptes de test créés en script, sans `conn.commit()`, semblent
créés — la fonction ne lève rien — et le `/login` les refuse ensuite. Vérifier par un
`authentifier()` **après reconnexion**, pas par l'absence d'erreur.


---

## LES CONSIGNES S'OUVRENT EN FENÊTRE CENTRÉE À LA CONNEXION (journal 2026-09-22)

**Demande** : *que la consigne s'ouvre en fenêtre centrée et un peu plus grande dès que
l'utilisateur accède à son compte, avec une option pour la fermer ; s'il y en a
plusieurs, elles s'ouvrent une à une et l'utilisateur les ferme une à une.*

Jusqu'ici une consigne non lue ne se signalait que par une **bulle** en haut à gauche
(`bulle_consignes`), qu'il fallait remarquer puis cliquer. Une instruction urgente pouvait
donc passer inaperçue toute une session.

### Ce qui a été ajouté

| Fichier | Quoi |
|---|---|
| `serveur_app.py` | **`modale_consignes(sess)`** — la fenêtre : boîte centrée `min(760px, 94vw)`, hauteur plafonnée à 86 vh, corps défilant, fond sombre. Les consignes non lues y sont **toutes empilées** dans le HTML, **une seule affichée** à la fois. |
| | **`_traiter_login`** pose `_consignes_modale` dans la session ; **`_html`** le consomme sur la 1re page servie. |

### Le fonctionnement, et pourquoi il est ainsi

- **Une seule fois, à l'arrivée.** Le drapeau est posé au **login** et retiré par la 1re
  page HTML servie (même s'il n'y a rien à lire). Une consigne qui arrive **pendant** la
  session ne vient donc pas interrompre une saisie : elle se signale par la bulle, comme
  avant. C'est la différence entre « prévenir » et « interrompre ».
- **Une à la fois, fermée une à une.** Le bouton porte **« Fermer et voir la suivante »**
  tant qu'il en reste, **« Fermer »** sur la dernière ; l'en-tête compte
  « Consigne 2 sur 5 ». Trois façons de fermer : le bouton, la **croix ✕**, la touche
  **Échap**. Le **fond n'est PAS cliquable** — sur une pile de consignes, un clic à côté
  en sauterait une sans que l'utilisateur s'en rende compte.
- **Fermer, c'est REPORTER — jamais « j'ai lu ».** Rien n'est envoyé au serveur : la
  consigne reste « à lire » et se rouvre à la prochaine connexion tant qu'elle ne l'est
  pas. Seule l'ouverture de **`/consignes`** vaut accusé de lecture (comportement
  d'origine, inchangé). Le pied de la fenêtre le dit à l'usager.
- **La BULLE reste en place, sous la fenêtre.** `_html` injecte les deux (`bulle_consignes`
  puis la fenêtre par-dessus, z-index 2147482800 < 2147483000) : quand la dernière
  consigne est fermée, la fenêtre se retire et la bulle — compteur intact — prend le
  relais pour rouvrir les consignes **quand l'usager a le temps**.
- **Seulement sur une page servie en 200** : une page d'erreur ne consomme pas le drapeau,
  sinon la fenêtre s'ouvrirait et disparaîtrait avec elle.
- Garde-fou **`_CONSIGNES_MODALE_MAX = 20`** : on n'empile pas 200 fenêtres.
- Le défilement de la page est **bloqué** pendant l'affichage (`body.style.overflow`), et
  **restauré à la valeur d'origine** à la fermeture de la dernière — pas remis à `""` en
  aveugle.

### Vérifié (HTTP + Firefox headless via geckodriver, sur une COPIE de la base, port 8097)

| Contrôle | Résultat |
|---|---|
| Connexion avec 5 consignes non lues | fenêtre ouverte sur la page d'atterrissage (`/traitement`), **« Consigne 1 sur 5 »**, 1 seule visible, **aucune bulle** |
| Boîte **centrée et grande** | 760 × 250 px, centre (683 ; 341) dans une fenêtre 1366 × 682 — le centre exact |
| Fermetures successives | 1→2→3→4→5, libellé du bouton passant à **« Fermer »** sur la dernière, puis fenêtre **retirée du DOM** |
| Après la dernière fermeture | **la bulle est toujours là**, compteur inchangé (« 6 consignes à lire »), **visible et cliquable** (`elementFromPoint` la désigne) |
| Clic sur la bulle → `/consignes` | consignes marquées lues, bulle éteinte ; retour à l'espace : plus de bulle |
| Consigne **reportée** (fermée sans lire) puis reconnexion | la fenêtre **se rouvre** sur la même consigne |
| Croix ✕ et touche Échap | ferment aussi, et font avancer à la suivante |
| Consigne longue (400 mots) | le **corps défile** dans la boîte (`scrollHeight > clientHeight`), la boîte ne déborde pas de l'écran |
| `body.style.overflow` | `hidden` pendant, **restauré** après ; la page redevient utilisable |
| 2e connexion, tout lu | **ni fenêtre ni bulle** |
| 2e page de la même session | plus de fenêtre, **bulle** « N consignes à lire » |
| Une seule consigne | en-tête « Consigne à lire » (pas « 1 sur 1 ») |
| Non-régression | `/consignes` marque toujours tout lu ; envoi/modification/suppression par l'Admin et les Coordonnateurs inchangés ; `/admin`, `/consignes`, `/consignes/nouvelle`, `/journal`, `/manuel`, `/profil` en 200 |

⚠️ **Redémarrage du service requis** pour que ce code soit servi en ligne.

### À retenir

**Une notification qui interrompt et une notification qui rappelle ne se déclenchent pas
au même moment.** La fenêtre modale est justifiée **à l'arrivée sur le compte** — l'usager
n'a encore rien commencé ; la même fenêtre surgissant en pleine saisie de journal serait
une gêne. D'où le drapeau de session posé au seul `login`, et la bulle conservée pour
tout le reste.

**Et fermer une fenêtre n'est pas la lire.** Première version : chaque fermeture valait
accusé de lecture, donc la bulle s'éteignait — une consigne survolée à la connexion
devenait introuvable pour qui n'avait pas le temps de la lire sur le moment. Corrigé avant
déploiement (demande utilisateur) : fermer **reporte**, la bulle demeure, et seule la
lecture sur `/consignes` éteint le rappel. `consignes.marquer_lue`, la route
`POST /consignes/lue` et le helper `_vide` — écrits pour l'accusé de lecture au clic — ont
été **retirés** plutôt que laissés en code mort.

### Piège d'outillage (le même que le 2026-09-20, sous une autre forme)

Le pilotage WebDriver enveloppe le script dans une fonction : `arguments[0]` y donne les
paramètres passés. **Mais si l'on écrit soi-même une IIFE** `(function(){…})()`,
`arguments` désigne celle-ci — **vide** — et le paramètre est `undefined` sans la moindre
erreur. Ici le login se soumettait à blanc et la page testée était en fait `/login` :
rien n'était cassé côté application. Capturer les arguments **avant** l'IIFE
(`var L=arguments[0];(function(){…L…})();`).

---

## L'ADMIN SUPPRIME LES DONNÉES D'UN DISTRICT (dénombrement, VAD, ou les deux) (journal 2026-09-22)

**Demande** : *comme pour la visualisation des dashboards en choisissant le district et le
dashboard à visualiser (Dénombrement ou VAD), donner un choix qui ressemble à cette
opération, qui est la suppression des données (VAD ou Dénombrement, en choix multiple) et
qui va supprimer les données dans la base du dénombrement, de la VAD ou des deux pour le
district choisi. C'est l'Admin qui a le privilège d'exécuter cette opération.* Puis, en
cours de route : *sans oublier qu'il faut supprimer aussi le dossier qui contient la base
de données `*.dta` du district dont on a choisi de supprimer les données.*

Jusqu'ici l'ingestion n'effaçait **jamais rien** (`maj_db.py` : ajoute, modifie, laisse
inchangé). Un district transcrit par erreur, avec un mauvais export ou sur un
questionnaire périmé, ne pouvait donc pas repartir de zéro. C'est désormais le pendant
destructif, **réservé à l'Admin**, calqué sur le choix « district + opération » de
`page_selection`.

### Fichiers

| Fichier | Quoi |
|---|---|
| **`suppression.py`** (nouveau) | Toute la logique + le rendu : le dict `OPERATIONS` (ce que « dénombrement » et « VAD » désignent en tables, en dossier et en comparatifs), `compter`/`details`, `supprimer`, `consigner`, et les deux pages (choix, confirmation). |
| `admin.py` | Lien **« Suppression »** dans la barre de l'espace Admin (`_entete`, clé `suppr`). |
| `serveur_app.py` | `import suppression` ; `GET /admin/suppression` dans `_admin_get` ; `POST /admin/suppression` → **`_admin_suppression_post`** (nouvelle méthode). |

### Ce qui part, et pourquoi c'est en trois catégories et non une

Le district n'est porté que par la table **PARENTE** ; les filles s'y rattachent par
`interview__key`. On supprime donc les filles **par sous-requête sur le parent**, puis le
parent — jamais l'inverse.

| Opération | Parent (colonne district) | Filles (via `interview__key`) |
|---|---|---|
| Dénombrement | `den_menage."district"` | `segment_roster`, `interview__diagnostics` |
| Visite à domicile | `vad_menage."CQ7"` | `vad_membre`, `vad_diagnostics`, `vad_ce` |

**Côté VAD, le district est `CQ7`, pas la colonne `district`** : cette dernière est une
valeur *préchargée* (souvent « ##N/A## », parfois un libellé comme « FIANARANTSOA »). C'est
déjà la clé du périmètre des tableaux de bord (`vad_db._clause_perimetre`) — s'en écarter
ici aurait supprimé le mauvais district, ou rien.

**Le périmètre du district a DEUX sources : la base et le dossier.** Un export se
téléverse et se transcrit *fichier par fichier*. La base garde donc des lignes que la
table parente ne désigne plus — c'est **mesurable** aujourd'hui : sur les 236 lignes
`den_menage` à `district` **NULL**, **22 appartiennent à VOHIBATO** et **12 à LALANGINA**
d'après leurs dossiers téléversés. Un filtre `WHERE district = ?` les laisserait sur
place : district « supprimé » avec, en base, ses diagnostics et ses segments fantômes
(c'est précisément ce que `deploy/supprimer_vavatenina.py` avait dû rattraper à la main,
journal 2026-09-21). `cles_cibles()` complète donc les clés de la base par celles du `.dta`
**ménage du dossier**, en **écartant** celles que la table parente attribue explicitement à
un *autre* district — même règle qu'à l'ingestion (`db_source.cles_hors_district`). Les
`interview__key` circulent par **paquets de 400** (`LOT`), la limite de paramètres SQL
interdisant un `IN (…)` de 1 249 clés.

**Le dossier des `.dta` téléversés part avec** : `UPLOAD_DIR/<code>/` pour le
dénombrement, `UPLOAD_DIR/VAD/<code>/` pour la VAD. Sans cela la suppression serait un
faux-semblant : l'Expert survey retrouve son export sur sa page de transcription et un clic
le réinjecte. `_dossier_sur()` garde le `rmtree` : `realpath` des deux côtés, le dossier
doit être un **enfant direct** de `UPLOAD_DIR[/VAD]` et porter **le code du district**,
sinon on ne supprime rien.

**Les comparatifs RGPH ↔ RSU sont VIDÉS, pas supprimés.** C'est la correction la plus
importante de la session. `comp_taille_menage` et `comp_pyramide`
(cf. `comparaison_rgph_rsu.py`) mettent côte à côte **deux** sources et existent pour les
**120 districts**, même sans une seule interview RSU : leurs colonnes `*_rgph` sont le
recensement 2018. Un premier jet les traitait comme des tables dérivées à supprimer par
`WHERE code_district = ?` — trois défauts d'un coup :

1. cela effaçait **la référence RGPH** du district (irrécupérable sans relancer un script
   sur 2,5 M de lignes) ;
2. dans `comp_taille_menage`, la ligne du **district** porte son code dans `code` et a
   `code_district` **NULL** (seules les lignes de *commune* l'ont rempli) : le filtre
   n'attrapait que les communes et **laissait la ligne du district avec ses valeurs RSU** ;
3. `comp_pyramide` est alimentée côté RSU par **`vad_membre`** — c'est de la **VAD**, pas
   du dénombrement : elle était rattachée à la mauvaise opération.

D'où, à la place, un `UPDATE … SET <colonnes RSU> = NULL` :

| Table | Source RSU | Opération | Clause |
|---|---|---|---|
| `comp_taille_menage` | `segment_roster.taille_menD` | **Dénombrement** | `(niveau='district' AND code=?) OR (niveau='commune' AND code_district=?)` |
| `comp_pyramide` | `vad_membre` M3/M4 | **VAD** | `code_district=?` |

Jamais touchés : `_schema` / `_value_labels` (la **structure** des tables, pas des données
de district — les vider casserait la lecture des 19 autres), le référentiel `zones`, les
comptes, équipes, journaux, consignes, et le RGPH.

### Le parcours : deux temps, un nom à retaper

1. **`GET /admin/suppression`** — cascade Province → Région → District (JS autonome, même
   principe que `admin._cascade_js` mais sans le couplage au formulaire des comptes), deux
   **cases à cocher** (choix multiple), et un **inventaire** de ce qu'il y a à supprimer par
   district : lignes des tables parentes **et** nombre de fichiers `.dta`. L'inventaire lit
   aussi `UPLOAD_DIR`, si bien qu'un district *téléversé mais pas encore transcrit*
   (SOANIERANA IVONGO, BELO SUR TSIRIBIHINA) y apparaît — sinon on ne l'aurait jamais vu.
2. **`POST action=verifier`** — page de confirmation : le décompte **exact, table par
   table**, le chemin et le poids du dossier, les lignes de comparatif qui seront vidées,
   puis un champ où l'Admin **retape le nom du district**.
   `suppression.confirmation_ok` tolère casse, accents et espaces (« fenerive est » passe) :
   on veut un geste délibéré, pas une dictée.
3. **`POST action=confirmer`** — suppression, **un seul commit** (une erreur en route ne
   laisse pas une opération à moitié faite), les **fichiers après le commit** (une erreur de
   disque ne doit pas faire perdre une suppression de données réussie : elle est signalée et
   journalisée à la place), `journal.consigner`, puis **`_vider_cache()`** — sans quoi une
   page en cache resservirait les données effacées.

Chaque suppression laisse une ligne dans les **journaux d'ingestion de `/admin`** :
« Suppression des données » (dénombrement) et « Suppression des données VAD » — c'est le
suffixe `VAD` qui range la ligne dans le bon journal (`journal.phase_evenement`).

### Vérifié (HTTP réel, sur une COPIE de la base ET une COPIE de `DATA_serveur`, port 8098)

`RSU_SQLITE` **et `RSU_UPLOAD_DIR`** pointés sur le scratchpad : la vraie base (6 486
`den_menage`, 1 150 `vad_menage`, 306 comptes) et le vrai `DATA_serveur` ont été
recomptés après coup, **inchangés**.

| Parcours | Résultat |
|---|---|
| Barre de `/admin` | lien **Suppression** présent |
| **VOHIBATO (3306)**, den+vad — le cas des lignes non transcrites | `verifier` annonce **119** et **113** interviews « que seul le dossier rattache à ce district », et **236** `den_menage` / **236** `interview__diagnostics` (214 du district **+ 22** à `district` NULL) ; après `confirmer` : `den_menage` à NULL passe de **236 à 214** — les 22 de VOHIBATO parties, les 214 autres intactes ; supprimé **=** annoncé, table par table |
| `GET /admin/suppression` | **200**, cascade + 2 cases + inventaire (y compris les districts qui n'ont QUE des fichiers) |
| `verifier` FENERIVE EST (5201), den+vad | **200** : 9 747 lignes à supprimer, 13 + 30 lignes de comparatif à vider, dossiers `…/5201` (14 fichiers, 9,0 Mo) et `…/VAD/5201` (16, 20,2 Mo) |
| `confirmer` avec « FENERIVE » (tronqué) | **200**, `<div class="err">` « rien n'a été supprimé » — base et dossiers **intacts** |
| `confirmer` avec « fenerive est » (casse/espaces) | **200** : 9 747 + 1 691 lignes supprimées, les 2 dossiers supprimés, 5201 disparu de l'inventaire |
| Contrôle en base | `comp_taille_menage` reste à **1824** lignes et `comp_pyramide` à **4080** : volet RGPH conservé (15 / 34 lignes), volet RSU à **0** pour 5201 seulement |
| **VAD seule** sur 1106 | 1 369 lignes + `…/VAD/1106` supprimés ; **dénombrement intact** (249 segments, `comp_taille_menage` RSU inchangé, dossier `…/1106` toujours là) |
| Orphelins | `segment_roster` sans parent : **7 avant, 7 après** (préexistants) — la suppression n'en crée pas |
| Aucune case cochée / district non choisi / `action` inconnue | message d'erreur · message d'erreur · **400** |
| District sans rien (AMBALAVAO) | page de confirmation « aucune donnée ni aucun fichier », sans bouton de suppression |
| Rôle **Traitement** (non-Admin), `GET` et `POST confirmer` | **403** les deux fois, district 1406 intact (données **et** dossiers) |
| Dashboards après suppression | `/vue/general` et `/vad/general` sur 5201 (vidé) : **200**, aucune trace d'erreur ; district intact (1406) : **200** |

⚠️ **Redémarrage du service requis** pour que ce code soit servi en ligne (cf.
« Redémarrer sans sudo »).

### À retenir

**Un script ad-hoc déjà écrit est une spécification.** `deploy/supprimer_vavatenina.py`
(suppression manuelle d'un district, périmètre décidé avec l'utilisateur) disait en
commentaire ce que la version générique allait oublier : les clés du **dossier téléversé
mais jamais transcrit**. Relire les scripts de `deploy/` avant de généraliser une
opération qui y a déjà été faite une fois à la main. (Son autre geste — supprimer de
`agent` les codes devenus sans données — n'a **pas** été reprise : `agent` est un
référentiel d'équipe, alimenté par `affectation_agents.py` / `charger_ce_vad.py`, pas une
donnée de collecte. À décider explicitement si le besoin revient.)

**Une table « dérivée » n'est pas forcément à nous.** Le réflexe « c'est un agrégat du
dénombrement, il part avec » était faux : `comp_*` porte aussi le RGPH, et sa maille
(ligne district à `code_district` NULL) ne se devine pas depuis le nom des colonnes. Avant
d'inclure une table dans une suppression, **relire le SQL qui la fabrique** — ici
`comparaison_rgph_rsu.py` disait en trois lignes que la source RSU de `comp_pyramide` est
`vad_membre`, donc la VAD, et non le dénombrement.

Corollaire : quand une même table mélange deux sources, l'opération juste n'est pas
`DELETE` mais **`UPDATE … = NULL` sur les colonnes de la source retirée**.

---

## BASE DE PRÉCHARGEMENT : des LIBELLÉS, et le LOGIN DU CE enfin renseigné (journal 2026-09-22)

**Demande** : *la base de préchargement devrait ressembler à ceci [classeur de référence,
feuille « nouveau », 19 colonnes, FENERIVE EST] : la région, district, commune, fokontany,
on ne prend pas le code mais les libellés. Et dans Ensemble la base n'a pas renseigné le
login du CE.*

### 1. Libellés au lieu des codes

`prechargement.py` écrivait les **codes** déduits du code fokontany à 8 chiffres
(`_codes_hierarchie`) : `52`, `5201`, `520101`, `52010101`. Le fichier de référence porte
des **libellés** — et le référentiel `zones` les a exactement, à l'identique des value
labels du questionnaire (vérifié sur FENERIVE EST) :

| Colonne | Avant | Après | Source |
|---|---|---|---|
| `region` | `52` | `ANALANJIROFO` | `region.nom` |
| `district` | `5201` | `FENERIVE EST` | `district.nom` |
| `commune` | `520101` | `AMBATOHARANANA` | `commune.nom` |
| `fokontany` | `52010101` | `AMBODIHASINA_52010101` | `fokontany.nom` (le nom PORTE le code) |
| `fkt_recherche` | value label | **le même libellé** que `fokontany` | idem |

Nouvelle fonction **`_libelles_zones(conn, code_district)`** : deux requêtes (communes du
district, fokontany du district) + `zones.libelles_district`, donc **quatre libellés
résolus en mémoire**, pas une requête par ligne. Les codes continuent d'être lus depuis
`den_menage` : ils servent de **clé** vers `zones`, ils ne sont simplement plus écrits.
Repli en cascade : référentiel → value label du questionnaire → le code lui-même, pour
qu'une zone absente du référentiel ne **vide** pas la colonne.

Le référentiel est préféré aux value labels **parce qu'il ne dépend pas de la version du
questionnaire téléversé** et qu'il couvre les 20 256 fokontany du pays.

Effet secondaire voulu : `charge_agents_*.xlsx` (feuilles *Par_agent* / *Par_segment*)
affiche désormais `SOANIERANA IVONGO` / `AMBAHINKARABO_52050101` au lieu de `520501` —
c'est `_com` / `_fktnom` qui portent les libellés. Vérifié sans homonymes : aucun couple
(district, nom de commune) ni (commune, nom de fokontany) n'est en double dans `zones`,
donc l'agrégation de l'équilibrage reste exacte.

`IdeFKT_recherche` a été **retirée** de `COLS_NOUVEAU` : le fichier de référence a 19
colonnes, pas 20, et cette colonne était toujours vide.

### 2. Pourquoi le CE sortait vide — et d'où il vient vraiment

`CE` était dérivé de `agent.login_ce` via `equipes.agents_et_chefs`. Or **`agent.login_ce`
est vide pour 3 867 des 4 422 agents** : les agents *découverts à la transcription des
diagnostics* sont créés avec `login_ae = nom_prenom_ae = 'EQ2_FNRVE_0727'` et **aucun
chef**. Pour FENERIVE EST, les 502 agents sont tous dans ce cas — la jointure réussissait
(502/502) et renvoyait `NULL`. `chef_equipe` ne contient, elle, aucun chef `FNRVE`.

La vraie source est **`base_login_ce.dta`**, un fichier de l'export Survey Solutions qui
donne `interview__key → responsible__name` pour le **rôle 2** (chef d'équipe) — l'exact
pendant de `vad_ce` pour la VAD. Il n'est pas transcrit en base (il n'est pas dans
`db_source.FICHIERS`) mais il **reste dans `UPLOAD_DIR/<code>/`** avec le reste du
téléversement. Nouvelle fonction **`_ce_du_dossier(code_district, log)`** : le lit, filtre
sur `responsible__role == 2` quand la colonne est là (un login d'*enquêteur* glissé dans
la colonne CE passerait inaperçu), et renvoie `{}` s'il est absent ou illisible —
`agent.login_ce` reste alors le **repli**.

**`_note_ce()` le dit sur la page**, par district : bandeau vert « `base_login_ce.dta` est
présent (921 interviews rattachées) — la colonne CE sera renseignée », ou bandeau orange
qui **nomme le fichier à inclure dans l'export**. Sans ça, la colonne sortait vide en
silence. Le journal de génération ajoute une ligne : `CE renseigné sur N/M ménages`.

⚠️ **Un téléversement n'efface pas le dossier** (`shutil.move` fichier par fichier,
`makedirs(exist_ok=True)`) : un `base_login_ce.dta` déjà là survit à un export qui ne le
contient pas. Mais comme les **3 `.dta` requis** doivent être présents à la racine, on ne
peut pas téléverser ce seul fichier : il faut refaire le téléversement du dossier complet
en l'incluant.

### Vérifié — la sortie est IDENTIQUE au fichier de référence

Sur une COPIE de la base (`RSU_SQLITE`), le dossier **5205 (SOANIERANA IVONGO)** transcrit
pour le test car c'est le seul qui porte `base_login_ce.dta`, puis comparaison de la
feuille `nouveau` de FENERIVE EST au classeur de référence, **colonne par colonne sur les
5 398 clés `interview_keyden` communes** :

| Contrôle | Résultat |
|---|---|
| En-têtes (19 colonnes, ordre) | **identiques** |
| 17 colonnes sur 19 | **0 écart** sur 5 398 lignes (`region`, `district`, `commune`, `fokontany`, `fkt_recherche`, `nom_cm`, `taille_men`, GPS, `code_den`, `_responsible`, `_quantity`, `typemen`, `mode_enreg`, `nom_projet`, `interview_keyden`…) |
| `CQ17_preload` / `description` | 54 et 24 écarts — la référence porte `##N/A##`, nous écrivons **vide** (apurement `_sans_na`). Écart **assumé** : `##N/A##` s'afficherait tel quel à l'agent sur sa tablette |
| 5 412 lignes de référence vs 5 398 générées | les 14 manquantes sont des fokontany `520605xx` = **VAVATENINA**, absents de la base : des interviews saisies **hors zone**, écartées à l'ingestion (`cles_hors_district`). Notre sortie est plus juste |
| CE (5205, dossier avec `base_login_ce.dta`) | **48 641 / 48 641** ménages renseignés (`CE_SNRVG_013`…) |
| CE (5201, dossier sans le fichier) | vide + **bandeau orange** nommant le fichier à inclure |
| HTTP réel (port 8098, compte Traitement de 5205) | `GET /traitement/prechargement` **200** avec le bon bandeau · `POST` → **ZIP 9,2 Mo**, feuille `Ensemble` avec libellés et `CE = CE_SNRVG_013` |
| `charge_agents` en mode `equilibre` | 244 agents, ~220 ménages chacun, communes et fokontany **nommés** |

### À retenir

**Une jointure qui réussit peut renvoyer du vide.** `agent` contenait bien les 502 agents
du district (502/502 trouvés) : seule la colonne `login_ce` était nulle. Le diagnostic
« la jointure ne matche pas » aurait envoyé chercher au mauvais endroit — c'est en
comptant `login_ce IS NULL` (3 867/4 422) que la cause apparaît. **Compter les valeurs
nulles de la colonne qu'on lit, pas seulement les lignes de la table qu'on joint.**

Et : **un fichier de l'export qu'on ne transcrit pas reste une source de données.**
`base_login_ce.dta` dormait dans `UPLOAD_DIR` depuis le début ; l'en-tête du module
affirmait pourtant que « la base web ne contient pas `base_login_ce.dta` » — vrai pour la
*base*, faux pour le *serveur*.

### Reste à décider

Le CE dépend du dossier téléversé. Pour le rendre indépendant, il faudrait **transcrire
`base_login_ce.dta` en base**, dans une table `den_ce` (`interview__key`, `CE`) calquée sur
`vad_ce` — non fait, hors demande. À trancher si le fichier doit survivre à un nettoyage
de `UPLOAD_DIR` (y compris par la suppression par district ajoutée ce jour, qui efface le
dossier).

---

## PRÉCHARGEMENT : un REGISTRE en base, le choix des fokontany (journal 2026-09-26)

**Demande** : transposer le do-file « RSU VAGUE 2 - PRECHARGEMENT SURVEY SOLUTIONS »
(un par district) : un ménage envoyé une fois n'est **jamais** renvoyé, sans avoir à
réimporter les anciens fichiers Excel ; pouvoir choisir les fokontany à précharger.

### Décisions de l'utilisateur
1. Tout ce qui précède était du **test** : le registre **part vide**, pas
   d'initialisation depuis d'anciens fichiers (le `0_DEJA_ENVOYES_AVANT` du do-file
   n'est pas repris).
2. **Même filtre de statut que le do-file** : interviews 100 / 120 / 130 seulement. Une
   interview rejetée n'entre pas au registre et sera préchargée à une sortie ultérieure,
   une fois approuvée.
3. On peut **annuler le dernier lot**, **retélécharger** n'importe quel lot, et
   télécharger le **fichier total** des préchargements.
4. La **suppression des données d'un district** (Admin, dénombrement) efface **aussi**
   son registre (phase de test). La page de confirmation le signale.

### Ce qui a été fait (`prechargement.py`)
- **Tables** (créées au démarrage, `prechargement.creer_tables` dans `preparer()`) :
  `prechargement_lot` (une ligne par sortie : district, date, auteur, mode, fokontany
  retenus ou `TOUS`, effectifs, version) et `prechargement_ensemble` / `_nouveau` /
  `_efokontany` = les **trois feuilles à l'identique**, clé `interview_keyden`, plus les
  méta `lot_id`, `code_district`, `code_fokontany`, `segment`, `rang` (pour
  reconstituer le classeur ET la charge par agent dans le même ordre).
- `generer_lot()` remplace `generer_zip()` : charge → filtre fokontany → retire le
  **registre** (`prechargement_ensemble`, qui fait foi) → affectation → **inscrit le lot
  dans la même transaction**. Rien à précharger → « AUCUN NOUVEAU MENAGE ».
- `_charger_menages` filtre `interview__status` (`STATUTS_OK`) ; `_ligne_vide` factorise
  l'apurement, partagé avec `fokontany_disponibles()` (effectifs total / déjà / reste par
  fokontany, groupés par commune, pour la page).
- `zip_lot`, `xlsx_total`, `annuler_dernier_lot` (refuse tout lot qui n'est pas le
  dernier).
- **Retiré** : l'exclusion par téléversement de fichiers (`_keyden_precedents`,
  `_resume_rapport`, champ « Exclure les ménages déjà envoyés »).

### Serveur (`serveur_app.py`)
`POST /traitement/prechargement` (champs `portee=tous|choix`, `fokontany` multiples,
`mode`) → **303** vers `/traitement/prechargement?lot=<id>`, dont la page lance le
téléchargement (**PRG** : rafraîchir ne régénère pas de lot). `GET …/lot?id=` (ZIP,
borné au district de l'utilisateur, 404 sinon), `GET …/total.xlsx`,
`POST …/annuler`. Rôle Traitement uniquement (Admin → 403).

### Suppression (`suppression.py`)
`OPERATIONS["den"]["par_district"]` : les 4 tables du registre, supprimées par
`code_district`, comptées sur la page de confirmation, avec un bandeau d'avertissement.

### Vérifié (COPIE de la base, serveur de test port 8098)
FENERIVE EST : 7 283 ménages préchargeables ; lot 1 sur 2 fokontany = 161 (= attendu),
lot 2 « tous » = 7 122, 3ᵉ sortie → « AUCUN NOUVEAU MENAGE » ; lot 1 + lot 2 = total.
ZIP d'un lot rejoué : 19 colonnes du fichier de référence, libellés géographiques.
Total : Ensemble 7 283 / nouveau 7 283 / e_fokontany 0. Annulation d'un lot ancien
refusée, du dernier acceptée (les ménages redeviennent à précharger). HTTP : choix vide
refusé, lot inconnu 404, Admin 403 sur les routes Traitement ; suppression Admin du
district 5201 → registre à 0. Le JavaScript de la page (bascule de la liste, « Toute la
commune », téléchargement automatique) n'a **pas** été exécuté dans un navigateur.

⚠️ **Redémarrage du service requis** (création des tables + nouvelles routes).

## PRÉCHARGEMENT : DEUX formats géographiques au choix — codes OU libellés (journal 2026-09-26)

Retour en arrière puis généralisation du changement du 2026-09-22 (« des LIBELLÉS ») :
la base de préchargement se produit désormais dans **DEUX formats**, au choix, pour les
4 colonnes `region` / `district` / `commune` / `fokontany` :
- **`code`** : `52 / 5201 / 520109 / 52010904` ;
- **`libelle`** : `ANALANJIROFO / FENERIVE EST / MIORIMIVALANA / MIORIMIVALANA_52010904`.

Dans les DEUX formats : **`fkt_recherche` = nom du fokontany** (recherche par libellé) et
le fichier **`charge_agents_<version>.xlsx` reste en NOMS** (résumé RH lisible, méta
internes `_com` / `_fktnom`). Seules les 4 colonnes du fichier de base changent.

### Mise en œuvre (`prechargement.py`)
- `FORMATS_GEO` = `("code", "libelle")`, `LIBELLE_FORMAT`, `_format_ok()`.
- **`_rendre_geo(conn, code_district, feuilles, format_geo)`** applique le format
  AVANT l'écriture. Clé de vérité = le **code fokontany 8 chiffres** (`_fkt_code`, ou la
  méta `code_fokontany` relue du registre) : region/district/commune s'en déduisent
  (`//1e6`, `//1e4`, `//100`). ROBUSTE quel que soit le contenu des colonnes stockées —
  donc les **lots créés avant** (colonnes en libellés) se retéléchargent aussi bien en
  codes qu'en libellés. Fait aussi `fkt_recherche`/`_com`/`_fktnom` = noms.
- `_charger_menages` produit la forme **canonique** (4 colonnes = CODES, `fkt_recherche`
  = nom). `_lignes_registre` expose désormais la méta `code_fokontany` comme `_fkt_code`.
- `zip_lot(..., format_geo)` et `xlsx_total(..., format_geo)` appellent `_rendre_geo` et
  **suffixent le nom de fichier** (`_codes` / `_libelles`) pour distinguer les deux ZIP.
- UI `page_prechargement` : **radio « Format géographique »** sur le formulaire de
  génération ; dans l'historique, chaque lot a **deux liens ZIP** (Codes · Libellés) et
  le **fichier TOTAL** a deux boutons. La confirmation post-génération télécharge au
  format choisi (repli sur l'autre proposé).

### Serveur (`serveur_app.py`)
`GET …/lot?id=&fmt=`, `GET …/total.xlsx?fmt=`, la page lit `fmt` (→ `format_ok`), le POST
lit `format_geo` et le propage dans la redirection PRG (`&fmt=`).

### Vérifié (COPIE de la base, district 5201 FENERIVE EST — lots préexistants en libellés)
`xlsx_total` et `zip_lot` en `code` → `52/5201/520113/52011306`, `fkt_recherche` = nom ;
en `libelle` → noms ; **charge = noms dans les deux cas** ; noms de fichiers distincts
(`_codes`/`_libelles`). Forme canonique à la génération confirmée (colonnes = codes,
`fkt_recherche`/`_com`/`_fktnom` = noms, `_fkt_code` = code). Le JavaScript de la page
(auto-téléchargement) n'a **pas** été exécuté dans un navigateur.

⚠️ **Redémarrage du service requis** pour être servi.

## MISE À JOUR ciblée du référentiel `zones` : 31 districts (journal 2026-09-26)

À partir du fichier Google Sheets fourni (« Base compilée », copié dans le projet sous
`MAJ_ZONES_31DISTRICTS.xlsx` : 9 286 fokontany, 469 communes, **31 districts**, 11 régions ;
colonnes Région / Code+Libellé District / Code+Libellé Commune / Code+Libellé Fokontany —
**pas** de code région/province, déduits : région = district//100, province = région//10).

### Script `maj_zones_31districts.py` (séparé de `zones.py`)
`zones.charger_excel_vers_db` recharge TOUT le pays ; ce script ne touche QUE les 31
districts du fichier (les 89 autres intacts). **Sémantique = REMPLACEMENT** (décision
utilisateur : « prendre exactement le fichier ») : pour chaque district, on supprime ses
communes/fokontany puis on réinsère ceux du fichier ; noms district/région mis à jour.
La hiérarchie retenue est celle des **colonnes** (commune/district de la ligne), pas celle
déduite des codes. `commune."nombreMenage"` préservé par code. CLI : `--dry-run`, ou
`python maj_zones_31districts.py [fichier.xlsx]`. Idempotent (rejouable).

### Anomalies du fichier (rapport `anomalies_zones_31districts.xlsx` envoyé à l'utilisateur)
Un code fokontany « normal » commence par le code de sa commune. Écarts trouvés :
- **543** fokontany : même district, mais code commune différent (renumérotation) ;
- **52** fokontany : code pointant vers un **AUTRE district** (contamination probable,
  ex. commune ANALAMARY/610108 d'Ambovombe contenant `62030404…` = Amboasary).
Aucun doublon de code fokontany, aucune commune multi-district, **aucune collision** avec
les 89 autres districts. **Décision : TOUT charger tel quel** (52 + 543 inclus). ⚠️ Le
rapport et le préchargement DÉDUISENT commune/district du code fokontany
(`fktcode[:6]`, `_codes_hierarchie`) : pour ces lignes, la déduction rattachera au mauvais
endroit — l'intégrité des TABLES `zones` (FK par colonnes) reste correcte, mais les codes
gagneraient à être corrigés à la source.

### Appliqué à la vraie base (2026-09-26), après sauvegarde `rsu_local.sqlite.bak_<horodatage>`
Avant→après (31 districts) : communes 456→469, fokontany 7 352→9 286. Base entière :
120 districts, **1 717** communes, **22 190** fokontany, **0 orphelin** (fokontany→commune
→district→région tous résolus). 34 fokontany à **9 chiffres** (ex. `610106001`) chargés.
Testé d'abord sur COPIE (mêmes chiffres). **Pas de redémarrage nécessaire** : `zones` est
lu en direct depuis la base à chaque requête. ⚠️ Un futur `python zones.py` (rechargement
complet FKT_ampiasan_SS) écraserait ces 31 districts → relancer le script après, ou mettre
à jour le fichier maître.

### Téléchargement du rapport d'anomalies (réservé Admin)
Le rapport `anomalies_zones_31districts.xlsx` (généré par `anomalies_zones.py`, présent à la
racine du projet) est servi par une route **`GET /admin/anomalies-zones.xlsx`**
(`serveur_app._admin_get`, garde `_admin_ok` → 403 si non-Admin, redirection /login sans
session), et un lien **« Référentiel géographique → Télécharger le rapport »** a été ajouté
au tableau de bord Admin (`admin.page_admin`). Testé en HTTP réel (port 8098, COPIE de la
base, comptes temporaires) : Admin → **200** + xlsx (37 919 o, `PK…`) ; non-Admin → **403** ;
sans session → 303 /login. ⚠️ **Redémarrage du service requis** pour servir la nouvelle route.

## RAPPORT DE MISSION INDIVIDUEL (un Word par utilisateur) (journal 2026-09-26)

Besoin : pour chaque utilisateur des **4 districts** (1101, 1106, 5201, 5206), un rapport
Word compilé **à partir de SON journal de bord**, rangé dans
`rapport_mission/<code_district>/rapport_<login>.docx`, ressemblant au modèle de district
(le doc fourni par l'utilisateur). Génération **LOCALE, sans IA** (décision utilisateur :
« c'est vous qui faites la génération »), **mise à jour à la demande** (l'utilisateur me
demande par un prompt de relancer), et **téléchargement par chaque utilisateur** de SON
rapport depuis « Mon journal de bord ».

### `rapport_mission_users.py` (générateur, lancé par l'assistant)
- Réutilise le rendu du modèle : `rapport_word.construire_docx` (page de garde INSTAT,
  KPI, graphiques, annexe des pièces jointes). Le **texte** des 7 sections est une
  compilation FACTUELLE du journal (pas d'IA → aucune donnée ne sort du serveur).
- `synthese_locale`/`collecter` de `rapport_mission` ont reçu un paramètre **`login=`**
  (rétrocompatible) pour borner à un utilisateur ; `pieces_jointes` renvoie alors ses
  seules pièces.
- `rapport_word.construire_docx`/`_page_de_garde` ont reçu **`sous_titre=`** (défaut = le
  texte IA existant, inchangé) ; le générateur y met « compilé… sans intelligence
  artificielle ».
- API : `generer_un(conn, login)`, `generer_tous(conn)`, `trouver_rapport(login, code)`.
  CLI : `python rapport_mission_users.py` → (re)génère TOUS les utilisateurs des 4
  districts (≈1m40 pour 48 rapports, 175 Mo au total, pièces images embarquées).

### Téléchargement (chacun le sien) — `serveur_app.py`
Route **`GET /journal/rapport.docx`** (placée AVANT les gardes de rôle, comme les autres
routes /journal) : sert `rapport_<login-connecté>.docx` via `_octets` ; si absent, message
explicatif (404) au lieu d'un 404 brut. Bouton **« ⬇ Télécharger mon rapport (Word) »**
ajouté sur la page « Mon journal de bord » (`page_journal_ecrire`).

### Mise à jour
**À la demande** : quand l'utilisateur le demande, relancer `python rapport_mission_users.py`
(pas de cron). Régénère tous les rapports à partir des journaux du moment.

### Vérifié
Rendu d'un rapport : page de garde INSTAT + KPI + 2 graphiques + 7 sections
(Introduction → Annexe journaux) + annexe pièces (25 images). HTTP réel (port 8098, COPIE,
comptes temporaires) : login écrivain → **200** + docx (`PK…`, Content-Disposition
`rapport_<login>.docx`) ; utilisateur sans rapport → **404** message ; sans session → 303 ;
bouton présent sur /journal. ⚠️ **Redémarrage du service requis** (route + bouton + import).

---

## VAD : COUVERTURE PAR AGENT — affectation du préchargement ↔ interviews (journal 2026-09-26)

**Demande** : pour le suivi de chaque agent, un tableau *Nom/login · Ménages affectés ·
Affectés interviewés · Couverture · Non affectés interviewés*, l'affectation venant de la
**base de préchargement** ; au clic sur un agent, la liste des ménages qui lui sont
affectés et qu'il n'a pas encore interviewés. Ménages attendus = ménages du dénombrement.

### La clé : `interview_keyden`, vérifiée sur les données
`interview_keyden` = clé de l'interview du DÉNOMBREMENT + « - » + rang du ménage dans le
segment (3 chiffres). Présente dans le registre du préchargement
(`prechargement_ensemble`, qui fait foi, agent dans `ENQ`) ET dans `vad_menage`. Mesuré :
la clé VAD se retrouve au dénombrement à ~100 % dans la plupart des districts, et sur les
241 ménages rapprochables du registre l'agent du préchargement = l'agent de l'interview
(241/241). ⚠️ 1 482 interviews VAD portent `##N/A##` (surtout 1106, 6306) : non
rattachables, comptées à part (« interviews sans clé »).

### Règles (décidées avec l'utilisateur)
- **Affectés interviewés** = interviewés PAR L'AGENT AFFECTÉ ; couverture = ÷ affectés.
- Affecté à A, interviewé par B : « interviewé par un autre agent » chez A (plus à faire),
  « non affecté interviewé » chez B. Le non-affecté se ventile en *affecté à un autre agent*
  / *hors préchargement*.
- **Statuts Survey Solutions ventilés, pas filtrés** : 130 Approuvé siège, 120 Approuvé
  superviseur, 100 Terminé, 65 Rejeté superviseur, **125 Rejeté siège** (et non superviseur :
  vérifié dans `_value_labels`), autre = en cours. Ménage interviewé plusieurs fois → statut
  le plus avancé.
- **Un ménage compte une fois** ; les doubles interviews sont listées à part (test),
  « Préchargement suspect » au-delà de `SEUIL_DOUBLON_DEN` (3) interviews.
- Seuls les districts ayant un registre sont comparés ; les interviews des autres sont
  comptées « hors registre » (sinon tout passerait pour « non affecté »).
- Le « reste à faire » = affecté et interviewé par PERSONNE.

### Mise en œuvre
- `vad_core` : `_affectations` (registre borné au périmètre par `code_fokontany`,
  commune = //100), `_vad_par_keyden` (TOUTE la VAD + agent de `vad_diagnostics` — une
  interview à zone mal saisie reste reconnue), `_sec_couverture_agents`, `_doubles`,
  `_requete` (rollback PG si table absente). Clé `couverture` de `agrege()`, calculée
  seulement pour `section in ("agents","export")` (lit tout le registre et toute la VAD).
  Codes agent BRUTS (`agent_code`) capturés avant le remplacement par les noms.
- `vad_web` : `_p_couverture` en tête de « Par agent » (KPI + tableau, agent cliquable →
  `/vad/agents?agent=<code>#reste`), `_p_couv_detail`, `_p_doubles`.
- `serveur_app._vad_get` : `agg["agentSel"] = ?agent=` (simple filtre d'affichage sur un
  calcul déjà borné au périmètre ; code inconnu → message).
- `export_vad` : feuilles 7-9 **Couverture par agent**, **Reste à interviewer**,
  **Doubles interviews** (`section="export"`).
- `manuel_roles` : puce « Par agent » du tableau de bord VAD.

### Vérifié (COPIE de la base, port 8098, comptes de test dans la copie)
Traitement 5206 : `/vad/agents` 200 (214 Ko, 1,5 s), 527 affectés / 177 interviewés /
33,6 %, liens agent ; détail EQ2S_VVTN_0249 = 10 affectés, 1 interviewé, **9 lignes** ;
`?agent=<script>` échappé (message « aucun ménage affecté ») ; export 200 (9 feuilles) ;
autres sections 200. National `?district=tout` : 200 (1,1 Mo, 7,8 s), districts comparés
1101/5201/5206/6303, 202 interviews hors registre signalées ; 3306 : « indisponible » +
doubles. 1101 : 2 doubles interviews.

### À savoir
- Le registre n'existe que depuis le 2026-09-26 (lots de test) : les couvertures actuelles
  sont basses parce que les VAD ont été préchargées AVANT le registre (1101 : 0 affecté
  interviewé, 261 « hors préchargement »). Elles deviendront justes avec les vrais lots.
- ⚠️ **Redémarrage du service requis** pour être servi.

## Export VAD, feuille « Global » : COUVERTURE et RSU ↔ RGPH-3 PAR COMMUNE (journal 2026-09-26)

**Demande** : dans le « Détail par commune » de la feuille Global, ajouter ménages attendus
(dénombrés), ménages interviewés, couverture, taille des ménages RSU / RGPH-3 / écart,
rapport de masculinité RSU / RGPH-3 / écart.

- `vad_core._couverture_communes` (clé `couvCommune` de `agrege`) : attendus =
  `_denombres_par_commune` (lignes `segment_roster` rattachées à `den_menage.commune`, MÊME
  base que `_couverture` → le total égale « Ménages dénombrés » de la synthèse) ;
  interviewés = ménages VAD de la commune (CQ8), **un `interview_keyden` compté une fois**
  (les sans-clé comptés chacun) ; taille RSU = membres ÷ ménages ; masculinité RSU =
  `_masculinite` (âges renseignés, règle de `_sec_demographie`) ; RGPH-3 : taille
  `rgph.parCommune`, masculinité `rgph.masculiniteCommune` (nouvelle requête dans
  `_sec_rgph`, `rgph_age_commune` groupé par `cc_rsu`, `sexe`). Écart = RSU − RGPH-3.
  Les communes dénombrées sans aucune VAD figurent avec 0 interviewé. Tri : la moins
  couverte d'abord.
- `export_vad._detail_communes` remplace l'ancien tableau commune (Ménages / Membres /
  Taille) ; le détail par fokontany est inchangé.
- Vérifié : 6305 → total 7 472 attendus (= synthèse), 1 467 interviewés (1 525 interviews),
  19,6 % ; masculinité totale RSU 92,3 = page Démographie, RGPH 96,7 = `rgph.masculinite`.
- ⚠️ La synthèse garde son « taux de couverture » sur les INTERVIEWS (20,4 % à 6305) ;
  le tableau commune compte les MÉNAGES (19,6 %). Redémarrage du service requis.
- (même jour) En-tête du tableau commune sur **deux lignes** : groupes fusionnés « Taille
  moyenne des ménages » et « Rapport de masculinité », chacun en colonnes RSU | RGPH-3 |
  Écart (RSU − RGPH-3).

## Test de qualité globale (A1) : la couverture se rapporte au DÉNOMBREMENT (journal 2026-09-26)

**Demande** : « tout ce qui est couverture prend le dénombrement comme référence ».
`vad_qualite_base.calculer` prenait les ménages attendus dans `commune."nombreMenage"`
(projection RGPH-3 2025). Désormais : attendus = `vad_core._denombres_par_commune`
(import local, `vad_core` important ce module) ; enquêtés = ménages DISTINCTS
(`interview_keyden` une fois), toutes interviews y compris rejetées — même règle que le
détail commune de la feuille Global. Les communes dénombrées sans interview figurent à 0 %
dans le tableau ; l'indicateur A1 (rapport max/min) ne porte que sur les communes visitées
et compte les autres à part (sinon rapport infini). Libellés « attendus » → « dénombrés »
(page, graphique, feuille Excel, qui gagne un taux sur la ligne Total).
Vérifié 6305 : 28 communes, 1 466 / 7 472 = 19,6 %, A1 = 108× (alerte). Le 1 ménage
d'écart avec la feuille Global (1 467) est une interview sans code commune.
La couverture du tableau de bord VAD (`vad_core._couverture`) prenait déjà le dénombrement.

## Synthèse Global sur les MÉNAGES + feuille « Écart par agent » refaite (journal 2026-09-26)

- `vad_core._nb_menages` : la synthèse (`global.couverture`, aussi affichée sur la Vue
  globale du tableau de bord) compte les ménages DISTINCTS (`interview_keyden` une fois),
  comme le détail commune et le test de qualité globale. 6305 : 20,4 % → 19,6 %.
- Feuille Excel **« Écart par agent »** : une ligne par AGENT × DATE pour **TOUS** les
  agents, déclaration saisie ou non (avant : un message si personne n'avait déclaré).
  Colonnes : Agent (AE), Login, Chef d'équipe, Date, Ménages déclarés (« — » = pas de
  déclaration), Arrivés au serveur (interviews datées), Écart (déclaré − arrivé), puis une
  colonne par statut (approuvé siège / superviseur, terminé, rejeté superviseur / siège,
  en cours). Sous-total par agent (écart sur les seuls jours déclarés), total général,
  mention des interviews sans date. Calcul `vad_core._sec_ecart_dates` (clé `ecartDates`,
  section « export » seulement). La page « Par agent » du tableau de bord garde sa
  synthèse (`_sec_ecart_declaration`) inchangée.
- Vérifié 5201 (420 agents, 1 018 lignes) et 6305 (330 agents) ; déclarations simulées :
  déclaré 20 / arrivé 15 → écart 5 ; jour déclaré sans arrivée → écart = déclaré ; agent
  déclarant sans aucune donnée présent. Export ≈ 10-12 s par district.

## Nom du classeur VAD (journal 2026-09-26)
`export_vad.nom_fichier(districts)` → **`Rapport_VAD_<code district>_<AAAAMMJJ>_<HHMM>.xlsx`**
(ex. `Rapport_VAD_6305_20260926_1745.xlsx`) ; plusieurs districts → codes joints par
« - », tout le pays → `TOUS`. `_vad_export_get` passe le périmètre effectif.
Même format pour le dénombrement (demande utilisateur) : `export_rapport.nom_fichier(code)`
→ **`Rapport_DEN_<code district>_<AAAAMMJJ>_<HHMM>.xlsx`** (remplace
`Rapport_RSU2026_<nom du district>.xlsx`, route `/export/rapport.xlsx`).
