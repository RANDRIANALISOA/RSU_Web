/*********************************************************************
 * Objectif : TRAITEMENT DE LA BASE DENOMBREMENT RSU/e-fokontany
 *********************************************************************/
 
 *INSTRUCTIONS AVANT DE LANCER LE DOFILE ENTIER

 *Pour afficher les résultats d'un seul coup
set more off
*Pour vider complètement la mémoire de STATA
clear all

*Creer les différents dossiers dans C:
capt mkdir "C:\TRAITEMENT RSU_e-fokontany"
capt mkdir "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS"
capt mkdir "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS"
capt mkdir "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS\BASE .RAR"
capt mkdir "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS\DOFILE"
capt mkdir "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS\BASE BRUTE"
capt mkdir "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS\BASE APUREE"
capt mkdir "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS\BASE RAPPORT"


*macro global pour faciliter les enregistrements et les utilisations des fichiers créés
	global path "C:\TRAITEMENT RSU_e-fokontany\VAD_20_DISTRICTS" //Repertoire principal
	global brute "$path\BASE BRUTE"
	global apuree "$path\BASE APUREE"
	global erreur "$path\BASE ERREUR"
	global rapport "$path\BASE RAPPORT"
	
	global errjournal="$erreur\"+string(year(today()))+strofreal(month(today()),"%02.0f")+string(day(today()))+"_SUPTECH"
	capture mkdir "$errjournal"
    global errjournal_survey="$erreur\"+string(year(today()))+strofreal(month(today()),"%02.0f")+string(day(today()))+"_SURVEY"
	capture mkdir "$errjournal_survey"
	global errjournal_hist="$erreur\"+string(year(today()))+strofreal(month(today()),"%02.0f")+string(day(today()))+"_HISTORIQUE_BASE_ERREUR_STATA"
	capture mkdir "$errjournal_hist"
	
	global version=string(year(today()))+strofreal(month(today()),"%02.0f")+string(day(today()))+"_"+strofreal(hh(now()),"%02.0f")+"H"
 

*Macro utile pour tabout: police en gras; les nombres avec une virgule comme séparateur de milliers,...	
global form_all dpcomma font(bold) wide (9) style(xlsx) 



*************************************************************************************************************************************************
*******************************************************************BASE LOGIN CE*****************************************************************
*************************************************************************************************************************************************

use "$brute\interview__actions", clear
keep if action==0
keep interview__key responsible__name responsible__role
duplicates report interview__key
duplicates drop interview__key, force
gen CQ2=responsible__name
save "$brute\base_login_ce_vad" , replace



*************************************************************************************************************************************************
*******************************************************************BASE MENAGE*******************************************************************
*************************************************************************************************************************************************

use "$brute\rsuefkt_25_rN_pil", clear


merge 1:1 interview__key using "$brute\base_login_ce_vad", keepusing(CQ2)
keep if _merge==3

drop _merge



**fusion avec la base interview__diagnostics pour avoir les codes des agents
merge 1:1 interview__id using "$brute\interview__diagnostics", keepusing(responsible interview__status)
keep if _merge==3
drop _merge
gen CQ1=responsible
duplicates report interview__id

*Garder les entretiens completés ou approuvés
keep if interview__status==100 | interview__status==120

keep if Perm_indiv==1 | Perm_rsu==1

*gen err_double=_n

**NOUVEAU MENAGE**

gen nouveau = 2
replace nouveau = 1 if household_id == "##N/A##"| household_id == "Nouveau"
lab def nouveau 2 "Ménage enregistré dans e-fokontany" 1 "Nouveau ménage" ,modify
lab val nouveau nouveau
lab var nouveau "Statut ménage"

/*
**fusion avec la base interview__actions pour avoir le statut(rejet...)
merge 1:m interview__id using interview__actions, keepusing(action)
lab list action
drop if action==8
duplicates drop interview__id, force
*/

forvalue i=0/18{
    replace M1a__`i'="" if M1a__`i'=="##N/A##" 
}

**Dates et heures**

gen heure_debut=substr(CQ3,12,8), a(CQ3)
lab var heure_debut "Heure de debut de l'enquête"

gen heure_fin=substr(CQ4,12,8), a(CQ4)
lab var heure_fin "Heure de fin de l'enquête"

gen double debut = clock(heure_debut, "hms")
gen double fin   = clock(heure_fin, "hms")

gen duree_sec=(fin-debut)/1000

gen duree_minute=duree_sec/60
lab var duree_minute "Durée mn"
mean duree_min

*date de fin
gen date_fin1=substr(CQ4,1,10), a(CQ4)
replace date_fin1=substr(CQ3,1,10) if date_fin1=="##N/A##"

encode date_fin1, gen(date_fin) 

bysort taille_men: su duree_min

*CATEGORISATION DES MENAGES VIDES 
gen erreur_refus_RSU = 0 
replace erreur_refus_RSU=1 if Perm_rsu>1 & !mi(Perm_rsu)
lab def erreur_refus_RSU 0"" 1 "Tsy mazava ny antony fandavana/tsy feno ny consentement RSU/etc..."  ,modify
lab val erreur_refus_RSU erreur_refus_RSU 
lab var erreur_refus_RSU "erreur Permission RSU"

*FOKONTANY VIDE
gen erreur_fokontany=0
replace erreur_fokontany=1 if CQ9>=. | CQ8>=.
lab def erreur_fokontany 0 "" 1 "Tsy feno ny fokontany/commune",modify
lab val erreur_fokontany erreur_fokontany
lab var erreur_fokontany "erreur fokontany"


/*
*Milieu vide
gen err_milieu=0
replace err_milieu=1 if Milieu>=.
lab def err_milieu 0 "" 1 "tsy feno ny milieu"
lab val err_milieu err_milieu
*/
/*gen err_autre=0
foreach x in H1_Oth H4_Oth H5_Oth H6_Oth H7_Oth H8_Oth H9_Oth{
	replace err_autre=1 if `x'!=""
}
sort commune
br if err_autre==1*/

