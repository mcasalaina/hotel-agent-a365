# Microsoft Fabric artifacts

This directory contains source-controlled Phase 1 artifacts for the hotel workspace:

- `topology.json` defines the single workspace, exactly two lakehouses, limited `ops_` shortcuts, notebook inventory, and deployable downstream artifacts.
- `notebooks/` contains executable Fabric notebooks for load/reset/validation, controlled mutations, aggregate refresh, and data-agent runtime publish.
- `semantic-model/` contains a deployable Direct Lake TMDL definition for `HotelOperationsModel`.
- `report/` contains a deployable PBIR project for `HotelOperationsReport`.
- `ontology/` contains a deployable Ontology definition for `HotelOperationsOntology`.
- `data-agent/` contains the deployable **draft** Data Agent definition for `HotelOperationsAgent`; runtime publication is intentionally separate.

Known Phase 1 limitations are documented inline in the semantic-model blueprint and measure definitions. In particular, the committed CSV contract does not contain an explicit food-and-beverage revenue fact, so `Food and Beverage Revenue` and `TRevPAR` intentionally return `BLANK()` instead of inventing unsupported logic.
