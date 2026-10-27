from __future__ import annotations

import re
from typing import Literal

type PropertyId = Literal[
    "HTL-001",
    "HTL-002",
    "HTL-003",
    "HTL-004",
    "HTL-005",
    "HTL-006",
    "HTL-007",
    "HTL-008",
    "HTL-009",
    "HTL-010",
    "HTL-011",
    "HTL-012",
    "HTL-013",
    "HTL-014",
    "HTL-015",
    "HTL-016",
    "HTL-017",
    "HTL-018",
    "HTL-019",
    "HTL-020",
]

PROPERTY_NAMES: dict[PropertyId, str] = {
    "HTL-001": "Lyrenza Seattle Waterfront",
    "HTL-002": "Lyrenza Vancouver Coal Harbour",
    "HTL-003": "Lyrenza San Francisco Embarcadero",
    "HTL-004": "Lyrenza Scottsdale Sonoran Resort",
    "HTL-005": "Lyrenza Chicago River North",
    "HTL-006": "Lyrenza New York Midtown",
    "HTL-007": "Lyrenza Miami South Beach",
    "HTL-008": "Lyrenza Mexico City Polanco",
    "HTL-009": "Lyrenza London Mayfair",
    "HTL-010": "Lyrenza Paris Left Bank",
    "HTL-011": "Lyrenza Amsterdam Canal Quarter",
    "HTL-012": "Lyrenza Lisbon Baixa",
    "HTL-013": "Lyrenza Barcelona Eixample",
    "HTL-014": "Lyrenza Rome Via Veneto",
    "HTL-015": "Lyrenza Vienna Ring",
    "HTL-016": "Lyrenza Buenos Aires Puerto Madero",
    "HTL-017": "Lyrenza Rio Copacabana",
    "HTL-018": "Lyrenza Sao Paulo Jardins",
    "HTL-019": "Lyrenza Lima Miraflores",
    "HTL-020": "Lyrenza Cartagena Walled City",
}


def official_property_name(property_id: PropertyId) -> str:
    return PROPERTY_NAMES[property_id]


def property_id_from_text(text: str) -> PropertyId | None:
    normalized = text.casefold()
    id_match = re.search(r"\bHTL-\d{3}\b", text, re.IGNORECASE)
    if id_match:
        candidate = id_match.group(0).upper()
        return next(
            (property_id for property_id in PROPERTY_NAMES if property_id == candidate),
            None,
        )

    full_name_matches = [
        property_id
        for property_id, property_name in PROPERTY_NAMES.items()
        if property_name.casefold() in normalized
    ]
    if len(full_name_matches) == 1:
        return full_name_matches[0]

    token_owners: dict[str, set[PropertyId]] = {}
    for property_id, property_name in PROPERTY_NAMES.items():
        for token in re.findall(r"[a-z0-9]+", property_name.casefold()):
            if len(token) >= 4 and token not in {"hotel", "lyrenza", "resort", "the"}:
                token_owners.setdefault(token, set()).add(property_id)
    abbreviated_matches = {
        next(iter(owners))
        for token, owners in token_owners.items()
        if len(owners) == 1 and re.search(rf"\b{re.escape(token)}\b", normalized)
    }
    return next(iter(abbreviated_matches)) if len(abbreviated_matches) == 1 else None