/*Autre à preciser et correction
*Tsy tafiditra e-fokontany
replace typemen_motif_Oth=upper(typemen_motif_Oth)
gen erreur_typemen_motif_Oth=0
replace erreur_typemen_motif_Oth=1 if strmatch(typemen_motif_Oth, "*FANTATRA*") ==1 |strmatch(typemen_motif_Oth, "*VAO*") ==1 | strmatch(typemen_motif_Oth, "*RECHERCHE*") ==1 |strmatch(typemen_motif_Oth, "*NIFINDRA*") ==1 |strmatch(typemen_motif_Oth, "*NIORINA*") ==1 
lab def erreur_typemen_motif_Oth 0 "" 1 "Amarino/ahitsio ny modalité antony tsy nahatafiditra azy e-fokontany"
lab val erreur_typemen_motif_Oth erreur_typemen_motif_Oth
lab var erreur_typemen_motif_Oth "erreur motif non enregistrement e-fokontany"

*H1
replace H1_Oth=upper(H1_Oth)
gen erreur_H1_Oth=0
replace erreur_H1_Oth=1 if strmatch(H1_Oth, "*TANY*") ==1 |strmatch(H1_Oth, "*FALAFA*") ==1 | strmatch(H1_Oth, "*CIMENT*") ==1 | strmatch(H1_Oth, "*BIRIKY*") ==1 |strmatch(H1_Oth, "*TANIMANGA*") ==1 |strmatch(H1_Oth, "*MANTA*") ==1 |  strmatch(H1_Oth, "* SIMBA*") ==1 | strmatch(H1_Oth, "*BOZAKA*") ==1 | strmatch(H1_Oth, "*PLANCH*") ==1 | strmatch(H1_Oth, "*SIMENITR*") ==1 | strmatch(H1_Oth, "*VATO*") ==1 | strmatch(H1_Oth, "*DUR*") ==1 
lab def erreur_H1_Oth 0 "" 1 "Amarino/ahitsio ny modalité mur extérieur"
lab val erreur_H1_Oth erreur_H1_Oth
lab var erreur_H1_Oth "erreur mur extérieur"

*H4_Oth
replace H4_Oth=upper(H4_Oth)
gen erreur_H4_Oth=0
replace erreur_H4_Oth=1 if strmatch(H4_Oth, "*PLANCH*") ==1 | strmatch(H4_Oth, "*HAZO*") ==1 | strmatch(H4_Oth, "*SIMENIT*") ==1 | strmatch(H4_Oth, "*TANY*") ==1 | strmatch(H4_Oth, "*SIMENIT*") ==1 | strmatch(H4_Oth, "*CIMEN*") ==1 | strmatch(H4_Oth, "*BET*") ==1
lab def erreur_H4_Oth 0 "" 1 "Amarino/ahitsio ny modalité gorodona(plancher)"
lab val erreur_H4_Oth erreur_H4_Oth
lab var erreur_H4_Oth "erreur plancher(gorodona)"

*H5_Oth
replace H5_Oth=upper(H5_Oth)
gen erreur_H5_Oth=0
replace erreur_H5_Oth=1 if strmatch(H5_Oth, "*SIMEN*") ==1 | strmatch(H5_Oth, "*HAZO*") ==1 | strmatch(H5_Oth, "*CIMEN*") ==1 | strmatch(H5_Oth, "*TOLE*") ==1 | strmatch(H5_Oth, "*BOZAK*") ==1 | strmatch(H5_Oth, "*FANITS*") ==1 
lab def erreur_H5_Oth 0 "" 1 "Amarino/ahitsio ny modalité ny tafo(toit)"
lab val erreur_H5_Oth erreur_H5_Oth
lab var erreur_H5_Oth "erreur tafo(toit)"

*H6_Oth
replace H6_Oth=upper(H6_Oth)
gen erreur_H6_Oth=0
replace erreur_H6_Oth=1 if strmatch(H6_Oth, "*MISY*") ==1 | strmatch(H6_Oth, "*HAZO*") ==1 | strmatch(H6_Oth, "*KITAY*") ==1 | strmatch(H6_Oth, "*BATTERIE*") ==1 | strmatch(H6_Oth, "*BATER*") ==1 | strmatch(H6_Oth, "*AMPOUL*") ==1 
lab def erreur_H6_Oth 0 "" 1 "Amarino/ahitsio ny modalité Electricité"
lab val erreur_H6_Oth erreur_H6_Oth
lab var erreur_H6_Oth "erreur Electricité"

*H7_Oth
replace H7_Oth=upper(H7_Oth)
gen erreur_H7_Oth=0
replace erreur_H7_Oth=1 if strmatch(H7_Oth, "*MISY*") ==1 | strmatch(H7_Oth, "*HAZO*") ==1 | strmatch(H7_Oth, "*KITAY*") ==1 | strmatch(H7_Oth, "*BATTERIE*") ==1 | strmatch(H7_Oth, "*BATER*") ==1 | strmatch(H7_Oth, "*AMPOUL*") ==1 | strmatch(H7_Oth, "*PILE*") ==1 | strmatch(H7_Oth, "*TORCHE*") ==1 | strmatch(H7_Oth, "*LAMP*") ==1 | strmatch(H7_Oth, "*LEMP*") ==1 | strmatch(H7_Oth, "*KELY*") ==1 | strmatch(H7_Oth, "*JIRO*") ==1
lab def erreur_H7_Oth 0 "" 1 "Amarino/ahitsio ny modalité Electricité"
lab val erreur_H7_Oth erreur_H7_Oth
lab var erreur_H7_Oth "erreur Electricité"

*H8_Oth
replace H8_Oth=upper(H8_Oth)
gen erreur_H8_Oth=0
replace erreur_H8_Oth=1 if strmatch(H8_Oth, "*MIS*") ==1 | strmatch(H8_Oth, "*TSY*") ==1 | strmatch(H8_Oth, "*VATO*") ==1 | strmatch(H8_Oth, "*MINDRANA*") ==1 | strmatch(H8_Oth, "*LAVAK*") ==1 | strmatch(H8_Oth, "*FOSS*") ==1 
lab def erreur_H8_Oth 0 "" 1 "Amarino/ahitsio ny modalité toilette",modify
lab val erreur_H8_Oth erreur_H8_Oth
lab var erreur_H8_Oth "erreur toilette"

*H9_Oth *H9 :"H9. Evacuation d'ordures"
replace H9_Oth=upper(H9_Oth)
gen erreur_H9_Oth=0
replace erreur_H9_Oth=1 if strmatch(H9_Oth, "*MISY*") ==1 | strmatch(H9_Oth, "*TS*") ==1 | strmatch(H9_Oth, "*LAVA*") ==1 | strmatch(H9_Oth, "*ZEZIK*") ==1 | strmatch(H9_Oth, "*RAN*") ==1 | strmatch(H9_Oth, "*DORANA*") ==1 
lab def erreur_H9_Oth 0 "" 1 "Amarino/ahitsio ny modalité Evacuation d'ordures"
lab val erreur_H9_Oth erreur_H9_Oth
lab var erreur_H9_Oth "erreur Evacuation d'ordures"

*H10_Oth
replace H10_Oth=upper(H10_Oth)
gen erreur_H10_Oth=0
replace erreur_H10_Oth=1 if strmatch(H10_Oth, "*TRANO*") ==1 | strmatch(H10_Oth, "*PETRAKA*") ==1 | strmatch(H10_Oth, "*PANDOVA*") ==1 | strmatch(H10_Oth, "*NDRANA*") ==1 
lab def erreur_H10_Oth 0 ""  1 "Amarino/ahitsio ny modalité ny occupation dans le logement"
lab val erreur_H10_Oth erreur_H10_Oth
lab var erreur_H10_Oth "erreur occupation dans le logement"

efitra trano eritreretina ho betsaka loatra
bysort district commune fokontany: egen q1_h2=pctile(H2),p(25)
bysort district commune fokontany: egen q3_h2=pctile(H2),p(75)
gen H2_aberante=0
replace H2_aberante=1 if H2>q3_h2+(1.5*(q3_h2-q1_h2))
lab def H2_aberante 0 "non" 1 "oui"
lab val  H2_aberante  H2_aberante
lab var H2_aberante " H2_valeur aberrante ve sa tsia?"
ta H2 if H2_aberante==1*/

