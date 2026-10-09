# D4 reference captures

`d4-api-signatures.json` contains signatures of the original module functions and
SQLiteStore methods. `d4-renderer-data.json` contains plotted line coordinates,
collection offsets, histogram/bar geometry and axis labels for all ten renderers.
Both were captured from **ddf67a85793e8dd64bbac19fe29e7a84634b89f0** (pre-D4)
using Python 3.12.15, Matplotlib 3.10.8 and the unchanged synthetic `example`
fixture in test_d3c_rendering. They are independent expected results, not generated
from the implementation under test. Signature checks normalize only the
`pathlib._local` implementation prefix introduced by Python 3.13 to the public
`pathlib` namespace; a separate original-3.13 capture confirms this difference. Do not regenerate them to silence failures.

Renderer capture: export the baseline with `git archive`, then run
`python scripts/capture_d4_rendering.py BASELINE_CHECKOUT TEMP_OUTPUT`.
The test also retains analytical scientific expectations and their tolerances.
PNG equality was checked separately in the reference environment; cross-platform
acceptance uses represented data plus visual QA rather than PNG byte equality.
