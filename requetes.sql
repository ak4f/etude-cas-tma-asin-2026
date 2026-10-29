-- ==============================================================================
-- REQUETES D'IMPACT SUR L'EXPORT DE LA BASE DE DONNEES (base_rendez_vous.sql)
-- Epreuve pratique TMA Full Stack - ASIN 2026
-- Auteur : ANATO Kodjo Freddy (fredak946@gmail.com)
--
-- Date de reference de l'export : vendredi 20 novembre 2026 a 18 h 00 (heure du Benin).
-- Les requetes ci-dessous sont testees et compatibles SQLite, PostgreSQL et MySQL.
-- ==============================================================================


-- ==============================================================================
-- REQUETE 1 : Rendez-vous confirmes a venir pris un samedi ou un dimanche
-- Objectif : identifier les usagers a prevenir d'urgence avant leur deplacement.
--
-- Resultat attendu sur l'export : 5 rendez-vous trouves (tous des samedis).
-- IDs concernes : 680, 730, 834, 857, 874.
-- ==============================================================================

-- Syntaxe SQLite (strftime '%w' : 0 = dimanche, 6 = samedi) :
SELECT
    r.id,
    r.npi,
    r.service,
    r.date_heure,
    r.statut,
    CASE strftime('%w', r.date_heure)
        WHEN '0' THEN 'Dimanche'
        WHEN '6' THEN 'Samedi'
    END AS jour_ferme
FROM rendez_vous r
WHERE r.statut = 'confirme'
  AND r.date_heure >= '2026-11-20 18:00:00'
  AND strftime('%w', r.date_heure) IN ('0', '6')
ORDER BY r.date_heure ASC;

-- Variante PostgreSQL :
-- SELECT id, npi, service, date_heure, statut
-- FROM rendez_vous
-- WHERE statut = 'confirme'
--   AND date_heure >= '2026-11-20 18:00:00'
--   AND EXTRACT(ISODOW FROM date_heure) IN (6, 7)
-- ORDER BY date_heure ASC;

-- Variante MySQL :
-- SELECT id, npi, service, date_heure, statut
-- FROM rendez_vous
-- WHERE statut = 'confirme'
--   AND date_heure >= '2026-11-20 18:00:00'
--   AND DAYOFWEEK(date_heure) IN (1, 7)
-- ORDER BY date_heure ASC;


-- ==============================================================================
-- REQUETE 2 : Creneaux comptant plus de 3 rendez-vous non annules
-- Objectif : detecter les surcharges de guichets (capacite maximale de 3 usagers).
--
-- Resultat attendu sur l'export : 3 creneaux en surcharge (4 usagers chacun).
-- 1. 2026-10-22 10:30:00 (RDV 502, 511, 517, 519) - passe
-- 2. 2026-11-10 09:00:00 (RDV 632, 644, 681, 697) - ticket TMA-102
-- 3. 2026-11-24 14:00:00 (RDV 728, 750, 763, 783) - CRENEAU FUTUR A PREVENIR !
-- ==============================================================================

SELECT
    date_heure AS creneau,
    COUNT(*) AS total_usagers,
    GROUP_CONCAT(id) AS liste_ids_rdv
FROM rendez_vous
WHERE statut != 'annule'
GROUP BY date_heure
HAVING COUNT(*) > 3
ORDER BY date_heure ASC;

-- Variante PostgreSQL / MySQL (remplacer GROUP_CONCAT par STRING_AGG en PostgreSQL) :
-- PostgreSQL : STRING_AGG(id::text, ', ')
-- MySQL : GROUP_CONCAT(id ORDER BY id SEPARATOR ', ')


-- ==============================================================================
-- REQUETE 3 : Rendez-vous passes du statut "annule" a un autre statut
-- Objectif : tracer les mutations illegales depuis un statut terminal.
--
-- Resultat attendu sur l'export : 4 rendez-vous violant la definitivite des statuts.
-- 1. RDV 208 : modifie le 2026-10-07 10:20 par AG-01 (annule -> honore)
-- 2. RDV 231 : modifie le 2026-10-15 10:26 par AG-02 (annule -> honore)
-- 3. RDV 262 : modifie le 2026-10-29 10:21 par AG-03 (annule -> absent)
-- 4. RDV 292 : modifie le 2026-11-12 10:13 par AG-04 (annule -> honore) - ticket TMA-105
-- ==============================================================================

SELECT
    h.id AS id_historique,
    h.rendez_vous_id,
    r.npi,
    r.service,
    r.date_heure AS date_rendez_vous,
    h.ancien_statut,
    h.nouveau_statut,
    h.modifie_le,
    h.modifie_par
FROM historique_statuts h
JOIN rendez_vous r ON r.id = h.rendez_vous_id
WHERE h.ancien_statut = 'annule'
  AND h.nouveau_statut != 'annule'
ORDER BY h.modifie_le ASC;


-- ==============================================================================
-- REQUETES BONUS : ANOMALIES NON DOCUMENTEES IDENTIFIEES DANS L'EXPORT
-- ==============================================================================

-- BONUS 1 : Rendez-vous programmes hors grille horaire (> 15:30)
-- Resultat : 3 rendez-vous, dont le n° 842 programme dans le futur a 16:00 !
SELECT
    id,
    npi,
    service,
    date_heure,
    statut,
    cree_le
FROM rendez_vous
WHERE strftime('%H:%M', date_heure) NOT BETWEEN '08:00' AND '15:30'
ORDER BY date_heure ASC;


-- BONUS 2 : NPI de longueur invalide (differente d'exactement 10 chiffres)
-- Resultat : RDV 459 (11 chiffres) et RDV 642 (12 chiffres, saisie double 11).
SELECT
    id,
    npi,
    LENGTH(npi) AS longueur_npi,
    service,
    date_heure,
    statut
FROM rendez_vous
WHERE LENGTH(npi) != 10
   OR npi GLOB '*[^0-9]*'
ORDER BY id ASC;


-- BONUS 3 : Rendez-vous passes restes au statut "confirme" (rendez-vous fantomes)
-- Resultat : 3 rendez-vous passes (samedis 31/10 et 14/11), jamais honores ni absents.
SELECT
    id,
    npi,
    service,
    date_heure,
    statut,
    cree_le
FROM rendez_vous
WHERE statut = 'confirme'
  AND date_heure < '2026-11-20 18:00:00'
ORDER BY date_heure ASC;


-- BONUS 4 : Usagers ayant reserve un second rendez-vous alors qu'un etait deja a venir
-- Resultat : 51 paires de rendez-vous identifiees dans l'historique.
SELECT
    a.id AS rdv_initial_id,
    b.id AS rdv_second_id,
    a.npi,
    a.date_heure AS date_initiale,
    b.date_heure AS date_seconde,
    b.cree_le AS date_creation_second,
    a.service AS service_initial,
    b.service AS service_second
FROM rendez_vous a
JOIN rendez_vous b ON a.npi = b.npi AND a.id < b.id
WHERE b.cree_le < a.date_heure
  AND NOT EXISTS (
      SELECT 1 FROM historique_statuts h
      WHERE h.rendez_vous_id = a.id
        AND h.nouveau_statut = 'annule'
        AND h.modifie_le <= b.cree_le
  )
ORDER BY b.cree_le ASC;