*caractéristique de logement vide
ge err_caract_log=0
foreach x in H1 H2 H4 H5 H6 H7 H8 H9 H10{
	replace err_caract_log=1 if `x'>=. & Perm_rsu==1
}

lab def err_caract_log 0 "" 1 "Misy tsy feno ny toetrin'ny trano fonenana"
lab val err_caract_log err_caract_log
lab var err_caract_log "erreur caractéristiques du logement"

*Possession de biens vide
gen err_bien=0
foreach x in AP__1 AP__2 AP__3 AP__4 AP__5 AP__6 AP__7 AP__8 AP__9 AP__10 AP__11 AP__12 AP__13 AP__14 AP__15 AP__16 AP__17 AP__18 AP__19 AP__20 AP__21 AP__22 AP__23 AP__24 AP__25 AP__26{
	replace err_bien=1 if `x'>=. & Perm_rsu==1 & (CQ10_already_yes_scan!="" | CQ10_already_yes_saisi!="")
}

lab def err_bien 0 "" 1 "Misy tsy feno ny fananan'ny tokantrano"
lab val err_bien err_bien
lab var err_bien "erreur possession de biens"

*Source de revenu
gen err_SR=0
foreach x in SR01 SR02 SR03 SR04 SR05 SR06 SR07 SR08 SR09{
	replace err_SR=1 if `x'>=. & Perm_rsu==1 & (CQ10_already_yes_scan!="" | CQ10_already_yes_saisi!="")
}

lab def err_SR 0 "" 1 "Misy tsy feno ny loharanombola"
lab val err_SR err_SR
lab var err_SR "erreur source de revenu incomplète"

gen err_SR_ppl=0
replace err_SR_ppl=1 if  SR01!=1 & SR02!=1 & SR03!=1 & SR04!=1 & SR05!=1 & SR06!=1 & SR07!=1 & SR08!=1 & SR09!=1 & (CQ10_already_yes_scan!="" | CQ10_already_yes_saisi!="")

lab def err_SR_ppl 0 "" 1 "Tsy misy loharanombola fototra"
lab val err_SR_ppl err_SR_ppl
lab var err_SR_ppl "erreur source de revenu principal"

gen err_SRp=0
replace err_SRp=1 if  (SR01==4 | mi(SR01))  & (SR02==4 | mi(SR02)) & (SR03==4 | mi(SR03)) & (SR04==4 | mi(SR04)) & (SR05==4 | mi(SR05)) & (SR06==4 | mi(SR06)) & (SR07==4 | mi(SR07)) & (SR08==4 | mi(SR08)) & (SR09==4 | mi(SR09)) & (CQ10_already_yes_scan!="" | CQ10_already_yes_saisi!="")

lab def err_SRp 0 "" 1 "Tsy misy loharanombola mihitsy"
lab val err_SRp err_SRp
lab var err_SRp "erreur source de revenu"

/*
**Agriculture**
*Superficie*
gen err_suptot=0
replace err_suptot=1 if PT01+PT02<PT03
lab def err_suptot 0 "" 1 "Misy tsy marina ny velarantany"
lab val err_suptot err_suptot
lab var err_suptot "erreur superficie"

*Superficie cultivée*
gen err_supcult=0
replace err_supcult=1 if PT03==0 & typeculture==1
lab def err_supcult 0 "" 1 "Diso ny velarantany nambolena/fambolena"
lab val err_supcult err_supcult
lab var err_supcult "erreur superficie cultivée"

*Outliers superficies*
gen err_sup=0
replace err_sup=1 if PT01>5 | PT02>5 | PT03>5   /*5ha était la valeur maximale de la région Itasy selon l'EPM 2021*/
lab def err_sup 0 "" 1 "Misy velarantany ambony be, avereno kajiana sao diso"
lab val err_sup err_sup
lab var err_sup "valeurs abérrantes superficies"

*Rendement céréale*
gen err_rendmnt=0
replace err_rendmnt=1 if SR10*50/PT03>5000     /*selon la source de la BM le rendement moyen des céréales à Madagascar est de 2793kg/ha en 2022 (source : https://donnees.banquemondiale.org/indicateur/AG.YLD.CREL.KG?locations=MG&view=chart . Pourtant, nous prendrions une valeur maximale 5000kg*/

lab def err_rendmnt 0 "" 1 "Diso ny velarantany/fatran'ny céréales"
lab val err_rendmnt err_rendmnt
lab var err_rendmnt "erreur rendement des céréales"
*/
preserve
keep if erreur_refus_RSU==1|erreur_fokontany==1 |err_caract_log==1 |err_bien==1 |err_SR==1  | err_SR_ppl==1 | err_SRp==1 

keep interview__id interview__key nom_cm CQ6 CQ7 CQ8 CQ9 CQ2 CQ1 erreur_fokontany  err_bien err_SR  err_SR_ppl err_SRp  erreur_refus_RSU err_caract_log  interview__status

order interview__id interview__key nom_cm CQ6 CQ7 CQ8 CQ9 CQ2 CQ1 erreur_fokontany  err_bien err_SR  err_SR_ppl err_SRp  erreur_refus_RSU err_caract_log  interview__status

sort CQ7 CQ8 CQ9 CQ2

**ENSEMBLE**
capture mkdir "$erreur"

/*
*ENLEVER LES ERREURS DEJA ENVOYEES
merge 1:1 interview__key using "$erreur\base_erreur_ensemble.20250522_23H.dta", keepusing(interview__key) 
keep if _merge==1
drop _merge
*/

*Identifiant	region	district	commune	fokontany	nom_cm	chef d'equipe	enqueteur



keep if inlist(interview__status,100,120)


save "$errjournal_hist\base_erreur_menage_$version", replace


/*
export excel using  "$erreur\ERREUR_ENSEMBLE_MENAGE_$version.xlsx", firstrow(varlabels) sheet(erreur_menage) replace
putexcel set "$erreur\ERREUR_ENSEMBLE_MENAGE_$version.xlsx", sheet(erreur_menage) modify
putexcel A1:AX1, overwritefmt bold font(Calibri,12)
putexcel save

**Erreur par CE**
replace CQ2=999999 if mi(CQ2)
lab def CQ2 999999 "Login CE vide", modify



merge 1:1 interview__key using "$brute\base_login_ce_vad", keepusing(responsible__name)

keep if _merge==3

drop _merge

decode CQ2, gen(CE)
replace CE=responsible__name if CQ2==999999


levelsof CE, local(ce)
foreach x of local ce {
    export excel using  "$errjournal\ERREUR_MENAGE_`x'_$version.xlsx" if CE=="`x'", firstrow(varlabels) sheet(erreur_menage) replace
	putexcel set "$errjournal\ERREUR_MENAGE_`x'_$version.xlsx", sheet(erreur_menage) modify
	putexcel A1:AX1, overwritefmt bold font(Calibri,12)
	putexcel save
}

