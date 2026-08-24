# AEEP 0.5 economic evidence proof: deterministic-local-economic-evidence

Domain: text-statistics
Repetitions: 30
Conditions: process-cold, router-warm
Splits: holdout, qualification, training
Route types: aeep-hybrid, direct-http, local-cli, local-mcp, local-python, subscription-baseline, usage-priced-provider
Hybrid qualification/training observations: 40

The JSON artifact is authoritative for per-trial token, resource, failure, and timing dimensions. `unknown` is never rendered as zero.

## Route summary

| Route | Type | Trials | Valid | Median total ms | Median actual cash | Settlement evidence | Quote failures | Settlement failures | Indeterminate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| aeep-hybrid | aeep-hybrid | 60 | 60 | 12.301000 | USD 0 | 6/60 | 0 | 0 | 0 |
| direct-http-mock | direct-http | 60 | 60 | 0.447604 | unknown | 0/60 | 0 | 0 | 0 |
| local-cli | local-cli | 60 | 60 | 27.4712915 | USD 0 | 0/60 | 0 | 0 | 0 |
| local-mcp-stdio | local-mcp | 60 | 60 | 27.1491665 | unknown | 0/60 | 0 | 0 | 0 |
| local-python | local-python | 60 | 60 | 0.0382295 | USD 0 | 0/60 | 0 | 0 | 0 |
| subscription-baseline-unknown-cash | subscription-baseline | 60 | 60 | 0.0326665 | unknown | 0/60 | 0 | 0 | 0 |
| usage-priced-reference | usage-priced-provider | 60 | 60 | 12.816896 | USD 0.0038 | 60/60 | 0 | 0 | 0 |

## Measured trials

