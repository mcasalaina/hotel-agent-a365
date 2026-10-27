# HotelOperationsReport

`HotelOperationsReport` is a PBIR project bound by `semanticmodelid={{SEMANTICMODEL_ID}}` at deploy time.

The report currently ships six deployable pages:

1. Executive and property performance
2. Booking pace, demand, and channel mix
3. Guest value and spend
4. Front-desk and stay operations
5. Dining and HoReCa performance
6. Requests, maintenance, disputes, and service recovery

Deploy with `scripts/deploy_semantic_model_and_report.py` as described in
[`HotelOperationsModel`](../semantic-model/README.md). It deploys the model first,
substitutes the returned ID into `definition.pbir`, and verifies the binding and all
six pages from the live report definition. Workspace and item IDs stay external to
the committed PBIR files.