*/
restore



*************************************************************************************************************************************************************
*************************************************************************************************************************************************************
****************************************************************INDIVIDU*************************************************************************************
*************************************************************************************************************************************************************
*************************************************************************************************************************************************************



***************************************************************************************************************************************************
**************************************************************DEBUT DE CONTROLE BASE INDIVIDU********************************************************
***************************************************************************************************************************************************

use "$brute\RMen", clear

*FUSION AVEC LA BASE MENAGE POUR AVOIR LES INFORMATIONS SUR LES AGENTS DE TERRAIN ET LES DIVISIONS ADMINISTRATIVES

merge m:1 interview__id using "$brute\rsuefkt_25_rN_pil" , keepusing(CQ3 nom_cm code_den CQ6 CQ7 CQ8 CQ9 CQ17 interview__status)
keep if _merge==3
drop _merge

merge m:1 interview__key using "$brute\base_login_ce_vad", keepusing(CQ2)
keep if _merge==3
drop _merge


merge m:1 interview__id using "$brute\interview__diagnostics", keepusing(responsible)
keep if _merge==3
drop _merge
ren responsible CQ1



*Garder les entretiens completés ou approuvés
keep if interview__status==100 | interview__status==120



*ERREUR MEMBRE DE MENAGE SI NON MEMBRE

gen nomemnre_motif_Oth_util=upper(nomembre_motif_Oth)

gen err_membre=0
replace err_membre=1 if  strmatch(nomemnre_motif_Oth_util, "*IASA*") ==1 | strmatch(nomemnre_motif_Oth_util, "*KARAMA*") ==1

replace nomemnre_motif_Oth_util="" if strmatch(nomemnre_motif_Oth_util, "*IASA*") ==0 & strmatch(nomemnre_motif_Oth_util, "*KARAMA*") ==0

lab def err_membre 0 "" 1 "Hamarino sao membre ménage ihany: raha mihoatra ny 6mois ny absence dia tsy membre intsony sinon mbola membre ihany", modify
lab val err_membre err_membre


/*
**Numéro CIN**
preserve
use "$brute/interview__comments", clear
keep if variable=="M6a"
ren id1 RMen__id
ren comment comment_M6a
keep interview__id comment_M6a RMen__id
tempfile comment_M6a
duplicates drop interview__id RMen__id, force
save `comment_M6a', replace
restore
merge 1:1 interview__id RMen__id using `comment_M6a'
drop _m
gen nb_com_M6a=strlen(comment_M6a)
gen err_cin=1 if mi(M6a) & M4>=18 & !mi(M4) & nb_com_M6a<6 & inlist(M6_valid,1,2)
replace err_cin=0 if mi(err_cin)
lab def err_cin 1 "Tsy misy Numéro CIN" 0 ""
lab value err_cin err_cin
drop comment nb_com

**Date de délivrance CIN**
preserve
use "$brute/interview__comments", clear
keep if variable=="M6b"
ren id1 RMen__id
ren comment comment_M6b
keep interview__id comment_M6b RMen__id
tempfile comment_M6b
save `comment_M6b', replace
restore
merge 1:1 interview__id RMen__id using `comment_M6b'
drop _m
gen nb_com_M6b=strlen(comment_M6b)
gen err_date_cin=1 if mi(M6b) & M4>=18 & !mi(M4) & nb_com_M6b<6 & inlist(M6_valid,1,2)
replace err_date_cin=0 if mi(err_date_cin)
lab def err_date_cin 1 "Tsy misy Date de delivrance CIN" 0 ""
lab val err_date_cin err_date_cin
drop comment nb_com

**Lieu de délivrance CIN**
preserve
use "$brute/interview__comments", clear
keep if variable=="M6d"
ren id1 RMen__id
ren comment comment_M6d
keep interview__id comment_M6d RMen__id
tempfile comment_M6d
save `comment_M6d', replace
restore
merge 1:1 interview__id RMen__id using `comment_M6d'
drop _m
gen nb_com_M6d=strlen(comment_M6d)
gen err_lieu_cin=1 if mi(M6d) & M4>=18 & !mi(M4) & nb_com_M6d<6 & inlist(M6_valid,1,2)
replace err_lieu_cin=0 if mi(err_lieu_cin)
lab def err_lieu_cin 1 "Tsy misy Lieu de delivrance CIN" 0 ""
lab value err_lieu_cin err_lieu_cin
drop comment nb_com

*/



