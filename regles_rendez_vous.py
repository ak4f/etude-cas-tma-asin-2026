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
MSG_PASSE = "Impossible de prendre un rendez-vous dans le passé."
MSG_WEEK_END = "Le centre est fermé le week-end."
MSG_HORS_GRILLE = "Créneau invalide : de 08:00 à 15:30, toutes les 30 minutes."
MSG_DEJA_A_VENIR = "Vous avez déjà un rendez-vous à venir."
MSG_COMPLET = "Ce créneau est complet."
MSG_NON_ANNULABLE = "Ce rendez-vous ne peut plus être annulé."
MSG_ANNULATION_TARDIVE = "Annulation impossible moins de 24 h avant le rendez-vous."
MSG_STATUT_INVALIDE = "Statut invalide : honore ou absent."
MSG_CLOTURE = "Ce rendez-vous est déjà clôturé."
# Hors tableau de l'énoncé : rendez-vous inexistant (l'appelant n'a rien trouvé en base).
MSG_INTROUVABLE = "Rendez-vous introuvable."

STATUTS_DEMANDABLES = ("honore", "absent")

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

    Accepte :
    - None : heure réelle actuelle du Bénin (GMT+1).
    - datetime : converti si besoin en heure du Bénin et débarrassé de son fuseau.
    - str : texte au format 'AAAA-MM-JJ HH:MM' ou 'AAAA-MM-JJTHH:MM'.
    """
    if maintenant is None:
        maintenant = datetime.now(FUSEAU_BENIN)
    elif isinstance(maintenant, str):
        for fmt in _FORMATS_DATE:
            try:
                maintenant = datetime.strptime(maintenant, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Instant 'maintenant' illisible : {maintenant!r}")
    elif not isinstance(maintenant, datetime):
        raise TypeError("`maintenant` doit être un datetime ou une chaîne de date valide")

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


def est_jour_ouvre(date_heure: datetime) -> bool:
    """Le centre reçoit du lundi au vendredi. `weekday()` vaut 0 pour lundi, 5 pour
    samedi et 6 pour dimanche : le samedi et le dimanche sont donc tous deux fermés."""
    return date_heure.weekday() <= 4


def est_creneau_valide(date_heure: datetime) -> bool:
    """Créneaux de 30 minutes, de 08:00 (premier) à 15:30 (dernier) inclus."""
    if date_heure.minute not in (0, 30):
        return False
    return PREMIER_CRENEAU <= date_heure.time() <= DERNIER_CRENEAU


@dataclass(frozen=True)
class RendezVous:
    """Rendez-vous tel que le module le manipule (les mêmes champs que la table
    `rendez_vous` de l'export). `statut` vaut confirme, honore, absent ou annule."""

    id: Any
    npi: str
    service: str
    date_heure: datetime
    statut: str


_FORMATS_DATE = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")


def lire_rendez_vous(source: Any) -> Optional[RendezVous]:
    """Accepte un `RendezVous` ou un dictionnaire (par exemple une ligne de la base).
    Retourne None si l'objet est incomplet ou invalide."""
    if isinstance(source, RendezVous):
        return source
    if not isinstance(source, dict):
        return None
    date_heure = source.get("date_heure")
    if isinstance(date_heure, datetime):
        dh = date_heure
    elif isinstance(date_heure, str):
        for fmt in _FORMATS_DATE:
            try:
                dh = datetime.strptime(date_heure, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    else:
        return None
    return RendezVous(
        source.get("id"),
        str(source.get("npi", "")),
        str(source.get("service", "")),
        dh,
        str(source.get("statut", "")),
    )


def a_un_rendez_vous_a_venir(npi: str, rendez_vous: Iterable[RendezVous], maintenant: datetime) -> bool:
    """Un usager a un rendez-vous à venir s'il en possède un `confirme` qui n'a pas
    encore eu lieu, quel que soit le service. Un rendez-vous annulé, honoré ou absent
    ne compte pas, et un rendez-vous resté `confirme` dans le passé non plus."""
    return any(
        r.npi == npi and r.statut == "confirme" and r.date_heure >= maintenant
        for r in rendez_vous
    )


def places_prises(date_heure: datetime, rendez_vous: Iterable[RendezVous]) -> int:
    """Nombre d'usagers occupant le créneau, tous services confondus. Un rendez-vous
    annulé libère sa place."""
    return sum(1 for r in rendez_vous if r.date_heure == date_heure and r.statut != "annule")


def controler_prise(
    npi: Any,
    service: Any,
    date_heure: Any,
    rendez_vous_existants: Iterable[Any] = (),
    maintenant: Any = None,
) -> Resultat:
    """Contrôle une prise de rendez-vous, dans l'ordre du tableau de l'énoncé :
    NPI, service, format de date, passé, week-end, grille horaire, rendez-vous déjà à
    venir, créneau plein. `rendez_vous_existants` contient les rendez-vous connus
    (au minimum ceux de l'usager et ceux du créneau demandé)."""
    refus = valider_npi(npi)
    if refus is not None:
        return refus
    refus = valider_service(service)
    if refus is not None:
        return refus
    debut = lire_date_heure(date_heure)
    if debut is None:
        return _refus(400, MSG_DATE_ILLISIBLE)
    instant = heure_courante(maintenant)
    if debut < instant:
        return _refus(409, MSG_PASSE)
    if not est_jour_ouvre(debut):
        return _refus(409, MSG_WEEK_END)
    if not est_creneau_valide(debut):
        return _refus(409, MSG_HORS_GRILLE)
    connus = [r for r in (lire_rendez_vous(x) for x in rendez_vous_existants) if r is not None]
    if a_un_rendez_vous_a_venir(npi, connus, instant):
        return _refus(409, MSG_DEJA_A_VENIR)
    if places_prises(debut, connus) >= CAPACITE_CRENEAU:
        return _refus(409, MSG_COMPLET)
    return Resultat(True, 201)


def controler_annulation(rendez_vous: Any, maintenant: Any = None) -> Resultat:
    """Contrôle l'annulation d'un rendez-vous par l'usager.

    Seul un rendez-vous `confirme` peut être annulé. L'annulation est possible
    « jusqu'à 24 heures avant l'heure prévue » : un délai d'exactement 24 h est donc
    accepté, un délai de 23 h 59 min est refusé. Le délai se calcule comme
    `heure du rendez-vous - heure courante`, en durée totale (jours compris).
    """
    rdv = lire_rendez_vous(rendez_vous)
    if rdv is None:
        return _refus(404, MSG_INTROUVABLE)
    if rdv.statut != "confirme":
        return _refus(409, MSG_NON_ANNULABLE)
    if rdv.date_heure - heure_courante(maintenant) < DELAI_ANNULATION:
        return _refus(409, MSG_ANNULATION_TARDIVE)
    return Resultat(True, 200)


def controler_changement_statut(rendez_vous: Any, nouveau_statut: Any) -> Resultat:
    """Contrôle le passage d'un rendez-vous à « honoré » ou « absent » par un agent.

    Le statut demandé est vérifié d'abord (400), puis l'état actuel du rendez-vous :
    `honore`, `absent` et `annule` sont définitifs, seul `confirme` peut évoluer (409).
    """
    if not isinstance(nouveau_statut, str) or nouveau_statut not in STATUTS_DEMANDABLES:
        return _refus(400, MSG_STATUT_INVALIDE)
    rdv = lire_rendez_vous(rendez_vous)
    if rdv is None:
        return _refus(404, MSG_INTROUVABLE)
    if rdv.statut != "confirme":
        return _refus(409, MSG_CLOTURE)
    return Resultat(True, 200)


def lister_rendez_vous(
    rendez_vous_usager: Iterable[Any],
    page: int = 1,
    par_page: int = TAILLE_PAGE,
    maintenant: Any = None,
) -> dict[str, Any]:
    """Trie et découpe en pages les rendez-vous d'un usager.

    Règle de tri (section 2) :
    - Le prochain rendez-vous à venir (date_heure >= maintenant et non annulé)
      est placé en tête absolue de liste.
    - Tous les autres rendez-vous sont ensuite triés du plus récent au plus ancien
      (ordre chronologique décroissant selon leur date_heure réelle).
    - Le résultat est découpé par pages de `par_page` (10 par défaut).
    """
    instant = heure_courante(maintenant)
    tous = [r for r in (lire_rendez_vous(x) for x in rendez_vous_usager) if r is not None]

    # Identifier le prochain rendez-vous à venir (le plus proche dans le futur, non annulé)
    a_venir = [r for r in tous if r.date_heure >= instant and r.statut != "annule"]
    prochain = min(a_venir, key=lambda r: r.date_heure) if a_venir else None

    # Les autres rendez-vous (tous sauf le prochain sélectionné)
    autres = [r for r in tous if prochain is None or r.id != prochain.id]
    autres.sort(key=lambda r: r.date_heure, reverse=True)

    ordonnes = ([prochain] if prochain else []) + autres

    # Découpage par page
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


__all__ = [
    "Resultat",
    "RendezVous",
    "controler_prise",
    "controler_annulation",
    "controler_changement_statut",
    "lister_rendez_vous",
    "valider_npi",
    "valider_service",
    "lire_date_heure",
    "heure_courante",
    "CAPACITE_CRENEAU",
    "DELAI_ANNULATION",
    "SERVICES",
]


if __name__ == "__main__":
    print("Module de regles de gestion : Prise de rendez-vous au guichet (ASIN)")
    print("Auteur : ANATO Kodjo Freddy (fredak946@gmail.com)")
    print("Capacite par creneau :", CAPACITE_CRENEAU, "usagers max")
    print("Delai annulation minimum :", DELAI_ANNULATION.total_seconds() / 3600, "heures")
    print("Premier creneau :", PREMIER_CRENEAU.strftime("%H:%M"), "| Dernier creneau :", DERNIER_CRENEAU.strftime("%H:%M"))
    print("Services autorises :", ", ".join(SERVICES))
    print("Auto-diagnostic : Module pret et autonome.")

