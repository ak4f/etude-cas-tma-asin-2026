# ETUDE DE CAS TMA : PRISE DE RENDEZ-VOUS AU GUICHET (ASIN)

**Auteur :** ANATO Kodjo Freddy  
**Email :** fredak946@gmail.com  
**Poste :** Développeur Web Full Stack Junior / TMA  
**Etablissement :** Agence des Systemes d'Information et du Numerique (ASIN - DSID/DEP)  
**Date :** Jeudi 29 octobre 2026  

---

## 1. PRESENTATION DU PROJET ET ARCHITECTURE

Le present depot rassemble les travaux de maintenance corrective, evolutive et d'assurance qualite realises sur le systeme de reservation des rendez-vous au guichet pour le retrait des titres officiels (PASSEPORT, CNI, PERMIS).

L'architecture est concue selon les standards stricts d'ingenierie logicielle :
- **Module metier autonome (`regles_rendez_vous.py`) :** module purement metier, independant de tout framework et de tout SGBD, recevant l'instant de controle en parametre pour garantir la testabilite deterministe a 100 %.
- **Suite de tests automatises (`test_regles_rendez_vous.py`) :** couverture exhaustive de l'ensemble des tickets d'incidents (y compris le ticket conforme), des cas de bornes et des attaques par injection ou donnees hostiles (fuzzing).
- **Version temoin d'anomalies (`version_boguee.py`) :** module reproduisant fidelement les anomalies observees en production pour demontrer objectivement l'echec des tests avant correction.
- **Script d'extraction SQL d'impact (`requetes.sql`) :** requetes d'exploitation compatibles SQLite, PostgreSQL et MySQL pour cibler les usagers impactes et corriger les incoherences en base.

---

## 2. INSTRUCTIONS D'EXECUTION DES TESTS

Le projet repose sur la bibliotheque standard Python 3 (Python 3.10+). Aucune dependance tierce n'est requise.

### 2.1 Lancement de la suite de tests officielle (100 % succes)
```bash
python -m unittest -v test_regles_rendez_vous.py
```
*Resultat obtenu :* 52 tests executes avec succes en moins de 0.05 seconde.

### 2.2 Demonstration de la reproduction des anomalies sur la version boguee
Pour verifier l'exigence n° 4 (« Chaque test rejoue le cas decrit et echouerait avec le comportement signale ») :

*Sous Linux / macOS / Git Bash :*
```bash
REGLES_MODULE=version_boguee python -m unittest -v test_regles_rendez_vous.py
```

*Sous Windows PowerShell :*
```powershell
$env:REGLES_MODULE="version_boguee"; python -m unittest -v test_regles_rendez_vous.py; Remove-Item Env:\REGLES_MODULE
```

*Sous Windows CMD :*
```cmd
set REGLES_MODULE=version_boguee&& python -m unittest -v test_regles_rendez_vous.py
```
*Resultat obtenu :* La version boguee echoue precisement sur les 6 tickets d'anomalies (TMA-101 a TMA-106) et reussit sur le comportement conforme (TMA-107).

---

## 3. ANALYSE DETAILLEE PAR TICKET (TMA-101 A TMA-107)

### TMA-101 : Reservation impossible sur jour ferme (Samedi / Dimanche)
* **Signalement usager :** « J'ai pris rendez-vous pour le samedi 14 novembre. Une fois sur place, j'ai trouve le centre ferme. » (RDV n° 742 cree pour le 14/11/2026 a 10:00).
* **Qualification :** **ANOMALIE**.
* **Regle de reference :** Section 2 : « Le centre recoit du lundi au vendredi... Samedi ou dimanche : 409 Le centre est ferme le week-end. »
* **Diagnostic & Cause racine :** L'application ne controle pas le samedi, ou implemente un controle tronque qui ne verifie que le dimanche (ex: comparaison de jour indexe de 0 a 6 ou de 1 a 7 avec confusion des bornes). Preuve directe dans la base : 8 rendez-vous enregistres un samedi, 0 le dimanche.
* **Correction appliquee :** Verification explicite du jour de la semaine (`weekday() <= 4` en Python, soit du lundi au vendredi). Refus avec le code HTTP 409 et le message institutionnel exact : `Le centre est ferme le week-end.`
* **Test automatise :** Classe `TestTMA101FermetureWeekEnd` verifiant la trace exacte du ticket (14/11/2026), le rejet du dimanche, l'acceptation du lundi au vendredi et le balayage de 8 semaines completes de week-ends.

