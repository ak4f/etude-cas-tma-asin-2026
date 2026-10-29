"""Version reproduisant les anomalies de l'application en production.

Ce module permet de démontrer objectivement l'exigence n° 4 de l'énoncé :
« Chaque test rejoue le cas décrit et échouerait avec le comportement signalé. »

Auteur : ANATO Kodjo Freddy
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Iterable, Optional

# Réimportation des constantes et structures
from regles_rendez_vous import (
    CAPACITE_CRENEAU,
    DELAI_ANNULATION,
    DERNIER_CRENEAU,
    MSG_ANNULATION_TARDIVE,
    MSG_CLOTURE,
    MSG_COMPLET,
    MSG_DATE_ILLISIBLE,
    MSG_DEJA_A_VENIR,
    MSG_HORS_GRILLE,
    MSG_INTROUVABLE,
    MSG_NON_ANNULABLE,
    MSG_NPI,
    MSG_PASSE,
    MSG_SERVICE,
    MSG_STATUT_INVALIDE,
    MSG_WEEK_END,
    PREMIER_CRENEAU,
    SERVICES,
    STATUTS_DEMANDABLES,
    TAILLE_PAGE,
    RendezVous,
    Resultat,
    _refus,
    heure_courante,
    lire_date_heure,
    lire_rendez_vous,
)


def controler_prise(
    npi: Any,
    service: Any,
    date_heure: Any,
    rendez_vous_existants: Iterable[Any] = (),
    maintenant: Any = None,
) -> Resultat:
    # BUG TMA-103 : conversion int directe sans regex -> crash ValueError (erreur 500) si lettre
    if not isinstance(npi, str):
        return _refus(400, MSG_NPI)
    int(npi)  # Lève ValueError si lettre (ex: '06142A3647') -> 500 serveur

    if service not in SERVICES:
        return _refus(400, MSG_SERVICE)

    debut = lire_date_heure(date_heure)
    if debut is None:
        return _refus(400, MSG_DATE_ILLISIBLE)

    instant = heure_courante(maintenant)
    if debut < instant:
        return _refus(409, MSG_PASSE)

    # BUG TMA-101 : seul le dimanche est bloqué (erreur classique getDay()==0 vs weekend)
    # Le samedi (weekday()==5) est accepté à tort !
    if debut.weekday() == 6:
        return _refus(409, MSG_WEEK_END)

    connus = [r for r in (lire_rendez_vous(x) for x in rendez_vous_existants) if r is not None]

    if any(r.npi == npi and r.statut == "confirme" and r.date_heure >= instant for r in connus):
        return _refus(409, MSG_DEJA_A_VENIR)

    # BUG TMA-102 : condition avec erreur de borne (> 3 au lieu de >= 3)
    # Accepte le 4e rendez-vous (n° 697) sur le créneau !
    actifs = sum(1 for r in connus if r.date_heure == debut and r.statut != "annule")
    if actifs > CAPACITE_CRENEAU:
        return _refus(409, MSG_COMPLET)

    return Resultat(True, 201)


def controler_annulation(rendez_vous: Any, maintenant: Any = None) -> Resultat:
    rdv = lire_rendez_vous(rendez_vous)
    if rdv is None:
        return _refus(404, MSG_INTROUVABLE)
    if rdv.statut != "confirme":
        return _refus(409, MSG_NON_ANNULABLE)

    instant = heure_courante(maintenant)
    # BUG TMA-104 : inversion du calcul temporel (maintenant - rdv < 24)
    # Pour un rendez-vous futur, maintenant - rdv est négatif, donc TOUJOURS < 24 h !
    # Toutes les annulations futures sont rejetées en 409 !
    if instant - rdv.date_heure < DELAI_ANNULATION:
        return _refus(409, MSG_ANNULATION_TARDIVE)

    return Resultat(True, 200)


def controler_changement_statut(rendez_vous: Any, nouveau_statut: Any) -> Resultat:
    if nouveau_statut not in STATUTS_DEMANDABLES:
        return _refus(400, MSG_STATUT_INVALIDE)
    rdv = lire_rendez_vous(rendez_vous)
    if rdv is None:
        return _refus(404, MSG_INTROUVABLE)

    # BUG TMA-105 : absence de vérification du statut actuel (aucun contrôle de clôture)
    # Accepte le passage d'un rendez-vous annulé vers honoré !
    return Resultat(True, 200)


def lister_rendez_vous(
    rendez_vous_usager: Iterable[Any],
    page: int = 1,
    par_page: int = TAILLE_PAGE,
    maintenant: Any = None,
) -> dict[str, Any]:
    tous = [r for r in (lire_rendez_vous(x) for x in rendez_vous_usager) if r is not None]

    # BUG TMA-106 : tri textuel sur JJ/MM/AAAA décroissant sans mettre le prochain en tête
    tous_formats = [
        (r.date_heure.strftime("%d/%m/%Y %H:%M"), r)
        for r in tous
    ]
    tous_formats.sort(key=lambda x: x[0], reverse=True)
    ordonnes = [x[1] for x in tous_formats]

    page_num = max(1, int(page))
    debut = (page_num - 1) * par_page
    fin = debut + par_page
    page_elements = ordonnes[debut:fin]

    return {
        "page": page_num,
        "parPage": par_page,
        "total": len(ordonnes),
        "rendezVous": [
            {
                "id": r.id,
                "npi": r.npi,
                "service": r.service,
                "dateHeure": r.date_heure.strftime("%d/%m/%Y %H:%M"),
                "dateHeureIso": r.date_heure.strftime("%Y-%m-%dT%H:%M"),
                "statut": r.statut,
            }
            for r in page_elements
        ],
    }

