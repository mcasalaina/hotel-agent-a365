# HotelOperationsModel

`HotelOperationsModel` is a Direct Lake TMDL semantic model over `HotelGuestServices` aggregate tables plus limited `ops_` shortcuts from `HotelOperations`.

Highlights:

- Direct Lake named expressions are templated with workspace and lakehouse IDs at deploy time.
- Technical IDs are hidden.
- Measures are limited to metrics supported by the committed CSV contract.
- `Food and Beverage Revenue` and `TRevPAR` intentionally return `BLANK()` because the contract has no supported F&B revenue fact.