*Remplacer d'abord M7 par M7_preload si vide
replace M7=M7_preload if M7==. & M7_preload!=.

*Détection des ménages ayant deux chef de ménage/ sans Chef de ménage
gen err_cm=0
replace err_cm=1 if M7==1
bysort interview__id: egen err_cm_tot=total(err_cm)
sort interview__key RMen__id
br if err_cm_tot>1 | err_cm_tot==0
ta err_cm_tot



*Ménage ayant deux conjoints
gen err_cj=0
replace err_cj=1 if M7==2
bysort interview__id: egen err_cj_tot=total(err_cj)
replace err_cj_tot=0 if M7>2 
br if err_cj_tot>1
ta err_cj_tot
ta M4  if err_cj_tot>1 & M7<=3


sort interview__key RMen__id
gen err_cm_cj_age=0
replace err_cm_cj_age=1 if M7<3 & M4<12


gen err_cm_cj=0
replace err_cm_cj=1 if ((err_cm_tot>1 | err_cm_tot==0) | (err_cj_tot>1 & M7<=3)| err_cm_cj_age==1) 



lab def err_cm_cj 0 "" 1 "Tsy misy lohatokantrano/Lohatokatrano mihoatra ny roa/Vady roa ao anaty tokantrano iray/Taonan'ny lohatokantrano na ny vadiny latsaky ny 12 taona"
lab val err_cm_cj err_cm_cj

br if err_cm_cj==1

drop err_cj_tot err_cm_tot

*------------CONTROLE DU SEXE CM et Conjoint(e)------------------------
*Remplacer d'abord M7 par M7_preload si vide
replace M7=M7_preload if M7==. & M7_preload!=.

*Remplacer d'abord M7 par M7_preload si vide
replace M3=M3_preload if M3==. & M3_preload!=.

*Dichotomiser la variable sexe
tab M3, gen(M3_)

replace M3_1=. if M7>=3
replace M3_2=. if M7>=3

bysort interview__id: egen err_M3_1=total(M3_1)
bysort interview__id: egen err_M3_2=total(M3_2)

replace err_M3_1=. if M7>=3
replace err_M3_2=. if M7>=3

gen err_sexe_cm_cj=0
replace err_sexe_cm_cj=1 if err_M3_1==2 & (err_cm_cj==0) | err_M3_2==2 & (err_cm_cj==0)

drop err_M3_1 err_M3_2 M3_1 M3_2

lab def err_sexe_cm_cj 0 "" 1 "Mitovy fananahana (sexe) ny lohatokantrano sy ny vadiny"
lab val err_sexe_cm_cj err_sexe_cm_cj



*M7
ta M7 


lab var err_cm_cj "Hamarino ny lien de parenté avec le CM sy ny taona"



*Taille du ménage
preserve
keep if membre_valid!=3
bysort interview__key: gen taille_menage=_N 
save "$brute\base_taille", replace

tabout CQ8  using "$rapport\Taille_ménage.xlsx",  append sum  c(mean taille_menage) ///
f(1) location(1 1) $form_all sheet(taille) h1(nil) total(DISTRICT Ensemble) ///
h3(nil) layout(cb) title(Taille moyenne de ménage par commune) fn(Source : Enquete E-fokontany/RSU) sheetreplace

restore

*Manquante sur sexe, résidence, lien de parente, age en années revolue, capie, statut matrimonial


des M7 M3 M4a M5e M6 M6a M6b M6d M7a M7b M8

foreach x in M7 M3  M6  M8{
	replace `x'=`x'_preload if `x'>=. & membre_valid!=3 & `x'_preload<.
}


foreach x in M6a M6b M6d M7a M7b M4a M5e{
	replace `x'=`x'_preload if `x'=="" & membre_valid!=3 & `x'_preload!=""& `x'_preload!="##N/A##"
}

gen err_M7_M3_M4_M8_M5_vide=0

foreach x in M7 M3 M4 M5 M8{
	replace err_M7_M3_M4_M8_M5_vide=1 if `x'>=. & membre_valid!=3
}

replace err_M7_M3_M4_M8_M5_vide=0 if M8>=. & M4<10

ta err_M7_M3_M4_M8_M5_vide

br if err_M7_M3_M4_M8_M5_vide==1

lab def err_M7_M3_M4_M8_M5_vide 0 "" 1 "Misy tsy feno ny  lien de parente, sexe, age en année révolue, copie d'acte de naissance, statut matrimonial"
lab val err_M7_M3_M4_M8_M5_vide err_M7_M3_M4_M8_M5_vide

br if err_M7_M3_M4_M8_M5_vide==1
lab var err_M7_M3_M4_M8_M5_vide "Manquante sur sexe, résidence, lien de parente, age en années revolue, copie, statut matrimonial "



*********ERREUR DE VALIDATION*********

*string M1b M1b1 M4a M5e M6a M6b M6d M7a M7b
*byte M7 M3 M6 M8
*Ens M1b M1b1 M4a M5e M6a M6b M6d M7 M3 M6 M8
gen err_validation_e_fkt=0
foreach x in M1b M4a M5e{
    replace err_validation_e_fkt =1 if  (`x'_preload=="" |`x'_preload=="##N/A##") & `x'_valid == 1
}

foreach x in M7 M3 M6 M8 {
    replace err_validation_e_fkt =1 if  `x'_preload>=. & `x'_valid == 1
}

replace err_validation_e_fkt=0 if (M8>=. & M4<10) | membre_valid!=1

lab def err_validation_e_fkt 0 "" 1 "Tsy azo valider'na ny information e-fokontany banga, atao TSIA foana ny valiny"

lab val err_validation_e_fkt err_validation_e_fkt




*Femme enceinte

gen err_M12=0
replace err_M12=1 if (M3==2 & M4>=15) & M12>=.

ta err_M12

*EDUCATION ET ALPHABETISATION DES MEMBRES DU MENAGE

