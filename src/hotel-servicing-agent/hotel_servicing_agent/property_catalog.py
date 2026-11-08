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
    "HTL-001": "Hotel Seattle Waterfront",
    "HTL-002": "Hotel Vancouver Coal Harbour",
    "HTL-003": "Hotel San Francisco Embarcadero",
    "HTL-004": "Hotel Scottsdale Sonoran Resort",
    "HTL-005": "Hotel Chicago River North",
    "HTL-006": "Hotel New York Midtown",
    "HTL-007": "Hotel Miami South Beach",
    "HTL-008": "Hotel Mexico City Polanco",
    "HTL-009": "Hotel London Mayfair",
    "HTL-010": "Hotel Paris Left Bank",
    "HTL-011": "Hotel Amsterdam Canal Quarter",
    "HTL-012": "Hotel Lisbon Baixa",
    "HTL-013": "Hotel Barcelona Eixample",
    "HTL-014": "Hotel Rome Via Veneto",
    "HTL-015": "Hotel Vienna Ring",
    "HTL-016": "Hotel Buenos Aires Puerto Madero",
    "HTL-017": "Hotel Rio Copacabana",
    "HTL-018": "Hotel Sao Paulo Jardins",
    "HTL-019": "Hotel Lima Miraflores",
    "HTL-020": "Hotel Cartagena Walled City",
}


def official_property_name(property_id: PropertyId) -> str:
    return PROPERTY_NAMES[property_id]