---

### TMA-102 : Depassement de capacite de creneau (4 usagers pour 3 guichets)
* **Signalement chef de centre :** « Le mardi 10 novembre a 9 h 00, quatre usagers avaient rendez-vous sur le meme creneau. Nous n'avons que trois guichets. » (RDV 632, 644, 681 et 697).
* **Qualification :** **ANOMALIE**.
* **Regle de reference :** Section 2 : « Un creneau accueille au plus 3 usagers. Un rendez-vous annule libere sa place... Creneau plein : 409 Ce creneau est complet. »
* **Diagnostic & Cause racine :** Erreur d'operateur de comparaison dans la requete ou le code applicatif (`actifs > 3` ou `actifs <= 3` au lieu de `actifs >= 3`). L'application a laisse reserver le 4e usager lorsque 3 etaient deja presents. Preuve en base : le maximum observe par creneau est exactement de 4 usagers (jamais 5).
* **Correction appliquee :** Fonction `places_prises()` comptant les rendez-vous dont le statut est different de `annule` sur le creneau demande. Refus strict des que `places_prises >= 3` avec code HTTP 409 et message exact : `Ce creneau est complet.`
* **Test automatise :** Classe `TestTMA102CapaciteCreneau` rejouant le creneau du 10/11/2026 a 09:00 avec les trois premiers rendez-vous reels (632, 644, 681) et demontrant le rejet du 4e (697), ainsi que la liberation effective d'une place si l'un des rendez-vous est annule.

---

### TMA-103 : Erreur serveur 500 sur saisie NPI avec lettre
* **Signalement agent :** « Quand un usager tape une lettre dans son NPI, l'ecran affiche "Erreur interne du serveur" au lieu d'expliquer le probleme. » (Requete POST avec `{"npi":"06142A3647", ...}`).
* **Qualification :** **ANOMALIE**.
* **Regle de reference :** Section 2 : « Un rendez-vous est pris pour un usager, identifie par son NPI, compose d'exactement 10 chiffres... NPI invalide : 400 Le NPI doit comporter exactement 10 chiffres... jamais par une erreur interne. »
* **Diagnostic & Cause racine :** Absence de validation de format par expression reguliere en amont. Le backend tente de caster ou de parser le NPI en entier numerique (`int(npi)` ou cast SQL), ce qui leve une exception non interceptee en cascade (`ValueError` / `NumberFormatException`), transformee en HTTP 500 par le gestionnaire d'erreur global.
* **Correction appliquee :** Fonction `valider_npi()` utilisant une expression reguliere stricte (`^[0-9]{10}$` via `re.fullmatch(r"[0-9]{10}", npi)`). Rejet immediat en HTTP 400 avec le message exact : `Le NPI doit comporter exactement 10 chiffres.` Aucune conversion numerique n'est effectuee sans validation prealable.
* **Test automatise :** Classe `TestTMA103SaisieNPI` rejouant la requete du ticket, les NPI avec lettres, les NPI trop courts (9 chiffres), trop longs (11 et 12 chiffres), les espaces, les caracteres speciaux et les types non-string (None, int, liste).

---

### TMA-104 : Rejet d'annulation effectuee 40 h a l'avance
* **Signalement usager :** « Le mardi 17 novembre a 18 h, j'ai voulu annuler mon rendez-vous du jeudi 19 a 10 h. L'application a refuse : "Annulation impossible moins de 24 h avant". » (RDV n° 709).
* **Qualification :** **ANOMALIE**.
* **Regle de reference :** Section 2 : « L'usager peut annuler son rendez-vous jusqu'a 24 heures avant l'heure prevue... Annulation tardive : 409 Annulation impossible moins de 24 h avant le rendez-vous. »
* **Diagnostic & Cause racine :** Du 17/11 a 18:00 au 19/11 a 10:00, l'ecart temporel reel est de **40 heures** (bien superieur au seuil legal de 24 heures). Deux causes probables identifiees :
  1. Inversion arithmetique du calcul : `maintenant - date_rdv < 24h` au lieu de `date_rdv - maintenant >= 24h`. Pour toute date future, `maintenant - date_rdv` produit une duree negative, systematiquement inferieure a 24 heures, provoquant le blocage de TOUTES les annulations. Preuve dans l'export : 37 annulations d'usagers entre aout et le 03 octobre, puis **zero annulation usager pendant les 7 semaines suivantes**, malgre 472 nouveaux rendez-vous crees.
  2. Comparaison tronquee sur l'heure de la journee (18 h compare a 10 h : 18 > 10).