gen err_M13=0
replace err_M13=1 if M13>=. & M4>=5 & M4!=.
ta err_M13

*M14

gen err_M14=0
replace err_M14=1 if M13==1 & M14>.
ta err_M14

*Alphabetisation
*M16a M16b

gen err_alphabet=0
replace err_alphabet=1 if (M16a>=. | M16b>=.) & membre_valid!=3 & M13==1



gen err_education=0
replace err_education=1 if (err_M13==1 | err_M14==1 | err_alphabet==1) & membre_valid!=3

lab def err_education 0 "" 1 "Misy tsy feno ny section education et alphabetisation"
lab val err_education err_education

ta err_education


*M15
ta M15

*HANDICAP

*AUEM17c AUEM17a AUEM17b AUEM17d AUEM17e AUEM17f AUEM17g AUEM17i
tab1 AUEM17c AUEM17a AUEM17b AUEM17d AUEM17e AUEM17f AUEM17g AUEM17i
gen err_handicap=0
foreach x in  AUEM17a AUEM17b AUEM17d AUEM17e AUEM17f AUEM17g AUEM17i{
	replace err_handicap=1 if M4>5 & M4!=. & `x'>=. & membre_valid!=3
}

ta err_handicap

lab def err_handicap 0 "" 1 "Misy tsy feno ny section handicap"
lab val err_handicap err_handicap
*ta err_ensemble


*ERREUR ENSEMBLE
gen err_ensemble=0
foreach x in err_cm_cj err_membre err_M7_M3_M4_M8_M5_vide err_education err_handicap err_sexe_cm_cj err_validation_e_fkt{
replace err_ensemble=1 if  `x'==1
*bysort interview__id: egen 	`x'_fin=total(`x')
*replace err_ensemble=1 if  `x'_fin>=1
	
}

save "$errjournal_hist\base_erreur_membre_$version0.dta", replace


keep if err_ensemble==1
keep if inlist(interview__status,100,120)

/*
*ENLEVER LES ERREURS DEJA ENVOYEES
merge m:1 interview__key using "$erreur\base_erreur_ensemble.20250522_23H.dta", keepusing(interview__key) 
keep if _merge==1
duplicates drop
drop _merge
*/

keep interview__id interview__key nom_cm M1a CQ6 CQ7 CQ8 CQ9 CQ2 CQ1 err_membre nomemnre_motif_Oth_util err_cm_cj err_sexe_cm_cj err_M7_M3_M4_M8_M5_vide err_education err_handicap err_validation_e_fkt interview__status

sort CQ8 CQ9 CQ2 CQ1

/*
export excel interview__key nom_cm M1a CQ7 CQ8 CQ9 CQ2 CQ1 err_membre nomemnre_motif_Oth_util err_cm_cj err_sexe_cm_cj err_M7_M3_M4_M8_M5_vide err_education err_handicap using  "$erreur\ERREUR_ENSEMBLE_INDIVIDU.$version.xlsx" , firstrow(varlabels)  sheet(erreur_membre) sheetreplace
*/


*save "$erreur\base_erreur_membre_$version.dta", replace


bysort interview__key: gen id_men=_n
keep interview__id id_men interview__key CQ6 CQ7 CQ8 CQ9 nom_cm CQ2 CQ1 nomemnre_motif_Oth_util M1a err_membre err_cm_cj err_sexe_cm_cj err_M7_M3_M4_M8_M5_vide  err_education err_handicap err_validation_e_fkt interview__status

ren  nomemnre_motif_Oth_util nomembre_motif_Oth

reshape  wide nomembre_motif_Oth M1a err_membre err_cm_cj err_sexe_cm_cj err_M7_M3_M4_M8_M5_vide  err_education err_handicap err_validation_e_fkt, i(interview__key) j(id_men)

save "$errjournal_hist\base_erreur_membre_$version.dta", replace

	preserve
clear
input str30 err_membre	str30 nomembre_motif_Oth
"err_cm_cj"	"M7"
"err_sexe_cm_cj"	"M3"
"err_sexe_cm_cj"	"M7"
"err_handicap"	"AUEM17a"
"err_handicap"	"AUEM17b"
"err_handicap"	"AUEM17d"
"err_handicap"	"AUEM17e"
"err_handicap"	"AUEM17f"
"err_handicap"	"AUEM17g"
"err_handicap"	"AUEM17i"
"err_M7_M3_M4_M8_M5_vide"	"M3"
"err_M7_M3_M4_M8_M5_vide"	"M4"
"err_M7_M3_M4_M8_M5_vide"	"M5"
"err_M7_M3_M4_M8_M5_vide"	"M7"
"err_M7_M3_M4_M8_M5_vide"	"M8"
"err_education"	"M13"
"err_education"	"M14"
"err_education"	"M16a"
"err_education"	"M16b"
"err_validation_e_fkt" "M1b"
"err_validation_e_fkt" "M4a"
"err_validation_e_fkt" "M5e"
"err_validation_e_fkt" "M7"
"err_validation_e_fkt" "M3"
"err_validation_e_fkt" "M6"
"err_validation_e_fkt" "M8"
end
tempfile Feuil3_individu
save `Feuil3_individu', replace

*M1b M1b1 M4a M5eM7 M3 M6 M8
restore



use "$errjournal_hist\base_erreur_membre_$version.dta", clear
lab var interview__key "Identifiant"
lab var CQ6 "region"
lab var CQ7 "district"
lab var CQ8 "commune"
lab var CQ9 "fokontany"
lab var CQ2 "chef d'equipe"
lab var nom_cm "nom_cm"
lab var CQ1 "enqueteur"


order interview__key CQ6 CQ7 CQ8 CQ9 nom_cm CQ2 CQ1 err_membre* nomembre_motif_Oth* err_cm_cj* err_sexe_cm_cj* err_M7_M3_M4_M8_M5_vide* err_education* err_handicap* err_validation_e_fkt*

*merge 1:1 using "$errjournal_hist\base_erreur_menage_$version.dta", keepusing(interview__key)


gen groupe = ceil(_n/199)
levelsof groupe, local(grps)
foreach g of local grps {
    preserve
    keep if groupe == `g'
			export excel interview__key CQ6 CQ7 CQ8 CQ9 nom_cm CQ2 CQ1 err_membre* nomembre_motif_Oth* err_cm_cj* err_sexe_cm_cj* err_M7_M3_M4_M8_M5_vide* err_education* err_handicap* err_validation_e_fkt* using  "$errjournal_survey\base_erreur_membre_numero_`g'_$version.xlsx" , firstrow(varlabels)  sheet(Feuil1) sheetreplace
			putexcel set "$errjournal_survey\base_erreur_membre_numero_`g'_$version.xlsx", sheet(Feuil1) modify
			putexcel A1:CX1, overwritefmt bold font(Calibri,12)
			export excel  interview__key interview__id using  "$errjournal_survey\base_erreur_membre_numero_`g'_$version.xlsx" , firstrow(varlabels)  sheet(Feuil2) sheetreplace
			use `Feuil3_individu', clear
export excel using  "$errjournal_survey\base_erreur_membre_numero_`g'_$version.xlsx" , firstrow(varlabels)  sheet(Feuil3) sheetreplace
    restore
}



/*

merge 1:1 interview__key using "$erreur\base_erreur_menage_$version"


keep interview__key nom_cm CQ7 CQ8 CQ9 CQ2 CQ1 erreur_fokontany  err_bien err_SR  err_SR_ppl err_SRp  erreur_refus_RSU err_caract_log  err_membre* nomemnre_motif_Oth_util* err_cm_cj* err_sexe_cm_cj* err_M7_M3_M4_M8_M5_vide* err_education* err_handicap* interview__status 

order interview__key nom_cm CQ7 CQ8 CQ9 CQ2 CQ1 erreur_fokontany  err_bien err_SR  err_SR_ppl err_SRp  erreur_refus_RSU err_caract_log   err_membre* nomemnre_motif_Oth_util* err_cm_cj* err_sexe_cm_cj* err_M7_M3_M4_M8_M5_vide* err_education* err_handicap*  interview__status 


save "$erreur\base_erreur_ensemble.$version.dta", replace

*******************************************
keep if inlist(interview__status,100,120)
*******************************************
/*
*ENLEVER LES ERREURS DEJA ENVOYEES
merge 1:1 interview__key using "$erreur\base_erreur_ensemble.20250522_23H.dta", keepusing(interview__key) 
keep if _merge==1
drop _merge
*/

order CQ7 CQ8 CQ9 nom_cm CQ2 CQ1 ,a(interview__key)
export excel  using  "$erreur\ERREUR_ENSEMBLE_MPS.$version.xlsx" , firstrow(varlabels)  sheet(erreur_ensemble) sheetreplace
putexcel set "$erreur\ERREUR_ENSEMBLE_MPS.$version.xlsx", sheet(erreur_ensemble) modify
putexcel A1:CX1, overwritefmt bold font(Calibri,12)
putexcel save
*/
use "$errjournal_hist\base_erreur_membre_$version0.dta", clear

preserve
clear
input str15 CE	str30 communeaffect	str30 suptech
"CE_MDVZ_011"	"ANKONDROMENA"	"PASCAL1_SENDERSEN"
"CE_MDVZ_012"	"ANKONDROMENA"	"PASCAL1_SENDERSEN"
"CE_MDVZ_013"	"SOALOKA"	"PASCAL1_SENDERSEN"
"CE_MDVZ_014"	"SOALOKA"	"PASCAL1_SENDERSEN"
"CE_MDVZ_015"	"SOALOKA"	"PASCAL1_SENDERSEN"
"""CE_MDVZ_001""	"ANKAVANDRA"	"JOSE_MARTINA"
"CE_MDVZ_002"	"ANKAVANDRA"	"JOSE_MARTINA"
"CE_MDVZ_003"	"ANKAVANDRA"	"JOSE_MARTINA"
"CE_MDVZ_004"	"ANKAVANDRA"	"JOSE_MARTINA"
"CE_MDVZ_005"	"ANKAVANDRA"	"JOSE_MARTINA"
"CE_MDVZ_006"	"ANKAVANDRA"	"JOSE_MARTINA"
"CE_MDVZ_007"	"ANKAVANDRA"	"JOSE_MARTINA"
"CE_MDVZ_008"	"BETSIPOLITRA"	 "JOSE_MARTINA"
"CE_MDVZ_009"	"BETSIPOLITRA"	 "JOSE_MARTINA"
"CE_MDVZ_010"	"BETSIPOLITRA" 	"JOSE_MARTINA"
"CE_MDVZ_016"	"MANANDAZA" 	"PASCAL2_ANTONIE"
"CE_MDVZ_017"	"MANANDAZA"	 "PASCAL2_ANTONIE"
"CE_MDVZ_018"	"MANANDAZA"	 "PASCAL2_ANTONIE"
"CE_MDVZ_019"	"ITONDY"	"PASCAL2_ANTONIE"
"CE_MDVZ_020"	"ITONDY"	"PASCAL2_ANTONIE"
"CE_MDVZ_021"	"ITONDY"	"PASCAL2_ANTONIE"
"CE_MDVZ_022"	"ITONDY"	"PASCAL2_ANTONIE"
"CE_MDVZ_023"	"AMPANIHY"	"PASCAL2_ANTONIE"
"CE_MDVZ_024	"  "AMPANIHY"	"PASCAL2_ANTONIE"
"CE_MDVZ_024"	"AMPANIHY"	"PASCAL2_ANTONIE"
"CE_MDVZ_025"	"BEMAHATAZANA"	"PASCAL2_ANTONIE"
"CE_MDVZ_026"	"BEMAHATAZANA"	"PASCAL2_ANTONIE"
"CE_MDVZ_027"	"BEMAHATAZANA"	"PASCAL2_ANTONIE"
"CE_MDVZ_028"	"ANOSIMENA"	"CHEFDAUD_HERY"
"CE_MDVZ_029"	"ANOSIMENA"	"CHEFDAUD_HERY"
"CE_MDVZ_030"	"DABOLAVA"	"CHEFDAUD_HERY"
"CE_MDVZ_031"	"DABOLAVA"	"CHEFDAUD_HERY"
"CE_MDVZ_032"	"DABOLAVA"	"CHEFDAUD_HERY"
"CE_MDVZ_033"	"DABOLAVA"	"CHEFDAUD_HERY"
"CE_MDVZ_034"	"MIANDRIVAZO"	"CHEFDAUD_HERY"
"CE_MDVZ_035"	"MIANDRIVAZO"	"CHEFDAUD_HERY"
"CE_MDVZ_036"	"MIANDRIVAZO"	"CHEFDAUD_HERY"
"CE_MDVZ_037"	"MIANDRIVAZO"	"CHEFDAUD_HERY"
"CE_MDVZ_038"	"MIANDRIVAZO"	"CHEFDAUD_HERY"
"CE_MDVZ_039"	"ANDRANOMAINTY"	"CHEFDAUD_HERY"
"CE_MDVZ_040"	"ANDRANOMAINTY"	"CHEFDAUD_HERY"
"CE_MDVZ_041"	"ANDRANOMAINTY"	"CHEFDAUD_HERY"
"CE_MDVZ_051"	"ISALO"	"PIERRE_CLARA"
"CE_MDVZ_052"	"ISALO"	"PIERRE_CLARA"
"CE_MDVZ_053"	"ISALO"	"PIERRE_CLARA"
"CE_MDVZ_042"	"ANKOTROFOTSY"	"PIERRE_CLARA"
"CE_MDVZ_043"	"ANKOTROFOTSY"	"PIERRE_CLARA"
"CE_MDVZ_044"	"ANKOTROFOTSY"	"PIERRE_CLARA"
"CE_MDVZ_045"	"ANKOTROFOTSY"	"PIERRE_CLARA"
"CE_MDVZ_046"	"AMBATOLAHY"	"PIERRE_CLARA"
"CE_MDVZ_047"	"AMBATOLAHY"	"PIERRE_CLARA"
"CE_MDVZ_048"	"AMBATOLAHY"	"PIERRE_CLARA"
"CE_MDVZ_049"	"AMBATOLAHY"	"PIERRE_CLARA"
"CE_MDVZ_050"	"AMBATOLAHY"	"PIERRE_CLARA"
"CE_MDVZ_054"	"MANAMBINA"	"PIERRE_CLARA"
"CE_MDVZ_055"	"MANAMBINA"	"PIERRE_CLARA"
"CE_MDVZ_056"	"MANAMBINA"	"PIERRE_CLARA"
"CE_MDVZ_057"	"MANAMBINA"	"PIERRE_CLARA"
end

tempfile repart_equip
save `repart_equip', replace
*use `repart_equip', clear
restore


use "$errjournal_hist\base_erreur_menage_$version", clear
lab var interview__key "Identifiant"
lab var CQ6 "region"
lab var CQ7 "district"
lab var CQ8 "commune"
lab var CQ9 "fokontany"
lab var CQ2 "chef d'equipe"
lab var nom_cm "nom_cm"
lab var CQ1 "enqueteur"
gen x="",a(CQ1)
merge 1:1 interview__key using "$errjournal_hist\base_erreur_membre_$version.dta", keepusing(interview__id CQ6 CQ7 CQ8 CQ9 nom_cm CQ2 CQ1)
*drop if _merge==2
lab var x " "
gen DETAIL=""
gen err_individu="",a(DETAIL)
replace err_individu="Misy erreur mahakasika ny olona ao an-tokantrano" if _merge==2
drop _merge
order interview__key CQ6 CQ7 CQ8 CQ9 nom_cm CQ2 CQ1 x


gen groupe = ceil(_n/199)
levelsof groupe, local(grps)
foreach g of local grps {
    preserve
    keep if groupe == `g'
export excel interview__key CQ6 CQ7 CQ8 CQ9 nom_cm CQ2 CQ1 x erreur_fokontany err_bien err_SR err_SR_ppl err_SRp erreur_refus_RSU err_caract_log err_individu DETAIL   using  "$errjournal_survey\base_erreur_menage_numero_`g'_$version.xlsx" , firstrow(varlabels)  sheet(Feuil1) sheetreplace
putexcel set "$errjournal_survey\base_erreur_menage_numero_`g'_$version.xlsx", sheet(Feuil1) modify
putexcel A1:CX1, overwritefmt bold font(Calibri,12)
export excel  interview__key interview__id using  "$errjournal_survey\base_erreur_menage_numero_`g'_$version.xlsx" , firstrow(varlabels)  sheet(Feuil2) sheetreplace
    restore
}



*****EXPORTATION ERREURS*****
foreach w in menage membre {
	use "$errjournal_hist\base_erreur_`w'_$version.dta", clear
	keep if inlist(interview__status,100,120)
	sort CQ8 CQ9 CQ2 CQ1

	**Erreur par sup tech et CE**
	ren CQ2 CE
	merge m:n CE using `repart_equip'
	duplicates drop
	drop if _m==2
	drop _merge
	levelsof suptech, local(sup)

	foreach z of local sup {
		global errsup="$errjournal\"+"`z'"
		capture mkdir "$errsup"
		levelsof communeaffect if suptech=="`z'", local(com`z')
		foreach y of local com`z' {
			global errcom="$errsup\"+"`y'"
			capture mkdir "$errcom"
			levelsof CE if communeaffect=="`y'", local(ce`y')
			foreach x of local ce`y' {
				export excel using  "$errcom\ERREUR_MENAGE_`x'_$version.xlsx" if CE=="`x'", firstrow(varlabels) sheet(erreur_`w',replace)
				putexcel set "$errcom\ERREUR_MENAGE_`x'_$version.xlsx", sheet(erreur_`w') modify
				putexcel A1:AX1, overwritefmt bold font(Calibri,12)
				putexcel save
					capt tabout  CQ1 using "$errcom\ERREUR_MENAGE_`x'_$version.xlsx" if CE=="`x'", oneway c(freq)append  ///
					 nnoc location(1 1) f(0) npos(col) clab(Effectif) nlab(Total) sheet(recap_erreur_`w') h1(nil) h3(nil) total(Ensemble Ensemble)  ///
					h3(nil) layout(cb)  $form_all title(Nombre d'erreur par enqueteur) fn(Source : Enquete E-fokontany/RSU) sheetreplace

						capt putexcel set "$errcom\ERREUR_MENAGE_`x'_$version.xlsx", sheet(recap_erreur_`w') modify
						capt putexcel B2=("Nombre d'erreur'") C2=("Total erreur")
						capt putexcel B2:C2, overwritefmt bold italic font(Calibri,12)
						capt putexcel save	
	}
		}
			}
				}



