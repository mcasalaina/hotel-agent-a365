from __future__ import annotations

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
