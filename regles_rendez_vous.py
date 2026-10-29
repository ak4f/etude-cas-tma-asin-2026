"""Règles de gestion de la prise de rendez-vous au guichet (section 2 de l'énoncé).

Module indépendant de toute base de données et de tout framework : il ne lit et
n'écrit rien, il décide. Chaque fonction reçoit les données nécessaires, y compris
l'heure courante, et renvoie un `Resultat` portant le code HTTP et le message prévus.
Aucune saisie, même hostile, ne doit provoquer d'exception.

Convention de temps : toutes les heures sont celles du Bénin (GMT+1). Les dates sont
des `datetime` naïfs exprimés en heure du Bénin. Un `datetime` portant un fuseau est
converti en heure du Bénin avant traitement.

Auteur : ANATO Kodjo Freddy
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable, Optional

FUSEAU_BENIN = timezone(timedelta(hours=1))

SERVICES = ("PASSEPORT", "CNI", "PERMIS")
CAPACITE_CRENEAU = 3
DELAI_ANNULATION = timedelta(hours=24)
PREMIER_CRENEAU = time(8, 0)
DERNIER_CRENEAU = time(15, 30)
TAILLE_PAGE = 10

# Messages exacts de l'énoncé (tableau de la section 2).
MSG_NPI = "Le NPI doit comporter exactement 10 chiffres."
MSG_SERVICE = "Service inconnu : choisissez PASSEPORT, CNI ou PERMIS."
MSG_DATE_ILLISIBLE = "Date et heure invalides (format attendu : AAAA-MM-JJTHH:MM)."

_RE_NPI = re.compile(r"[0-9]{10}")
_RE_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}")


@dataclass(frozen=True)
class Resultat:
    """Décision du module : `ok` vaut True si l'action est autorisée."""

    ok: bool
    code: int
    message: str = ""


def _refus(code: int, message: str) -> Resultat:
    return Resultat(False, code, message)


def heure_courante(maintenant: Any = None) -> datetime:
    """Ramène l'heure fournie à un `datetime` naïf en heure du Bénin.

    Sans argument, retourne l'heure réelle du Bénin. Le paramètre existe pour que
    les règles soient testables à n'importe quel instant.
    """
    if maintenant is None:
        maintenant = datetime.now(FUSEAU_BENIN)
    if not isinstance(maintenant, datetime):
        raise TypeError("`maintenant` doit être un datetime")
    if maintenant.tzinfo is not None:
        maintenant = maintenant.astimezone(FUSEAU_BENIN).replace(tzinfo=None)
    return maintenant


def valider_npi(npi: Any) -> Optional[Resultat]:
    """Un NPI est composé d'exactement 10 chiffres (0 à 9, sans espace ni saut de ligne).

    `re.fullmatch` avec `[0-9]` évite deux pièges : `\\d` accepte aussi les chiffres
    d'autres alphabets, et `$` accepterait un saut de ligne final.
    """
    if not isinstance(npi, str) or _RE_NPI.fullmatch(npi) is None:
        return _refus(400, MSG_NPI)
    return None


def valider_service(service: Any) -> Optional[Resultat]:
    """Le service doit être exactement PASSEPORT, CNI ou PERMIS (majuscules)."""
    if not isinstance(service, str) or service not in SERVICES:
        return _refus(400, MSG_SERVICE)
    return None


def lire_date_heure(texte: Any) -> Optional[datetime]:
    """Lit `AAAA-MM-JJTHH:MM`. Retourne None si le texte est illisible ou impossible
    (par exemple le 30 février ou 24:00)."""
    if not isinstance(texte, str) or _RE_DATE.fullmatch(texte) is None:
        return None
    try:
        return datetime.strptime(texte, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def controler_prise(
    npi: Any,
    service: Any,
    date_heure: Any,
    rendez_vous_existants: Iterable[Any] = (),
    maintenant: Any = None,
) -> Resultat:
    """Contrôle une prise de rendez-vous, dans l'ordre du tableau de l'énoncé."""
    refus = valider_npi(npi)
    if refus is not None:
        return refus
    refus = valider_service(service)
    if refus is not None:
        return refus
    if lire_date_heure(date_heure) is None:
        return _refus(400, MSG_DATE_ILLISIBLE)
    return Resultat(True, 201)