| Route | Split / condition / repetition | Valid | Expected | Maximum | Reserved | Captured | Released | Evidence | Prep / quote / execute / settle / total ms |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| aeep-hybrid | holdout / process-cold / 20 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.655000 / 2.052458 / 6.863375 / 0 / 14.117292 |
| direct-http-mock | holdout / process-cold / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.348458 / 0 / 0.348458 |
| local-cli | holdout / process-cold / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.459125 / 0 / 27.459125 |
| local-mcp-stdio | holdout / process-cold / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.232417 / 0 / 27.232417 |
| local-python | holdout / process-cold / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.083500 / 0 / 0.083500 |
| subscription-baseline-unknown-cash | holdout / process-cold / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.039208 / 0 / 0.039208 |
| usage-priced-reference | holdout / process-cold / 20 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.653291 / 1.973000 / 7.321417 / 0.102166 / 12.388083 |
| aeep-hybrid | holdout / process-cold / 21 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.702542 / 2.414125 / 6.622042 / 0 / 15.382167 |
| direct-http-mock | holdout / process-cold / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.406541 / 0 / 0.406541 |
| local-cli | holdout / process-cold / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.824750 / 0 / 27.824750 |
| local-mcp-stdio | holdout / process-cold / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.741833 / 0 / 25.741833 |
| local-python | holdout / process-cold / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.047125 / 0 / 0.047125 |
| subscription-baseline-unknown-cash | holdout / process-cold / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030166 / 0 / 0.030166 |
| usage-priced-reference | holdout / process-cold / 21 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.383875 / 2.487625 / 7.579833 / 0.086167 / 12.914958 |
| aeep-hybrid | holdout / process-cold / 22 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.826624 / 2.207167 / 6.233917 / 0 / 14.897000 |
| direct-http-mock | holdout / process-cold / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.406583 / 0 / 0.406583 |
| local-cli | holdout / process-cold / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.749458 / 0 / 26.749458 |
| local-mcp-stdio | holdout / process-cold / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.968125 / 0 / 25.968125 |
| local-python | holdout / process-cold / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.045792 / 0 / 0.045792 |
| subscription-baseline-unknown-cash | holdout / process-cold / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033625 / 0 / 0.033625 |
| usage-priced-reference | holdout / process-cold / 22 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.721584 / 1.859083 / 7.279708 / 0.085167 / 12.375000 |
| aeep-hybrid | holdout / process-cold / 23 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.547791 / 2.214667 / 6.582500 / 0 / 15.006500 |
| direct-http-mock | holdout / process-cold / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.343334 / 0 / 0.343334 |
| local-cli | holdout / process-cold / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.514083 / 0 / 27.514083 |
| local-mcp-stdio | holdout / process-cold / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.619000 / 0 / 25.619000 |
| local-python | holdout / process-cold / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.046000 / 0 / 0.046000 |
| subscription-baseline-unknown-cash | holdout / process-cold / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033625 / 0 / 0.033625 |
| usage-priced-reference | holdout / process-cold / 23 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.527208 / 2.093417 / 6.562459 / 0.085375 / 11.581875 |
| aeep-hybrid | holdout / process-cold / 24 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.074333 / 2.456375 / 6.581000 / 0 / 14.870459 |
| direct-http-mock | holdout / process-cold / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.354667 / 0 / 0.354667 |
| local-cli | holdout / process-cold / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.489333 / 0 / 26.489333 |
| local-mcp-stdio | holdout / process-cold / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.810375 / 0 / 25.810375 |
| local-python | holdout / process-cold / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.044958 / 0 / 0.044958 |
| subscription-baseline-unknown-cash | holdout / process-cold / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.040333 / 0 / 0.040333 |
| usage-priced-reference | holdout / process-cold / 24 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.603042 / 1.869750 / 8.915667 / 0.126791 / 13.860375 |
| aeep-hybrid | holdout / process-cold / 25 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.498584 / 2.392000 / 6.747709 / 0 / 15.273708 |
| direct-http-mock | holdout / process-cold / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.352625 / 0 / 0.352625 |
| local-cli | holdout / process-cold / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.708750 / 0 / 26.708750 |
| local-mcp-stdio | holdout / process-cold / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.947500 / 0 / 27.947500 |
| local-python | holdout / process-cold / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.071416 / 0 / 0.071416 |
| subscription-baseline-unknown-cash | holdout / process-cold / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031542 / 0 / 0.031542 |
| usage-priced-reference | holdout / process-cold / 25 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.717791 / 1.906375 / 7.649334 / 0.090458 / 12.726292 |
| aeep-hybrid | holdout / process-cold / 26 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.494959 / 2.304166 / 7.101333 / 0 / 15.469250 |
| direct-http-mock | holdout / process-cold / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.409208 / 0 / 0.409208 |
| local-cli | holdout / process-cold / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.634833 / 0 / 26.634833 |
| local-mcp-stdio | holdout / process-cold / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.579791 / 0 / 27.579791 |
| local-python | holdout / process-cold / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.054583 / 0 / 0.054583 |
| subscription-baseline-unknown-cash | holdout / process-cold / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.035042 / 0 / 0.035042 |
| usage-priced-reference | holdout / process-cold / 26 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.523749 / 2.169959 / 7.891958 / 0.086209 / 13.033792 |
| aeep-hybrid | holdout / process-cold / 27 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.861208 / 2.255000 / 6.761042 / 0 / 14.368750 |
| direct-http-mock | holdout / process-cold / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.331750 / 0 / 0.331750 |
| local-cli | holdout / process-cold / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 28.254084 / 0 / 28.254084 |
| local-mcp-stdio | holdout / process-cold / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.889083 / 0 / 27.889083 |
| local-python | holdout / process-cold / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.049041 / 0 / 0.049041 |
| subscription-baseline-unknown-cash | holdout / process-cold / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032334 / 0 / 0.032334 |
| usage-priced-reference | holdout / process-cold / 27 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.371958 / 2.237875 / 9.457001 / 0.111291 / 14.558708 |
| aeep-hybrid | holdout / process-cold / 28 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.970875 / 2.220708 / 7.043209 / 0 / 15.800917 |
| direct-http-mock | holdout / process-cold / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.405792 / 0 / 0.405792 |
| local-cli | holdout / process-cold / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.304875 / 0 / 27.304875 |
| local-mcp-stdio | holdout / process-cold / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.540417 / 0 / 28.540417 |
| local-python | holdout / process-cold / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.044959 / 0 / 0.044959 |
| subscription-baseline-unknown-cash | holdout / process-cold / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.044709 / 0 / 0.044709 |
| usage-priced-reference | holdout / process-cold / 28 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.541334 / 2.136166 / 7.732416 / 0.085917 / 12.840000 |
| aeep-hybrid | holdout / process-cold / 29 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.498624 / 2.227584 / 6.266000 / 0 / 14.523584 |
| direct-http-mock | holdout / process-cold / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.307625 / 0 / 0.307625 |
| local-cli | holdout / process-cold / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.331791 / 0 / 25.331791 |
| local-mcp-stdio | holdout / process-cold / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.717625 / 0 / 25.717625 |
| local-python | holdout / process-cold / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.047041 / 0 / 0.047041 |
| subscription-baseline-unknown-cash | holdout / process-cold / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031833 / 0 / 0.031833 |
| usage-priced-reference | holdout / process-cold / 29 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.512208 / 2.309667 / 7.584084 / 0.092458 / 12.974209 |
| aeep-hybrid | qualification / process-cold / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.447250 / 2.523083 / 12.018292 / 0.151875 / 18.831917 |
| direct-http-mock | qualification / process-cold / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.630792 / 0 / 0.630792 |
| local-cli | qualification / process-cold / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 54.611959 / 0 / 54.611959 |
| local-mcp-stdio | qualification / process-cold / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 39.723667 / 0 / 39.723667 |
| local-python | qualification / process-cold / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.087958 / 0 / 0.087958 |
| subscription-baseline-unknown-cash | qualification / process-cold / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031375 / 0 / 0.031375 |
| usage-priced-reference | qualification / process-cold / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.352124 / 3.308167 / 11.359750 / 0.402000 / 18.852875 |
| aeep-hybrid | qualification / process-cold / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.797208 / 1.622125 / 12.395125 / 0.161125 / 17.483375 |
| direct-http-mock | qualification / process-cold / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.567000 / 0 / 0.567000 |
| local-cli | qualification / process-cold / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 41.009208 / 0 / 41.009208 |
| local-mcp-stdio | qualification / process-cold / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 31.674167 / 0 / 31.674167 |
| local-python | qualification / process-cold / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.055916 / 0 / 0.055916 |
| subscription-baseline-unknown-cash | qualification / process-cold / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.048458 / 0 / 0.048458 |
| usage-priced-reference | qualification / process-cold / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.015875 / 2.008500 / 6.513791 / 0.089709 / 10.921875 |
| aeep-hybrid | qualification / process-cold / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.196625 / 2.175042 / 11.357792 / 0.110875 / 17.234625 |
| direct-http-mock | qualification / process-cold / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.377833 / 0 / 0.377833 |
| local-cli | qualification / process-cold / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 29.175792 / 0 / 29.175792 |
| local-mcp-stdio | qualification / process-cold / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 33.710542 / 0 / 33.710542 |
| local-python | qualification / process-cold / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.042792 / 0 / 0.042792 |
| subscription-baseline-unknown-cash | qualification / process-cold / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033708 / 0 / 0.033708 |
| usage-priced-reference | qualification / process-cold / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.650291 / 1.829875 / 6.427416 / 0.085042 / 10.219750 |
| aeep-hybrid | qualification / process-cold / 3 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.073959 / 2.597500 / 4.402958 / 0 / 10.743916 |
| direct-http-mock | qualification / process-cold / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.384708 / 0 / 0.384708 |
| local-cli | qualification / process-cold / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 29.216792 / 0 / 29.216792 |
| local-mcp-stdio | qualification / process-cold / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 31.116542 / 0 / 31.116542 |
| local-python | qualification / process-cold / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.064834 / 0 / 0.064834 |
| subscription-baseline-unknown-cash | qualification / process-cold / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031875 / 0 / 0.031875 |
| usage-priced-reference | qualification / process-cold / 3 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.755416 / 1.690625 / 6.274041 / 0.083959 / 10.037458 |
| aeep-hybrid | qualification / process-cold / 4 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.667417 / 1.940833 / 4.742083 / 0 / 10.943917 |
| direct-http-mock | qualification / process-cold / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.355625 / 0 / 0.355625 |
| local-cli | qualification / process-cold / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 30.222334 / 0 / 30.222334 |
| local-mcp-stdio | qualification / process-cold / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.965000 / 0 / 27.965000 |
| local-python | qualification / process-cold / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.041791 / 0 / 0.041791 |
| subscription-baseline-unknown-cash | qualification / process-cold / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030708 / 0 / 0.030708 |
| usage-priced-reference | qualification / process-cold / 4 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.062000 / 2.154333 / 7.109875 / 0.084208 / 11.734250 |
| aeep-hybrid | qualification / process-cold / 5 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.575292 / 2.050208 / 4.312208 / 0 / 10.452208 |
| direct-http-mock | qualification / process-cold / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.484792 / 0 / 0.484792 |
| local-cli | qualification / process-cold / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.485292 / 0 / 26.485292 |
| local-mcp-stdio | qualification / process-cold / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.558958 / 0 / 25.558958 |
| local-python | qualification / process-cold / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.037250 / 0 / 0.037250 |
| subscription-baseline-unknown-cash | qualification / process-cold / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030250 / 0 / 0.030250 |
| usage-priced-reference | qualification / process-cold / 5 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.930292 / 1.771250 / 6.892041 / 0.084667 / 10.950458 |
| aeep-hybrid | qualification / process-cold / 6 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.752666 / 1.875542 / 5.022625 / 0 / 11.263416 |
| direct-http-mock | qualification / process-cold / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.350208 / 0 / 0.350208 |
| local-cli | qualification / process-cold / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.234958 / 0 / 27.234958 |
| local-mcp-stdio | qualification / process-cold / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 24.989291 / 0 / 24.989291 |
| local-python | qualification / process-cold / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.041416 / 0 / 0.041416 |
| subscription-baseline-unknown-cash | qualification / process-cold / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031958 / 0 / 0.031958 |
| usage-priced-reference | qualification / process-cold / 6 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.256875 / 1.933458 / 8.698208 / 0.094292 / 13.308791 |
| aeep-hybrid | qualification / process-cold / 7 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.984958 / 1.981750 / 4.603083 / 0 / 10.994875 |
| direct-http-mock | qualification / process-cold / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.337500 / 0 / 0.337500 |
| local-cli | qualification / process-cold / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 28.417542 / 0 / 28.417542 |
| local-mcp-stdio | qualification / process-cold / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.246209 / 0 / 28.246209 |
| local-python | qualification / process-cold / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.044333 / 0 / 0.044333 |
| subscription-baseline-unknown-cash | qualification / process-cold / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030792 / 0 / 0.030792 |
| usage-priced-reference | qualification / process-cold / 7 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.126124 / 1.740917 / 7.580667 / 0.098958 / 11.847292 |
| aeep-hybrid | qualification / process-cold / 8 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.872749 / 2.253667 / 5.660125 / 0 / 12.330375 |
| direct-http-mock | qualification / process-cold / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.363792 / 0 / 0.363792 |
| local-cli | qualification / process-cold / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.746417 / 0 / 27.746417 |
| local-mcp-stdio | qualification / process-cold / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.282125 / 0 / 26.282125 |
| local-python | qualification / process-cold / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.042542 / 0 / 0.042542 |
| subscription-baseline-unknown-cash | qualification / process-cold / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031542 / 0 / 0.031542 |
| usage-priced-reference | qualification / process-cold / 8 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.144124 / 2.072959 / 7.406125 / 0.082250 / 12.020500 |
| aeep-hybrid | qualification / process-cold / 9 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.699083 / 2.048375 / 4.539667 / 0 / 10.766583 |
| direct-http-mock | qualification / process-cold / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.306208 / 0 / 0.306208 |
| local-cli | qualification / process-cold / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.939417 / 0 / 27.939417 |
| local-mcp-stdio | qualification / process-cold / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.106958 / 0 / 25.106958 |
| local-python | qualification / process-cold / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.061292 / 0 / 0.061292 |
| subscription-baseline-unknown-cash | qualification / process-cold / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031125 / 0 / 0.031125 |
| usage-priced-reference | qualification / process-cold / 9 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.199709 / 1.740750 / 7.607000 / 0.084292 / 11.917875 |
| aeep-hybrid | training / process-cold / 10 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.180584 / 2.415875 / 5.611792 / 0 / 12.859625 |
| direct-http-mock | training / process-cold / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.351000 / 0 / 0.351000 |
| local-cli | training / process-cold / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.618500 / 0 / 27.618500 |
| local-mcp-stdio | training / process-cold / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.352791 / 0 / 27.352791 |
| local-python | training / process-cold / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.051625 / 0 / 0.051625 |
| subscription-baseline-unknown-cash | training / process-cold / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030833 / 0 / 0.030833 |
| usage-priced-reference | training / process-cold / 10 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.043750 / 1.865250 / 8.026708 / 0.101709 / 12.310750 |
| aeep-hybrid | training / process-cold / 11 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.844750 / 1.933542 / 5.196500 / 0 / 11.521125 |
| direct-http-mock | training / process-cold / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.396291 / 0 / 0.396291 |
| local-cli | training / process-cold / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.394750 / 0 / 25.394750 |
| local-mcp-stdio | training / process-cold / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.065916 / 0 / 27.065916 |
| local-python | training / process-cold / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.039209 / 0 / 0.039209 |
| subscription-baseline-unknown-cash | training / process-cold / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.035333 / 0 / 0.035333 |
| usage-priced-reference | training / process-cold / 11 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.967376 / 1.855458 / 6.494708 / 0.083750 / 10.661958 |
| aeep-hybrid | training / process-cold / 12 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.391667 / 2.358000 / 5.930208 / 0 / 13.264541 |
| direct-http-mock | training / process-cold / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.378916 / 0 / 0.378916 |
| local-cli | training / process-cold / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.564125 / 0 / 25.564125 |
| local-mcp-stdio | training / process-cold / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.580709 / 0 / 25.580709 |
| local-python | training / process-cold / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.037250 / 0 / 0.037250 |
| subscription-baseline-unknown-cash | training / process-cold / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031375 / 0 / 0.031375 |
| usage-priced-reference | training / process-cold / 12 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.184167 / 1.823250 / 7.246083 / 0.085417 / 11.686542 |
| aeep-hybrid | training / process-cold / 13 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.687292 / 2.257583 / 8.841875 / 0 / 16.448833 |
| direct-http-mock | training / process-cold / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.496584 / 0 / 0.496584 |
| local-cli | training / process-cold / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.450125 / 0 / 27.450125 |
| local-mcp-stdio | training / process-cold / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.750000 / 0 / 25.750000 |
| local-python | training / process-cold / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.042792 / 0 / 0.042792 |
| subscription-baseline-unknown-cash | training / process-cold / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.034083 / 0 / 0.034083 |
| usage-priced-reference | training / process-cold / 13 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.295666 / 2.167584 / 8.260125 / 0.088875 / 13.108375 |
| aeep-hybrid | training / process-cold / 14 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.580208 / 2.252417 / 6.531375 / 0 / 14.119084 |
| direct-http-mock | training / process-cold / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.350125 / 0 / 0.350125 |
| local-cli | training / process-cold / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.551750 / 0 / 26.551750 |
| local-mcp-stdio | training / process-cold / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.883417 / 0 / 26.883417 |
| local-python | training / process-cold / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.046208 / 0 / 0.046208 |
| subscription-baseline-unknown-cash | training / process-cold / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.038167 / 0 / 0.038167 |
| usage-priced-reference | training / process-cold / 14 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.300042 / 2.180125 / 8.184334 / 0.095625 / 13.095500 |
| aeep-hybrid | training / process-cold / 15 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.426958 / 2.068167 / 6.173417 / 0 / 13.261667 |
| direct-http-mock | training / process-cold / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.421458 / 0 / 0.421458 |
| local-cli | training / process-cold / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.645709 / 0 / 25.645709 |
| local-mcp-stdio | training / process-cold / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.009541 / 0 / 25.009541 |
| local-python | training / process-cold / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.086000 / 0 / 0.086000 |
| subscription-baseline-unknown-cash | training / process-cold / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032250 / 0 / 0.032250 |
| usage-priced-reference | training / process-cold / 15 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.145584 / 2.061708 / 6.973958 / 0.084792 / 11.555583 |
| aeep-hybrid | training / process-cold / 16 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.185083 / 2.094625 / 6.292625 / 0 / 13.134250 |
| direct-http-mock | training / process-cold / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.405875 / 0 / 0.405875 |
| local-cli | training / process-cold / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.106917 / 0 / 27.106917 |
| local-mcp-stdio | training / process-cold / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.011084 / 0 / 28.011084 |
| local-python | training / process-cold / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.047208 / 0 / 0.047208 |
| subscription-baseline-unknown-cash | training / process-cold / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032916 / 0 / 0.032916 |
| usage-priced-reference | training / process-cold / 16 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.154000 / 2.050375 / 8.767625 / 0.090417 / 13.366375 |
| aeep-hybrid | training / process-cold / 17 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.361000 / 2.371875 / 6.489667 / 0 / 13.731542 |
| direct-http-mock | training / process-cold / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.361333 / 0 / 0.361333 |
| local-cli | training / process-cold / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.095000 / 0 / 26.095000 |
| local-mcp-stdio | training / process-cold / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.400125 / 0 / 28.400125 |
| local-python | training / process-cold / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.044125 / 0 / 0.044125 |
| subscription-baseline-unknown-cash | training / process-cold / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033667 / 0 / 0.033667 |
| usage-priced-reference | training / process-cold / 17 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.247916 / 2.190792 / 9.169251 / 0.120208 / 14.131584 |
| aeep-hybrid | training / process-cold / 18 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.846708 / 2.107959 / 6.179834 / 0 / 13.655791 |
| direct-http-mock | training / process-cold / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.344375 / 0 / 0.344375 |
| local-cli | training / process-cold / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.067709 / 0 / 26.067709 |
| local-mcp-stdio | training / process-cold / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.883000 / 0 / 26.883000 |
| local-python | training / process-cold / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.059791 / 0 / 0.059791 |
| subscription-baseline-unknown-cash | training / process-cold / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.039750 / 0 / 0.039750 |
| usage-priced-reference | training / process-cold / 18 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.019876 / 2.035958 / 6.796083 / 0.083750 / 11.202959 |
| aeep-hybrid | training / process-cold / 19 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.947875 / 2.275458 / 6.462584 / 0 / 14.257542 |
| direct-http-mock | training / process-cold / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.385041 / 0 / 0.385041 |
| local-cli | training / process-cold / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 28.273667 / 0 / 28.273667 |
| local-mcp-stdio | training / process-cold / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.750084 / 0 / 26.750084 |
| local-python | training / process-cold / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.050292 / 0 / 0.050292 |
| subscription-baseline-unknown-cash | training / process-cold / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.035667 / 0 / 0.035667 |
| usage-priced-reference | training / process-cold / 19 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.128376 / 2.001416 / 7.221208 / 0.083417 / 11.743209 |
| aeep-hybrid | holdout / router-warm / 20 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.317500 / 1.939750 / 5.626625 / 0 / 12.246584 |
| direct-http-mock | holdout / router-warm / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.442959 / 0 / 0.442959 |
| local-cli | holdout / router-warm / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.404833 / 0 / 26.404833 |
| local-mcp-stdio | holdout / router-warm / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.074625 / 0 / 25.074625 |
| local-python | holdout / router-warm / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.034167 / 0 / 0.034167 |
| subscription-baseline-unknown-cash | holdout / router-warm / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.036250 / 0 / 0.036250 |
| usage-priced-reference | holdout / router-warm / 20 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.424500 / 2.225375 / 10.190209 / 0.105916 / 17.291083 |
| aeep-hybrid | holdout / router-warm / 21 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.853000 / 1.896500 / 5.590250 / 0 / 12.720541 |
| direct-http-mock | holdout / router-warm / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.447667 / 0 / 0.447667 |
| local-cli | holdout / router-warm / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.398542 / 0 / 27.398542 |
| local-mcp-stdio | holdout / router-warm / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.257833 / 0 / 28.257833 |
| local-python | holdout / router-warm / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.032458 / 0 / 0.032458 |
| subscription-baseline-unknown-cash | holdout / router-warm / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032292 / 0 / 0.032292 |
| usage-priced-reference | holdout / router-warm / 21 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.964500 / 2.293083 / 8.042792 / 0.087333 / 14.683667 |
| aeep-hybrid | holdout / router-warm / 22 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.286709 / 2.164750 / 5.958291 / 0 / 12.878750 |
| direct-http-mock | holdout / router-warm / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.454916 / 0 / 0.454916 |
| local-cli | holdout / router-warm / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.876166 / 0 / 25.876166 |
| local-mcp-stdio | holdout / router-warm / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.809500 / 0 / 26.809500 |
| local-python | holdout / router-warm / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.033375 / 0 / 0.033375 |
| subscription-baseline-unknown-cash | holdout / router-warm / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031667 / 0 / 0.031667 |
| usage-priced-reference | holdout / router-warm / 22 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.410792 / 2.450875 / 8.721375 / 0.103042 / 16.066166 |
| aeep-hybrid | holdout / router-warm / 23 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.399750 / 2.073708 / 5.343625 / 0 / 12.271625 |
| direct-http-mock | holdout / router-warm / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.512958 / 0 / 0.512958 |
| local-cli | holdout / router-warm / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.736875 / 0 / 27.736875 |
| local-mcp-stdio | holdout / router-warm / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.291833 / 0 / 26.291833 |
| local-python | holdout / router-warm / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.035291 / 0 / 0.035291 |
| subscription-baseline-unknown-cash | holdout / router-warm / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.029375 / 0 / 0.029375 |
| usage-priced-reference | holdout / router-warm / 23 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.724251 / 2.180166 / 9.327958 / 0.087000 / 15.625167 |
| aeep-hybrid | holdout / router-warm / 24 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.129999 / 2.350209 / 5.054250 / 0 / 12.941792 |
| direct-http-mock | holdout / router-warm / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.742750 / 0 / 0.742750 |
| local-cli | holdout / router-warm / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 29.654708 / 0 / 29.654708 |
| local-mcp-stdio | holdout / router-warm / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.481833 / 0 / 25.481833 |
| local-python | holdout / router-warm / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.035000 / 0 / 0.035000 |
| subscription-baseline-unknown-cash | holdout / router-warm / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.029375 / 0 / 0.029375 |
| usage-priced-reference | holdout / router-warm / 24 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.868792 / 2.441083 / 8.744416 / 0.088584 / 15.419959 |
| aeep-hybrid | holdout / router-warm / 25 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.342291 / 1.912875 / 5.251875 / 0 / 11.878125 |
| direct-http-mock | holdout / router-warm / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.676375 / 0 / 0.676375 |
| local-cli | holdout / router-warm / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.483458 / 0 / 27.483458 |
| local-mcp-stdio | holdout / router-warm / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.009541 / 0 / 28.009541 |
| local-python | holdout / router-warm / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029250 / 0 / 0.029250 |
| subscription-baseline-unknown-cash | holdout / router-warm / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.038292 / 0 / 0.038292 |
| usage-priced-reference | holdout / router-warm / 25 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.608042 / 2.566375 / 11.371833 / 0.114709 / 18.993083 |
| aeep-hybrid | holdout / router-warm / 26 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.995792 / 1.994583 / 5.583750 / 0 / 13.000459 |
| direct-http-mock | holdout / router-warm / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.455500 / 0 / 0.455500 |
| local-cli | holdout / router-warm / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.567917 / 0 / 27.567917 |
| local-mcp-stdio | holdout / router-warm / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.879750 / 0 / 25.879750 |
| local-python | holdout / router-warm / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031583 / 0 / 0.031583 |
| subscription-baseline-unknown-cash | holdout / router-warm / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032417 / 0 / 0.032417 |
| usage-priced-reference | holdout / router-warm / 26 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.649875 / 2.256416 / 9.457792 / 0.105625 / 16.791959 |
| aeep-hybrid | holdout / router-warm / 27 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.720916 / 1.933375 / 5.023167 / 0 / 12.012459 |
| direct-http-mock | holdout / router-warm / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.533542 / 0 / 0.533542 |
| local-cli | holdout / router-warm / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 28.209625 / 0 / 28.209625 |
| local-mcp-stdio | holdout / router-warm / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.847667 / 0 / 26.847667 |
| local-python | holdout / router-warm / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029834 / 0 / 0.029834 |
| subscription-baseline-unknown-cash | holdout / router-warm / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033417 / 0 / 0.033417 |
| usage-priced-reference | holdout / router-warm / 27 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.558999 / 2.223209 / 10.644458 / 0.101167 / 17.950333 |
| aeep-hybrid | holdout / router-warm / 28 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.721916 / 1.990167 / 5.572916 / 0 / 12.654750 |
| direct-http-mock | holdout / router-warm / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.406291 / 0 / 0.406291 |
| local-cli | holdout / router-warm / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.431291 / 0 / 27.431291 |
| local-mcp-stdio | holdout / router-warm / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.733500 / 0 / 25.733500 |
| local-python | holdout / router-warm / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031375 / 0 / 0.031375 |
| subscription-baseline-unknown-cash | holdout / router-warm / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.034042 / 0 / 0.034042 |
| usage-priced-reference | holdout / router-warm / 28 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.311833 / 2.342125 / 10.014292 / 0.102292 / 17.105958 |
| aeep-hybrid | holdout / router-warm / 29 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.929667 / 2.105833 / 5.022666 / 0 / 12.373917 |
| direct-http-mock | holdout / router-warm / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.491792 / 0 / 0.491792 |
| local-cli | holdout / router-warm / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.392417 / 0 / 26.392417 |
| local-mcp-stdio | holdout / router-warm / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.975167 / 0 / 27.975167 |
| local-python | holdout / router-warm / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.033208 / 0 / 0.033208 |
| subscription-baseline-unknown-cash | holdout / router-warm / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033542 / 0 / 0.033542 |
| usage-priced-reference | holdout / router-warm / 29 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 5.164751 / 2.320541 / 9.775666 / 0.100334 / 17.746792 |
| aeep-hybrid | qualification / router-warm / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.967625 / 1.752417 / 6.613083 / 0.074167 / 11.725250 |
| direct-http-mock | qualification / router-warm / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.474541 / 0 / 0.474541 |
| local-cli | qualification / router-warm / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.153417 / 0 / 27.153417 |
| local-mcp-stdio | qualification / router-warm / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.030000 / 0 / 26.030000 |
| local-python | qualification / router-warm / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.055083 / 0 / 0.055083 |
| subscription-baseline-unknown-cash | qualification / router-warm / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031459 / 0 / 0.031459 |
| usage-priced-reference | qualification / router-warm / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.151042 / 2.326375 / 7.256958 / 0.090542 / 12.147792 |
| aeep-hybrid | qualification / router-warm / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.801291 / 1.560209 / 6.242541 / 0.081167 / 10.977542 |
| direct-http-mock | qualification / router-warm / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.649583 / 0 / 0.649583 |
| local-cli | qualification / router-warm / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 28.102959 / 0 / 28.102959 |
| local-mcp-stdio | qualification / router-warm / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 40.013375 / 0 / 40.013375 |
| local-python | qualification / router-warm / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029416 / 0 / 0.029416 |
| subscription-baseline-unknown-cash | qualification / router-warm / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030708 / 0 / 0.030708 |
| usage-priced-reference | qualification / router-warm / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.056750 / 2.020916 / 6.865333 / 0.285792 / 11.472958 |
| aeep-hybrid | qualification / router-warm / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.449916 / 1.615250 / 6.881833 / 0.081792 / 11.268875 |
| direct-http-mock | qualification / router-warm / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.645333 / 0 / 0.645333 |
| local-cli | qualification / router-warm / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 38.474875 / 0 / 38.474875 |
| local-mcp-stdio | qualification / router-warm / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 37.227667 / 0 / 37.227667 |
| local-python | qualification / router-warm / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029292 / 0 / 0.029292 |
| subscription-baseline-unknown-cash | qualification / router-warm / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031750 / 0 / 0.031750 |
| usage-priced-reference | qualification / router-warm / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.044958 / 2.075333 / 6.925875 / 0.088166 / 11.366292 |
| aeep-hybrid | qualification / router-warm / 3 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.351084 / 1.662166 / 3.458042 / 0 / 7.743833 |
| direct-http-mock | qualification / router-warm / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.556708 / 0 / 0.556708 |
| local-cli | qualification / router-warm / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 40.455458 / 0 / 40.455458 |
| local-mcp-stdio | qualification / router-warm / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 33.160209 / 0 / 33.160209 |
| local-python | qualification / router-warm / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029791 / 0 / 0.029791 |
| subscription-baseline-unknown-cash | qualification / router-warm / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030250 / 0 / 0.030250 |
| usage-priced-reference | qualification / router-warm / 3 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.120834 / 2.185125 / 7.159500 / 0.086584 / 11.841750 |
| aeep-hybrid | qualification / router-warm / 4 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.925334 / 2.031083 / 3.204417 / 0 / 8.441209 |
| direct-http-mock | qualification / router-warm / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.506833 / 0 / 0.506833 |
| local-cli | qualification / router-warm / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 30.131625 / 0 / 30.131625 |
| local-mcp-stdio | qualification / router-warm / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 31.282166 / 0 / 31.282166 |
| local-python | qualification / router-warm / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030000 / 0 / 0.030000 |
| subscription-baseline-unknown-cash | qualification / router-warm / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.049542 / 0 / 0.049542 |
| usage-priced-reference | qualification / router-warm / 4 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.886334 / 1.978791 / 6.740167 / 0.088750 / 10.936208 |
| aeep-hybrid | qualification / router-warm / 5 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.202208 / 2.086875 / 3.323625 / 0 / 8.893125 |
| direct-http-mock | qualification / router-warm / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.509917 / 0 / 0.509917 |
| local-cli | qualification / router-warm / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 30.008916 / 0 / 30.008916 |
| local-mcp-stdio | qualification / router-warm / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 33.783209 / 0 / 33.783209 |
| local-python | qualification / router-warm / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031708 / 0 / 0.031708 |
| subscription-baseline-unknown-cash | qualification / router-warm / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.043708 / 0 / 0.043708 |
| usage-priced-reference | qualification / router-warm / 5 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.242041 / 2.225542 / 6.771833 / 0.090417 / 11.585333 |
| aeep-hybrid | qualification / router-warm / 6 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.859291 / 1.678917 / 3.639250 / 0 / 8.520125 |
| direct-http-mock | qualification / router-warm / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.500125 / 0 / 0.500125 |
| local-cli | qualification / router-warm / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 35.080708 / 0 / 35.080708 |
| local-mcp-stdio | qualification / router-warm / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 36.130750 / 0 / 36.130750 |
| local-python | qualification / router-warm / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029334 / 0 / 0.029334 |
| subscription-baseline-unknown-cash | qualification / router-warm / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.036209 / 0 / 0.036209 |
| usage-priced-reference | qualification / router-warm / 6 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.200125 / 1.999292 / 7.060375 / 0.087875 / 11.607792 |
| aeep-hybrid | qualification / router-warm / 7 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.813458 / 1.767833 / 3.547292 / 0 / 8.442167 |
| direct-http-mock | qualification / router-warm / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.659250 / 0 / 0.659250 |
| local-cli | qualification / router-warm / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 35.671667 / 0 / 35.671667 |
| local-mcp-stdio | qualification / router-warm / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 35.004917 / 0 / 35.004917 |
| local-python | qualification / router-warm / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030375 / 0 / 0.030375 |
| subscription-baseline-unknown-cash | qualification / router-warm / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.059125 / 0 / 0.059125 |
| usage-priced-reference | qualification / router-warm / 7 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.079292 / 2.039416 / 6.659875 / 0.084667 / 11.087792 |
| aeep-hybrid | qualification / router-warm / 8 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.898084 / 1.955416 / 4.601792 / 0 / 9.793042 |
| direct-http-mock | qualification / router-warm / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.495917 / 0 / 0.495917 |
| local-cli | qualification / router-warm / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 42.512000 / 0 / 42.512000 |
| local-mcp-stdio | qualification / router-warm / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 34.300833 / 0 / 34.300833 |
| local-python | qualification / router-warm / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030333 / 0 / 0.030333 |
| subscription-baseline-unknown-cash | qualification / router-warm / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.052458 / 0 / 0.052458 |
| usage-priced-reference | qualification / router-warm / 8 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.104458 / 2.068000 / 6.742542 / 0.086583 / 11.230083 |
| aeep-hybrid | qualification / router-warm / 9 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.023042 / 1.917125 / 3.840167 / 0 / 9.064625 |
| direct-http-mock | qualification / router-warm / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.523834 / 0 / 0.523834 |
| local-cli | qualification / router-warm / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 34.213750 / 0 / 34.213750 |
| local-mcp-stdio | qualification / router-warm / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 32.575834 / 0 / 32.575834 |
| local-python | qualification / router-warm / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029084 / 0 / 0.029084 |
| subscription-baseline-unknown-cash | qualification / router-warm / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.066375 / 0 / 0.066375 |
| usage-priced-reference | qualification / router-warm / 9 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.589917 / 1.930500 / 7.373209 / 0.089083 / 12.209959 |
| aeep-hybrid | training / router-warm / 10 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.710709 / 1.893083 / 4.204583 / 0 / 10.278500 |
| direct-http-mock | training / router-warm / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.479500 / 0 / 0.479500 |
| local-cli | training / router-warm / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 33.039000 / 0 / 33.039000 |
| local-mcp-stdio | training / router-warm / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.289500 / 0 / 27.289500 |
| local-python | training / router-warm / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030375 / 0 / 0.030375 |
| subscription-baseline-unknown-cash | training / router-warm / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.029875 / 0 / 0.029875 |
| usage-priced-reference | training / router-warm / 10 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.470291 / 2.340334 / 7.603834 / 0.088500 / 12.793792 |
| aeep-hybrid | training / router-warm / 11 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.776042 / 1.992042 / 4.592084 / 0 / 10.789667 |
| direct-http-mock | training / router-warm / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.536917 / 0 / 0.536917 |
| local-cli | training / router-warm / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.677000 / 0 / 26.677000 |
| local-mcp-stdio | training / router-warm / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 29.164667 / 0 / 29.164667 |
| local-python | training / router-warm / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029750 / 0 / 0.029750 |
| subscription-baseline-unknown-cash | training / router-warm / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.029750 / 0 / 0.029750 |
| usage-priced-reference | training / router-warm / 11 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.238292 / 2.106125 / 7.163042 / 0.093708 / 12.992750 |
| aeep-hybrid | training / router-warm / 12 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.500959 / 1.978916 / 4.083167 / 0 / 9.910875 |
| direct-http-mock | training / router-warm / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.780458 / 0 / 0.780458 |
| local-cli | training / router-warm / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 24.937709 / 0 / 24.937709 |
| local-mcp-stdio | training / router-warm / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.971375 / 0 / 26.971375 |
| local-python | training / router-warm / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031834 / 0 / 0.031834 |
| subscription-baseline-unknown-cash | training / router-warm / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.038792 / 0 / 0.038792 |
| usage-priced-reference | training / router-warm / 12 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.592042 / 1.825625 / 8.493624 / 0.095584 / 13.261000 |
| aeep-hybrid | training / router-warm / 13 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.563500 / 1.632500 / 4.500167 / 0 / 10.182459 |
| direct-http-mock | training / router-warm / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.541500 / 0 / 0.541500 |
| local-cli | training / router-warm / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.433667 / 0 / 26.433667 |
| local-mcp-stdio | training / router-warm / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.322500 / 0 / 26.322500 |
| local-python | training / router-warm / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030708 / 0 / 0.030708 |
| subscription-baseline-unknown-cash | training / router-warm / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.029833 / 0 / 0.029833 |
| usage-priced-reference | training / router-warm / 13 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.723708 / 2.189500 / 9.262083 / 0.097667 / 14.696417 |
| aeep-hybrid | training / router-warm / 14 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.558875 / 1.770417 / 4.066833 / 0 / 10.719000 |
| direct-http-mock | training / router-warm / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.447541 / 0 / 0.447541 |
| local-cli | training / router-warm / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.273541 / 0 / 26.273541 |
| local-mcp-stdio | training / router-warm / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 24.478750 / 0 / 24.478750 |
| local-python | training / router-warm / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030959 / 0 / 0.030959 |
| subscription-baseline-unknown-cash | training / router-warm / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031750 / 0 / 0.031750 |
| usage-priced-reference | training / router-warm / 14 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.879416 / 2.317667 / 10.842458 / 0.086792 / 16.441833 |
| aeep-hybrid | training / router-warm / 15 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.840375 / 1.958750 / 4.486667 / 0 / 10.598250 |
| direct-http-mock | training / router-warm / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.495917 / 0 / 0.495917 |
| local-cli | training / router-warm / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 61.489416 / 0 / 61.489416 |
| local-mcp-stdio | training / router-warm / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 37.981334 / 0 / 37.981334 |
| local-python | training / router-warm / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030834 / 0 / 0.030834 |
| subscription-baseline-unknown-cash | training / router-warm / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.069042 / 0 / 0.069042 |
| usage-priced-reference | training / router-warm / 15 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.465292 / 2.328375 / 8.197333 / 0.094125 / 13.359458 |
| aeep-hybrid | training / router-warm / 16 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.988875 / 1.691750 / 4.433292 / 0 / 10.426667 |
| direct-http-mock | training / router-warm / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.429333 / 0 / 0.429333 |
| local-cli | training / router-warm / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.826334 / 0 / 25.826334 |
| local-mcp-stdio | training / router-warm / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.575750 / 0 / 25.575750 |
| local-python | training / router-warm / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031458 / 0 / 0.031458 |
| subscription-baseline-unknown-cash | training / router-warm / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031083 / 0 / 0.031083 |
| usage-priced-reference | training / router-warm / 16 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.698000 / 2.020042 / 7.596792 / 0.092208 / 12.627667 |
| aeep-hybrid | training / router-warm / 17 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.777959 / 1.933500 / 5.001125 / 0 / 11.075750 |
| direct-http-mock | training / router-warm / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.588334 / 0 / 0.588334 |
| local-cli | training / router-warm / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.543458 / 0 / 25.543458 |
| local-mcp-stdio | training / router-warm / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.490208 / 0 / 26.490208 |
| local-python | training / router-warm / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031833 / 0 / 0.031833 |
| subscription-baseline-unknown-cash | training / router-warm / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.052417 / 0 / 0.052417 |
| usage-priced-reference | training / router-warm / 17 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.213834 / 2.171458 / 10.668833 / 0.096167 / 16.472750 |
| aeep-hybrid | training / router-warm / 18 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.557584 / 2.056000 / 4.770250 / 0 / 11.773333 |
| direct-http-mock | training / router-warm / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.518875 / 0 / 0.518875 |
| local-cli | training / router-warm / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.506209 / 0 / 26.506209 |
| local-mcp-stdio | training / router-warm / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.838625 / 0 / 26.838625 |
| local-python | training / router-warm / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.046125 / 0 / 0.046125 |
| subscription-baseline-unknown-cash | training / router-warm / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.037209 / 0 / 0.037209 |
| usage-priced-reference | training / router-warm / 18 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.482250 / 2.264292 / 7.916959 / 0.097875 / 12.981958 |
| aeep-hybrid | training / router-warm / 19 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.147876 / 1.976208 / 6.439667 / 0 / 12.962917 |
| direct-http-mock | training / router-warm / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.525833 / 0 / 0.525833 |
| local-cli | training / router-warm / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 28.466292 / 0 / 28.466292 |
| local-mcp-stdio | training / router-warm / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.455625 / 0 / 28.455625 |
| local-python | training / router-warm / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029958 / 0 / 0.029958 |
| subscription-baseline-unknown-cash | training / router-warm / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031958 / 0 / 0.031958 |
| usage-priced-reference | training / router-warm / 19 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.900291 / 2.179542 / 10.523458 / 0.108709 / 15.990959 |