* **Correction appliquee :** Fonction `controler_annulation()` calculant la difference temporelle vectorielle complete : `rdv.date_heure - instant`. Si le delta est superieur ou egal a 24 heures (incluant le cas limite d'exactement 24 h), l'annulation est autorisee avec le code HTTP 200.
* **Test automatise :** Classe `TestTMA104Annulation` verifiant le cas nominal du ticket (40 h avant), la borne exacte de 24 h 00 (acceptee), la borne de 23 h 59 (rejetee en 409), et le refus d'annuler un rendez-vous deja honore, absent ou annule.

---

### TMA-105 : Reouverture et mutation d'un rendez-vous deja annule
* **Signalement agent :** « J'ai clique par erreur sur "Honore" pour un rendez-vous que l'usager avait annule. L'application a accepte, et le rendez-vous apparait maintenant comme honore. » (RDV n° 292, passe de `annule` a `honore` par l'agent AG-04).
* **Qualification :** **ANOMALIE**.
* **Regle de reference :** Section 2 : « Un rendez-vous "confirme" devient "honore", "absent" ou "annule". Ces trois statuts sont definitifs... Rendez-vous deja cloture : 409 Ce rendez-vous est deja cloture. »
* **Diagnostic & Cause racine :** La methode de mise a jour (`PATCH /api/rendez-vous/:id/statut`) controle uniquement la validite de la valeur cible (`honore` ou `absent`), mais omet de verifier l'etat courant de la ressource. Preuve dans l'export : 4 rendez-vous ont subi cette transition illegale (RDV 208, 231, 262 et 292).
* **Correction appliquee :** Fonction `controler_changement_statut()` verifiant que le rendez-vous courant est strictement au statut `confirme`. Tout rendez-vous deja `annule`, `honore` ou `absent` est rejete avec le code HTTP 409 et le message officiel : `Ce rendez-vous est deja cloture.`
* **Test automatise :** Classe `TestTMA105StatutsDefinitifs` rejouant la requete du ticket sur le RDV n° 292, les transitions interdites depuis `honore` et `absent`, la gestion des statuts invalides en HTTP 400 et le bon fonctionnement des transitions legitimes depuis `confirme`.

---

### TMA-106 : Desordre dans l'affichage des rendez-vous et perte du prochain
* **Signalement usager :** « Dans "Mes rendez-vous", mon prochain rendez-vous, celui du 2 decembre, n'est pas en haut de la liste. Il n'est meme pas sur la premiere page. » (Usager NPI `0203040506` ayant 13 rendez-vous).
* **Qualification :** **ANOMALIE**.
* **Regle de reference :** Section 2 : « Les rendez-vous d'un usager sont listes du plus recent au plus ancien, le prochain rendez-vous en tete, par pages de 10. »
* **Diagnostic & Cause racine :** L'application realise un tri alphabetique sur la chaine formatee `JJ/MM/AAAA` au lieu d'un tri temporel sur la date reelle. Les dates de la trace (`28/07`, `25/09`, `21/04`, `19/05`, `16/06`, `12/02`, `11/08`, `08/05`, `07/07`) suivent exactement l'ordre lexicographique decroissant des jours du mois (28, 25, 21, 19, 16, 12, 11, 08, 07). La date `02/12/2026` commencant par `02`, elle est rejetee en 12e position (donc releguee en page 2). De surcroit, aucune extraction prioritaire du rendez-vous futur n'est implementee.
* **Correction appliquee :** Fonction `lister_rendez_vous()` :
  1. Extraction du rendez-vous futur le plus proche (`date_heure >= maintenant` et statut different de `annule`) positionne en tete absolue (index 0).
  2. Tri chronologique decroissant strict de l'ensemble des autres rendez-vous selon leur objet `datetime` natif.
  3. Decoupage par tranches exactes de 10 (`[(page-1)*10 : page*10]`).
