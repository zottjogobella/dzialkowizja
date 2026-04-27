"""Registry of restrictable response fields and per-role restriction lookup.

The registry is the single source of truth for which fields admins can hide
from non-admin tiers. Each key follows ``<section>.<field>`` so the admin UI
can group them and so backend redaction sites can filter the relevant
subset by prefix.

Restrictions are scoped per ``(organization_id, role)`` — admins configure
``handlowiec`` and ``prawnik`` independently. ``admin`` and ``super_admin``
are never redacted.

Adding a new restrictable field is two steps: register it here, then either
(a) call ``redact()`` / ``is_section_restricted()`` in the endpoint that
returns the data (server-side hiding) or (b) rely on the frontend store
populated from /api/auth/me to hide layout-only elements (banners,
buttons, tab links) that aren't tied to a payload.

Each spec carries a ``group`` heading the admin panel uses to nest related
toggles together so the panel stays scannable as the list grows.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RESTRICTABLE_ROLES, RestrictedField


class FieldSpec(TypedDict):
    label: str
    description: str
    group: str


# Ordered for stable rendering in the admin panel. Order within a group
# defines display order; the grouped UI renders groups in the order their
# first field appears here.
RESTRICTABLE_FIELDS: dict[str, FieldSpec] = {
    # ── Nagłówek działki ──
    "header.tabs": {
        "label": "Pasek zakładek",
        "description": "Cały pasek nawigacyjny pod tytułem. Pojedyncze zakładki znikają automatycznie razem z odpowiadającą im sekcją (np. ukrycie „Transakcje w okolicy” usuwa też przycisk „Transakcje”).",
        "group": "Nagłówek działki",
    },
    "header.pdf_button": {
        "label": "Przycisk RAPORT PDF",
        "description": "Przycisk pobierania raportu PDF w prawym górnym rogu nagłówka.",
        "group": "Nagłówek działki",
    },
    "header.location": {
        "label": "Lokalizacja (miejscowość, ulica, gmina)",
        "description": "Tytułowy podpis lokalizacji obok ID działki.",
        "group": "Nagłówek działki",
    },
    "header.teryt_badge": {
        "label": "Badge TERYT",
        "description": "Pigułka z kodem TERYT po prawej stronie nagłówka.",
        "group": "Nagłówek działki",
    },
    "header.gmina_badge": {
        "label": "Badge gminy",
        "description": "Pigułka z nazwą gminy po prawej stronie nagłówka.",
        "group": "Nagłówek działki",
    },

    # ── Mapa ──
    "section.map": {
        "label": "Cała karta mapy",
        "description": "Pełna sekcja mapy działki wraz z kontrolkami i panelami pod nią.",
        "group": "Mapa",
    },
    "map.download_button": {
        "label": "Pływający przycisk „Pobierz mapę”",
        "description": "Przycisk pobierania widoku mapy w lewym górnym rogu mapy.",
        "group": "Mapa",
    },
    "map.controls": {
        "label": "Cały pasek kontrolek pod mapą",
        "description": "Wszystkie sekcje warstw razem (mapa bazowa, działka, budynki, MPZP, GESUT, linie, pinezki).",
        "group": "Mapa",
    },
    "map.layer.basemap": {
        "label": "Sekcja „Mapa bazowa”",
        "description": "Slider Carto ↔ Orto.",
        "group": "Mapa",
    },
    "map.layer.dzialka": {
        "label": "Sekcja „Działka”",
        "description": "Cała sekcja kontrolek warstwy działki (wymiary boków + styl).",
        "group": "Mapa",
    },
    "map.layer.dzialka.dimensions": {
        "label": "Checkbox „Wymiary boków”",
        "description": "Pojedynczy checkbox włączający etykiety długości boków działki.",
        "group": "Mapa",
    },
    "map.layer.dzialka.style": {
        "label": "Edytor „Styl działki”",
        "description": "Rozwijany panel kolorów wypełnienia, obrysu i grubości obrysu.",
        "group": "Mapa",
    },
    "map.layer.buildings": {
        "label": "Sekcja „Budynki”",
        "description": "Cała sekcja kontrolek warstwy budynków (źródła + przełącznik 2D/3D).",
        "group": "Mapa",
    },
    "map.layer.buildings.toggle3d": {
        "label": "Przycisk 2D/3D budynków",
        "description": "Przycisk przełączający widok budynków między 2D i 3D.",
        "group": "Mapa",
    },
    "map.layer.mpzp": {
        "label": "Sekcja „Plan zagospodarowania (MPZP)”",
        "description": "Warstwa kafelków MPZP z krajowej integracji + slider przezroczystości.",
        "group": "Mapa",
    },
    "map.layer.gesut": {
        "label": "Sekcja „Sieci uzbrojenia (GESUT)”",
        "description": "Cała sekcja warstw GESUT (linie elektroenergetyczne + urządzenia).",
        "group": "Mapa",
    },
    "map.layer.gesut.lines": {
        "label": "GESUT — linie elektroenergetyczne",
        "description": "Pojedynczy checkbox warstwy linii elektroenergetycznych GESUT.",
        "group": "Mapa",
    },
    "map.layer.gesut.devices": {
        "label": "GESUT — urządzenia uzbrojenia",
        "description": "Pojedynczy checkbox warstwy urządzeń uzbrojenia GESUT.",
        "group": "Mapa",
    },
    "map.layer.powerlines": {
        "label": "Sekcja „Linie energetyczne”",
        "description": "Cała sekcja wektorowych warstw linii energetycznych (BDOT, OSM, urządzenia BDOT).",
        "group": "Mapa",
    },
    "map.layer.powerlines.bdot": {
        "label": "Linie energetyczne — BDOT",
        "description": "Warstwa linii BDOT + slider bufora.",
        "group": "Mapa",
    },
    "map.layer.powerlines.osm": {
        "label": "Linie energetyczne — OSM",
        "description": "Warstwa linii OSM + bufory zależne od napięcia.",
        "group": "Mapa",
    },
    "map.layer.powerlines.bdot_devices": {
        "label": "Linie energetyczne — urządzenia BDOT",
        "description": "Warstwa urządzeń BDOT.",
        "group": "Mapa",
    },
    "map.layer.pinezki": {
        "label": "Sekcja „Pinezki”",
        "description": "Cała sekcja kontrolek widoczności pinezek na mapie.",
        "group": "Mapa",
    },
    "map.layer.pinezki.tx": {
        "label": "Pinezki — transakcje",
        "description": "Pojedynczy checkbox pinezek transakcji.",
        "group": "Mapa",
    },
    "map.layer.pinezki.listings": {
        "label": "Pinezki — ogłoszenia",
        "description": "Pojedynczy checkbox pinezek ogłoszeń.",
        "group": "Mapa",
    },
    "map.layer.pinezki.investments": {
        "label": "Pinezki — aktywność inwestycyjna",
        "description": "Pojedynczy checkbox pinezek inwestycji.",
        "group": "Mapa",
    },

    # ── Komplikacje własnościowe ──
    "section.komplikacje": {
        "label": "Cały banner komplikacji",
        "description": "Banner ostrzegawczy „Komplikacje własnościowe” pod kontrolkami mapy.",
        "group": "Komplikacje własnościowe",
    },
    "komplikacje.sluzebnosci": {
        "label": "Flaga „Służebności”",
        "description": "Pojedyncza karta flagi służebności w bannerze komplikacji.",
        "group": "Komplikacje własnościowe",
    },
    "komplikacje.many_owners": {
        "label": "Flaga „10+ współwłaścicieli”",
        "description": "Pojedyncza karta flagi wielu współwłaścicieli.",
        "group": "Komplikacje własnościowe",
    },
    "komplikacje.state_owner": {
        "label": "Flaga „Skarb Państwa”",
        "description": "Pojedyncza karta flagi Skarbu Państwa wśród właścicieli.",
        "group": "Komplikacje własnościowe",
    },
    "komplikacje.no_kw": {
        "label": "Flaga „Brak numeru KW”",
        "description": "Pojedyncza karta flagi braku KW w arkuszu.",
        "group": "Komplikacje własnościowe",
    },

    # ── Strefa · Roszczenie ──
    "section.strefa_roszczenie": {
        "label": "Cały panel Strefa · Roszczenie",
        "description": "Bursztynowy panel pod mapą z kolumnami: Strefy / Wartość działki / Wysokość roszczenia.",
        "group": "Strefa · Roszczenie",
    },
    "strefa.column_strefy": {
        "label": "Kolumna „Strefy”",
        "description": "Lewa kolumna z polem strefy (BDOT/OSM ∩ działka).",
        "group": "Strefa · Roszczenie",
    },
    "strefa.column_wartosc": {
        "label": "Kolumna „Wartość działki”",
        "description": "Środkowa kolumna z inputem wartości działki.",
        "group": "Strefa · Roszczenie",
    },
    "strefa.column_roszczenie": {
        "label": "Kolumna „Wysokość roszczenia”",
        "description": "Prawa kolumna z wyliczonym roszczeniem (BDOT/OSM × 0,5 × pokrycie).",
        "group": "Strefa · Roszczenie",
    },
    "strefa.wartosc_old": {
        "label": "„Poprzednio” pod wartością działki",
        "description": "Wiersz z poprzednią wyceną działki z arkusza.",
        "group": "Strefa · Roszczenie",
    },
    "strefa.roszczenie_old": {
        "label": "„Poprzednio” pod roszczeniem",
        "description": "Wiersz z poprzednią kwotą roszczenia (BDOT/OSM).",
        "group": "Strefa · Roszczenie",
    },

    # ── Księga wieczysta ──
    "section.kw_card": {
        "label": "Cała karta „Księga wieczysta i właściciel”",
        "description": "Cała karta z numerem KW, właścicielami i sekcją PODSTAWOWE.",
        "group": "Księga wieczysta",
    },
    "roszczenia.kw": {
        "label": "Numer KW (chip)",
        "description": "Chip z numerem księgi wieczystej i linkiem do EKW.",
        "group": "Księga wieczysta",
    },
    "roszczenia.entities": {
        "label": "Właściciele (chip)",
        "description": "Chip z listą podmiotów (nazwa + typ + PESEL/NIP) z arkusza roszczeń.",
        "group": "Księga wieczysta",
    },
    "section.basic_facts": {
        "label": "Sekcja PODSTAWOWE",
        "description": "Cała subsekcja PODSTAWOWE w karcie KW.",
        "group": "Księga wieczysta",
    },
    "plot.area": {
        "label": "Pole „Powierzchnia”",
        "description": "Powierzchnia działki w m²/ha (sekcja PODSTAWOWE).",
        "group": "Księga wieczysta",
    },
    "plot.is_buildable": {
        "label": "Pole „Budowlana”",
        "description": "Czy działka jest budowlana (Tak/Nie).",
        "group": "Księga wieczysta",
    },
    "plot.lot_type": {
        "label": "Pole „Typ”",
        "description": "Typ działki (np. rolna, budowlana, leśna).",
        "group": "Księga wieczysta",
    },
    "plot.building_count_bdot": {
        "label": "Pole „Budynki (BDOT)”",
        "description": "Liczba budynków na działce wg BDOT.",
        "group": "Księga wieczysta",
    },

    # ── Argumentacja wyceny ──
    "section.argumentacja": {
        "label": "Cała sekcja „Argumentacja wyceny”",
        "description": "Pełna sekcja wyceny z pewnością, kafelkami metryk i listą argumentów.",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.pewnosc": {
        "label": "Badge pewności",
        "description": "Badge w nagłówku sekcji z kategorią i wynikiem pewności (np. „85/100”).",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.metryki": {
        "label": "Cały rząd kafelków metryk",
        "description": "Wszystkie cztery kafelki: CENA ENSEMBLE, WARTOŚĆ CAŁKOWITA, CENA ROSZCZENIA, WARTOŚĆ ROSZCZENIA.",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.metryki.cena_ensemble": {
        "label": "Kafelek CENA ENSEMBLE",
        "description": "Pojedynczy kafelek z ceną ensemble (zł/m²).",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.metryki.wartosc_total": {
        "label": "Kafelek WARTOŚĆ CAŁKOWITA",
        "description": "Pojedynczy kafelek z wartością całkowitą działki.",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.metryki.cena_roszczenia": {
        "label": "Kafelek CENA ROSZCZENIA",
        "description": "Pojedynczy kafelek z ceną m² wg roszczenia.",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.metryki.wartosc_roszczenia": {
        "label": "Kafelek WARTOŚĆ ROSZCZENIA",
        "description": "Pojedynczy kafelek z wartością roszczenia.",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.segment": {
        "label": "Linia SEGMENT · POKRYCIE",
        "description": "Wiersz z informacją o segmencie rynku i procencie pokrycia działki.",
        "group": "Argumentacja wyceny",
    },
    "argumentacja.argumenty": {
        "label": "Lista argumentów",
        "description": "Lista argumentów wyceny z wagami.",
        "group": "Argumentacja wyceny",
    },

    # ── MPZP ──
    "section.mpzp": {
        "label": "Cała sekcja MPZP",
        "description": "Sekcja z planami zagospodarowania przestrzennego z GUGiK.",
        "group": "Plan zagospodarowania (MPZP)",
    },
    "mpzp.zrodlo": {
        "label": "Link „źródło: GUGiK KI MPZP”",
        "description": "Link do strony źródłowej GUGiK w prawym górnym rogu sekcji.",
        "group": "Plan zagospodarowania (MPZP)",
    },
    "mpzp.tytul": {
        "label": "Pole „Tytuł planu”",
        "description": "Tytuł każdego planu w karcie MPZP.",
        "group": "Plan zagospodarowania (MPZP)",
    },
    "mpzp.przeznaczenie": {
        "label": "Pole „Przeznaczenie”",
        "description": "Przeznaczenie wg planu MPZP.",
        "group": "Plan zagospodarowania (MPZP)",
    },
    "mpzp.uchwala": {
        "label": "Pole „Uchwała”",
        "description": "Numer/treść uchwały planu MPZP.",
        "group": "Plan zagospodarowania (MPZP)",
    },
    "mpzp.meta": {
        "label": "Wiersz Status / Data / Typ planu",
        "description": "Dolny wiersz z metadanymi planu MPZP.",
        "group": "Plan zagospodarowania (MPZP)",
    },
    "mpzp.opis": {
        "label": "Pole „Opis”",
        "description": "Pełny opis planu MPZP.",
        "group": "Plan zagospodarowania (MPZP)",
    },
    "mpzp.linki": {
        "label": "Linki do dokumentu i rysunku planu",
        "description": "Linki „Dokument uchwały” i „Rysunek planu” pod kartą MPZP.",
        "group": "Plan zagospodarowania (MPZP)",
    },

    # ── Plan ogólny gminy ──
    "section.zoning": {
        "label": "Cała sekcja „Plan ogólny gminy”",
        "description": "Cała sekcja z informacjami ze strefy zabudowy planu ogólnego gminy.",
        "group": "Plan ogólny gminy",
    },
    "zoning.status": {
        "label": "Badge statusu planu",
        "description": "Badge ze statusem (obowiązujący / projekt) w prawym górnym rogu sekcji.",
        "group": "Plan ogólny gminy",
    },
    "zoning.symbol": {
        "label": "Pigułka z symbolem strefy",
        "description": "Pigułka z symbolem strefy zabudowy.",
        "group": "Plan ogólny gminy",
    },
    "zoning.name": {
        "label": "Nazwa strefy",
        "description": "Pełna nazwa strefy zabudowy.",
        "group": "Plan ogólny gminy",
    },
    "zoning.constraint.max_height": {
        "label": "Wymóg „Maksymalna wysokość zabudowy”",
        "description": "Wiersz z maksymalną wysokością zabudowy.",
        "group": "Plan ogólny gminy",
    },
    "zoning.constraint.max_coverage": {
        "label": "Wymóg „Maks. udział pow. zabudowy”",
        "description": "Wiersz z maksymalnym udziałem powierzchni zabudowy.",
        "group": "Plan ogólny gminy",
    },
    "zoning.constraint.min_green": {
        "label": "Wymóg „Min. pow. biologicznie czynna”",
        "description": "Wiersz z minimalnym udziałem powierzchni biologicznie czynnej.",
        "group": "Plan ogólny gminy",
    },

    # ── Ochrona przyrody ──
    "section.nature_protection": {
        "label": "Banner ochrony przyrody",
        "description": "Banner informujący, że działka leży w obszarze chronionym (lista form ochrony).",
        "group": "Ochrona przyrody",
    },

    # ── Średnie ceny ──
    "section.average_prices": {
        "label": "Cała sekcja „Średnie ceny w okolicy”",
        "description": "Sekcja z tabelami średnich cen RCN dla gminy i powiatu.",
        "group": "Średnie ceny w okolicy",
    },
    "average_prices.gmina": {
        "label": "Tabela „Gmina”",
        "description": "Pojedyncza tabela średnich cen dla gminy.",
        "group": "Średnie ceny w okolicy",
    },
    "average_prices.powiat_total": {
        "label": "Tabela „Powiat (ogółem)”",
        "description": "Pojedyncza tabela średnich cen dla powiatu (ogółem).",
        "group": "Średnie ceny w okolicy",
    },
    "average_prices.powiat_segments": {
        "label": "Tabela „Powiat — per segment rynku”",
        "description": "Tabela średnich cen dla powiatu rozbita per segment rynku.",
        "group": "Średnie ceny w okolicy",
    },

    # ── Transakcje w okolicy ──
    "section.transactions": {
        "label": "Cała sekcja transakcji",
        "description": "Sekcja tabeli transakcji gruntowych w okolicy działki.",
        "group": "Transakcje w okolicy",
    },
    "transactions.show_outliers": {
        "label": "Checkbox „POKAŻ ODRZUCONE”",
        "description": "Przełącznik pokazywania transakcji oznaczonych jako outlier / nie do wyceny.",
        "group": "Transakcje w okolicy",
    },
    "transactions.type_chips": {
        "label": "Filtry typu (Wszystkie/Gruntowe/Inne)",
        "description": "Pasek chipów filtrujących transakcje wg rodzaju nieruchomości.",
        "group": "Transakcje w okolicy",
    },
    "transactions.col.price": {
        "label": "Kolumna „CENA” w tabeli",
        "description": "Kolumna z ceną transakcji.",
        "group": "Transakcje w okolicy",
    },
    "transactions.col.price_m2": {
        "label": "Kolumna „ZŁ/M²” w tabeli",
        "description": "Kolumna z ceną za m².",
        "group": "Transakcje w okolicy",
    },

    # ── Ogłoszenia w okolicy ──
    "section.listings": {
        "label": "Cała sekcja ogłoszeń",
        "description": "Sekcja ogłoszeń nieruchomości z portali w okolicy działki.",
        "group": "Ogłoszenia w okolicy",
    },
    "listings.active": {
        "label": "Sekcja „Aktywne”",
        "description": "Lista aktywnych ogłoszeń (z licznikiem).",
        "group": "Ogłoszenia w okolicy",
    },
    "listings.inactive": {
        "label": "Sekcja „Nieaktywne”",
        "description": "Lista nieaktywnych ogłoszeń (z licznikiem).",
        "group": "Ogłoszenia w okolicy",
    },
    "listings.card.price": {
        "label": "Pole „Cena” na karcie ogłoszenia",
        "description": "Cena widoczna w karcie ogłoszenia.",
        "group": "Ogłoszenia w okolicy",
    },
    "listings.card.site": {
        "label": "Badge portalu na karcie ogłoszenia",
        "description": "Badge z nazwą portalu, z którego pochodzi ogłoszenie.",
        "group": "Ogłoszenia w okolicy",
    },

    # ── Aktywność inwestycyjna ──
    "section.investments": {
        "label": "Cała sekcja aktywności inwestycyjnej",
        "description": "Sekcja pozwoleń na budowę i zgłoszeń z GUNB RWDZ.",
        "group": "Aktywność inwestycyjna",
    },
    "investments.type_chips": {
        "label": "Filtry typu (Wszystkie/Pozwolenia/Zgłoszenia)",
        "description": "Pasek chipów filtrujących inwestycje wg typu.",
        "group": "Aktywność inwestycyjna",
    },
    "investments.time_window": {
        "label": "Selektor zakresu czasu",
        "description": "Dropdown wyboru okna czasowego (12/24/36 mies., 5 lat).",
        "group": "Aktywność inwestycyjna",
    },
    "investments.card.organ": {
        "label": "Pole „Organ” na karcie inwestycji",
        "description": "Nazwa organu wydającego decyzję na karcie inwestycji.",
        "group": "Aktywność inwestycyjna",
    },

    # ── Inne ──
    "section.snapshots": {
        "label": "Zrzuty mapy (PDF)",
        "description": "Ortofotomapa i mapa bazowa działki używane w generowanym raporcie PDF.",
        "group": "Inne",
    },
}


async def get_restricted_keys(
    db: AsyncSession, organization_id: uuid.UUID | None, role: str
) -> set[str]:
    """Return the set of field keys hidden for ``role`` inside this org.

    Returns an empty set for admin/super_admin (or any role outside
    ``RESTRICTABLE_ROLES``) and for users without an organization.
    """
    if organization_id is None or role not in RESTRICTABLE_ROLES:
        return set()
    rows = await db.execute(
        select(RestrictedField.field_key).where(
            RestrictedField.organization_id == organization_id,
            RestrictedField.role == role,
        )
    )
    return {r[0] for r in rows}


async def get_effective_restrictions(db: AsyncSession, user) -> set[str]:
    """Return the keys hidden from ``user`` right now.

    Admins/super_admins see everything → empty set. Only handlowiec/prawnik
    are subject to org-level hidden fields. This is the function /auth/me
    uses to ship the list to the frontend so layout-only elements (banners,
    buttons, tab links) can be hidden cleanly without a backend payload.
    """
    if user.role not in RESTRICTABLE_ROLES:
        return set()
    return await get_restricted_keys(db, user.organization_id, user.role)


async def is_section_restricted(
    db: AsyncSession, user, section_key: str,
) -> bool:
    """Check if a whole section is hidden for this user's role+org.

    Returns False for admin/super_admin — they always see everything.
    """
    if user.role not in RESTRICTABLE_ROLES:
        return False
    restricted = await get_restricted_keys(db, user.organization_id, user.role)
    return section_key in restricted


def redact(payload: dict, restricted: set[str], prefix: str) -> dict:
    """Remove fields from ``payload`` that are restricted under ``prefix``.

    A key like ``roszczenia.kw`` matches ``prefix='roszczenia'`` and removes
    ``payload['kw']``. Mutates and returns the same dict for convenience.
    """
    pref = f"{prefix}."
    for key in restricted:
        if not key.startswith(pref):
            continue
        field = key[len(pref):]
        if field in payload:
            payload[field] = None
    return payload