## Prepared hybrid workflow proof

These multi-step DAG measurements are not included in the single-action route oracle.

| Workflow | Split / condition / repetition | Steps prepared | Quotes | Settlements | Dependency bytes | Valid | Expected | Maximum | Reserved | Captured | Released | Evidence | Prep / quote / execute / settle / total ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| prepared-hybrid-workflow-29 | holdout / process-cold / 29 | 2/2 | 1 | 1 | 14347 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.045916 / 1.992542 / 0 / 0.113708 / 20.695708 |

## Authoritatively costed oracle

- text-statistics-holdout process-cold repetition 20: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 21: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 22: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 23: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 24: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 25: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 26: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 27: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 28: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout process-cold repetition 29: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 20: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 21: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 22: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 23: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 24: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 25: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 26: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 27: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 28: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.
- text-statistics-holdout router-warm repetition 29: AEEP aeep-hybrid; cheapest successful aeep-hybrid; distance 0%.

## Economic gates

- PASS — zero-overcapture: 0 overcapture incident(s)
- PASS — paid-settlement-evidence: 66/66 paid completed trial(s) have quote, reservation, capture, and release evidence
- PASS — partial-capture-release: 66 partial settlement(s) released the remainder
- PASS — unknown-remains-unknown: 180/180 unknown-cash trial(s) retained no amount
- PASS — settlement-oracle: 20/20 measured AEEP selection(s) were within 10% of the cheapest successful authoritatively costed route
- PASS — prepared-hybrid-workflow: 1/1 hybrid workflow trial(s) bound real dependency inputs and carried settlement evidence

## Initial engineering targets

- PASS — task-valid success: AEEP 100% versus strongest measured baseline 100%.
- FAIL — deterministic-domain total-time target: AEEP median 12.301000 ms, fastest measured baseline 0.0326665 ms, reduction -37556.314573%.
- NOT EVALUATED — two-domain 20% model-token target: this local campaign covers one domain and 240 trial(s) with complete model-usage measurement; synthetic subscription usage is excluded from claims.
