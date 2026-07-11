# HotelOperationsOntology

`HotelOperationsOntology` is a deployable Ontology definition that binds actual Phase 1 lakehouse tables to entity and relationship types. It intentionally uses only supported value types (`String`, `DateTime`, `Double`) and actual contract columns.

The ontology does not fabricate associate or service-recovery entities because the committed Phase 1 contract does not contain those tables.
