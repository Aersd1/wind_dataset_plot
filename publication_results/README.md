# Result status

- `local_metadata/`: actual supplied-workbook equipment figure, source table, input manifest and rendered QA. No power time series was read for this result.
- `local_validation/`: software test log using temporary artificial fixtures, plus read-only metadata/manifest checks. No artificial figure is presented as a research result.
- `server_query/` and `server_run/`: generated only when the author runs the documented commands on the server. These directories are not populated by this local task.

The local equipment figure includes Offshore and Onshore only, with no model rows or connecting lines. Reference-model parameters remain traceable in the input tables but are not drawn as installed equipment.