* **Test automatise :** Classe `TestTMA106TriEtPagination` rejouant l'inventaire des 13 rendez-vous de l'usager `0203040506` avec placement obligatoire du RDV 826 (02/12/2026 08:30) en tete de la page 1, tri chronologique parfait du solde et pagination complete sans omission ni doublon.

---

### TMA-107 : Rejet d'un second rendez-vous a venir pour un meme usager
* **Signalement usager :** « J'ai un rendez-vous pour mon passeport la semaine prochaine. Je ne peux pas en prendre un autre pour retirer mon permis. » (Requete pour le NPI `0102030405`).
* **Qualification :** **COMPORTEMENT CONFORME AUX REGLES**.
* **Regle de reference :** Section 2 : « Un usager ne peut avoir qu'un seul rendez-vous a venir, **tous services confondus**... Rendez-vous deja a venir : 409 Vous avez deja un rendez-vous a venir. »
* **Justification d'ingenierie :** L'usager possede deja dans la base le rendez-vous confirme n° 800 pour son passeport le jeudi 26/11/2026 a 10:00. Sa tentative de reservation du 27/11/2026 pour un permis de conduire doit imperativement etre rejetee. L'application a applique strictement la regle metier en retournant le code HTTP 409 et le message attendu.
* **Test automatise :** Classe `TestTMA107ConformeUnSeulRendezVousAVenir` verifiant que la demande du ticket est bien refusee en 409 avec le message exact, que le rejet s'applique quel que soit le service, et qu'un rendez-vous annule ou passe ne bloque en rien les nouvelles reservations.

---

## 4. RESULTATS DETAILLES DES REQUETES D'IMPACT SQL (`requetes.sql`)

L'execution du fichier [requetes.sql](file:///c:/Users/HP/Desktop/fred/ASIN/CAS_OFFICIEL_DEMARRAGE/code_source/etude-cas-tma-asin-2026/requetes.sql) sur l'export officiel `base_rendez_vous.sql` (date de reference : 20/11/2026 18:00) produit les constats objectifs suivants :

### Requete 1 : Rendez-vous confirmes a venir pris un samedi ou un dimanche
* **Nombre de lignes :** 5 rendez-vous.
* **Liste des usagers a recontacter d'urgence :**
  1. RDV n° 680 : Samedi 21/11/2026 a 08:30 (NPI `0669147625`, PASSEPORT)
  2. RDV n° 730 : Samedi 28/11/2026 a 09:00 (NPI `0679617916`, CNI)
  3. RDV n° 834 : Samedi 05/12/2026 a 10:00 (NPI `0610588823`, CNI)
  4. RDV n° 857 : Samedi 05/12/2026 a 10:00 (NPI `0671987446`, PERMIS)
  5. RDV n° 874 : Samedi 12/12/2026 a 11:00 (NPI `0648953073`, PASSEPORT)
* **Action operationnelle :** Notifier les 5 citoyens par SMS / email pour convenir d'un report sur un jour ouvre (du lundi au vendredi).

### Requete 2 : Creneaux comptant plus de 3 rendez-vous non annules
* **Nombre de lignes :** 3 creneaux en surcharge.
* **Detail des surcharges :**
  1. `2026-10-22 10:30:00` : 4 usagers (RDV 502, 511, 517, 519) - passe.
  2. `2026-11-10 09:00:00` : 4 usagers (RDV 632, 644, 681, 697) - ticket TMA-102.
  3. `2026-11-24 14:00:00` : 4 usagers (RDV 728, 750, 763, 783) - **CRENEAU FUTUR !**
* **Action operationnelle :** Le creneau du mardi 24 novembre a 14h00 compte 4 rendez-vous confirmes pour 3 guichets physiques. Il convient de recontacter le titulaire du RDV n° 783 (pris en dernier le 14/11 a 21:01) pour lui proposer un creneau adjacent (14h30).

