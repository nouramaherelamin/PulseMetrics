# Third-party notices and source provenance

`native/vendor/sqlite3.c` and `sqlite3.h` are the SQLite3.45.3 amalgamation reused from the received project. SQLite's original public-domain disclaimer/blessing remains in these files. No extension loading is enabled.

`native/vendor/cJSON.c` and `cJSON.h` are the compact adaptation reused from the received project, not a verified upstream release. The original copyright remains in the C file and the full MIT permission notice remains in the header. V2 adds strict numeric grammar, finite-number checks, bounded nesting, full-input validation and Unicode escape decoding. The separate first-party JSON adapter adds duplicate-field rejection and bounded serialization. Preserve the header's notice with distributions.

The first-party C foundation and initial five native tests are adapted from the received PulseMetrics implementation. Changes and fresh build evidence are recorded in Git and `PROGRESS.md`. This records source provenance; it does not assign team credit or select a license for the first-party project. Project licensing/publication remains subject to project-lead approval.

Python dependencies are declared, not bundled. See [installed license metadata](docs/dependency-licenses.md); missing declarations require distribution-file review before bundling. Upstream notices remain intact. Provenance alone does not establish publication rights. See [publication provenance](docs/publication.md).