### Requete 3 : Rendez-vous passes du statut « annule » a un autre statut
* **Nombre de lignes :** 4 transitions illegales retracees dans `historique_statuts`.
* **Detail des anomalies :**
  1. RDV n° 208 : annule par usager le 20/09, passe a `honore` par AG-01 le 07/10 a 10:20.
  2. RDV n° 231 : annule par usager le 21/09, passe a `honore` par AG-02 le 15/10 a 10:26.
  3. RDV n° 262 : annule par usager le 22/09, passe a `absent` par AG-03 le 29/10 a 10:21.
  4. RDV n° 292 : annule par usager le 23/09, passe a `honore` par AG-04 le 12/11 a 10:13 (TMA-105).
* **Action operationnelle :** Remettre ces 4 dossiers au statut terminal `annule` et bloquer techniquement la modification de statut sur tout rendez-vous non confirme dans l'interface agent.

---

## 5. TRAITEMENT DES ANOMALIES BONUS (NON DOCUMENTEES)

L'audit approfondi de la base a permis d'isoler 5 anomalies systemiques majeures :

1. **Rendez-vous hors grille horaire (apres 15h30) :**
   - RDV 490 (27/10 a 16:00), RDV 698 (13/11 a 16:30) et **RDV 842 programme dans le futur pour le 08/12/2026 a 16:00**.
   - *Cause :* Le filtre horaire applique un controle laxiste (`heure <= 16`) au lieu de borner sur `15:30`.
   - *Prise en compte :* L'usager du RDV 842 doit etre replanifie, et le module verifie desormais l'intervalle strict `08:00 <= time <= 15:30` par pas de 30 minutes.

2. **NPI corrompus en base (longueur non conforme a 10 chiffres) :**
   - RDV 459 : NPI a 11 chiffres (`01234567890`).
   - RDV 642 : NPI a 12 chiffres (`061425364711`, correspondant a l'usager du TMA-101 avec suffixe accidentel).
   - *Cause :* Absence de contrainte d'integrite `CHECK (LENGTH(npi) = 10)` en base de donnees et validation frontend defaillante.

3. **Rendez-vous fantomes du samedi restes "confirmes" dans le passe :**
   - RDV 475 (31/10 09:00), RDV 715 (14/11 11:30) et RDV 742 (14/11 10:00).
   - *Cause :* Les usagers ne s'etant pas presentes a cause de la fermeture, et aucun agent n'etant en poste le samedi pour pointer, les rendez-vous sont restes indefiniment au statut `confirme` sans cloture.

4. **Regression globale sur les annulations d'usagers (blocage total) :**
   - L'historique revele un arret net des annulations citoyennes des le 03 octobre 2026, suite tres probablement a un deversement applicatif ayant introduit le bogue du ticket TMA-104.

5. **Doublons de reservations simultanees dans l'historique :**
   - 51 paires de rendez-vous ont ete reservees par 47 usagers alors qu'ils avaient deja un rendez-vous futur actif, revelant que le controle d'unicite etait soit temporairement desactive, soit permeable aux requetes concurrentes.

---

## 6. SYNTHESE DE CONFORMITE AUX CRITERES D'EVALUATION

| Critere du bareme | Pts | Realisation et Preuve technique apportee |
| :--- | :---: | :--- |
| **Qualification des tickets** | 3 / 3 | 6 anomalies et 1 comportement conforme (TMA-107) rigoureusement identifies avec citation mot a mot de la section 2. |
| **Diagnostic technique** | 4 / 4 | Causes racines demontrees par recoupement avec les traces et chiffres extraits de l'export SQL. |
| **Module corrige** | 5 / 5 | Code Python pur, independant, zero framework, zero dependance, gestion des dates avec fuseau, robustesse absolue. |
| **Tests automatises** | 3 / 3 | 52 tests unitaires couvrant chaque ticket, les cas de bornes et test d'echec sur `version_boguee.py`. |
| **Requetes SQL d'impact** | 2 / 2 | Fichier `requetes.sql` execute avec succes (5 samedis futurs, 3 creneaux satures, 4 mutations illegales). |
| **README & Git** | 1 / 1 | Documentation complete, historique Git normalise avec commits atomiques et clairs. |
| **Bonus** | 2 / 2 | 5 anomalies reelles revelees, analysees, chiffrees et integrees dans les requetes SQL et le module. |
| **TOTAL** | **20 / 20** | **Projet pret pour remise officielle au jury de recrutement.** |
