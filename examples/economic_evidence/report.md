# AEEP 0.4 economic evidence proof: deterministic-local-economic-evidence

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
| aeep-hybrid | aeep-hybrid | 60 | 60 | 11.2256875 | USD 0 | 6/60 | 0 | 0 | 0 |
| direct-http-mock | direct-http | 60 | 60 | 0.472271 | unknown | 0/60 | 0 | 0 | 0 |
| local-cli | local-cli | 60 | 60 | 26.520750 | USD 0 | 0/60 | 0 | 0 | 0 |
| local-mcp-stdio | local-mcp | 60 | 60 | 26.082583 | unknown | 0/60 | 0 | 0 | 0 |
| local-python | local-python | 60 | 60 | 0.0356875 | USD 0 | 0/60 | 0 | 0 | 0 |
| subscription-baseline-unknown-cash | subscription-baseline | 60 | 60 | 0.032354 | unknown | 0/60 | 0 | 0 | 0 |
| usage-priced-reference | usage-priced-provider | 60 | 60 | 11.174583 | USD 0.0038 | 60/60 | 0 | 0 | 0 |

## Measured trials

| Route | Split / condition / repetition | Valid | Expected | Maximum | Reserved | Captured | Released | Evidence | Prep / quote / execute / settle / total ms |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| aeep-hybrid | holdout / process-cold / 20 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.506125 / 2.199500 / 6.176792 / 0 / 13.574542 |
| direct-http-mock | holdout / process-cold / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.362625 / 0 / 0.362625 |
| local-cli | holdout / process-cold / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 32.651750 / 0 / 32.651750 |
| local-mcp-stdio | holdout / process-cold / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 43.775333 / 0 / 43.775333 |
| local-python | holdout / process-cold / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.059000 / 0 / 0.059000 |
| subscription-baseline-unknown-cash | holdout / process-cold / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.036333 / 0 / 0.036333 |
| usage-priced-reference | holdout / process-cold / 20 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.403208 / 2.948542 / 6.169918 / 0.070791 / 11.850875 |
| aeep-hybrid | holdout / process-cold / 21 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.235417 / 1.881958 / 6.384166 / 0 / 14.108500 |
| direct-http-mock | holdout / process-cold / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.359958 / 0 / 0.359958 |
| local-cli | holdout / process-cold / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 33.648708 / 0 / 33.648708 |
| local-mcp-stdio | holdout / process-cold / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 34.665667 / 0 / 34.665667 |
| local-python | holdout / process-cold / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.069041 / 0 / 0.069041 |
| subscription-baseline-unknown-cash | holdout / process-cold / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032458 / 0 / 0.032458 |
| usage-priced-reference | holdout / process-cold / 21 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.282958 / 1.909708 / 7.010500 / 0.088875 / 11.602125 |
| aeep-hybrid | holdout / process-cold / 22 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.744126 / 1.977791 / 6.304959 / 0 / 13.510792 |
| direct-http-mock | holdout / process-cold / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.466708 / 0 / 0.466708 |
| local-cli | holdout / process-cold / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 32.288041 / 0 / 32.288041 |
| local-mcp-stdio | holdout / process-cold / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 34.858625 / 0 / 34.858625 |
| local-python | holdout / process-cold / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.042958 / 0 / 0.042958 |
| subscription-baseline-unknown-cash | holdout / process-cold / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032000 / 0 / 0.032000 |
| usage-priced-reference | holdout / process-cold / 22 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.318375 / 1.995875 / 6.727375 / 0.078167 / 11.405792 |
| aeep-hybrid | holdout / process-cold / 23 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.182791 / 1.873667 / 5.520792 / 0 / 12.000083 |
| direct-http-mock | holdout / process-cold / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.364083 / 0 / 0.364083 |
| local-cli | holdout / process-cold / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.104208 / 0 / 26.104208 |
| local-mcp-stdio | holdout / process-cold / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.662334 / 0 / 25.662334 |
| local-python | holdout / process-cold / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.079208 / 0 / 0.079208 |
| subscription-baseline-unknown-cash | holdout / process-cold / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031625 / 0 / 0.031625 |
| usage-priced-reference | holdout / process-cold / 23 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.222166 / 1.829584 / 6.699834 / 0.075250 / 11.111375 |
| aeep-hybrid | holdout / process-cold / 24 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.886958 / 1.563667 / 5.263875 / 0 / 12.245166 |
| direct-http-mock | holdout / process-cold / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.383500 / 0 / 0.383500 |
| local-cli | holdout / process-cold / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.501416 / 0 / 26.501416 |
| local-mcp-stdio | holdout / process-cold / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.848208 / 0 / 26.848208 |
| local-python | holdout / process-cold / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.038042 / 0 / 0.038042 |
| subscription-baseline-unknown-cash | holdout / process-cold / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032333 / 0 / 0.032333 |
| usage-priced-reference | holdout / process-cold / 24 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.972333 / 1.855917 / 6.806458 / 0.078042 / 10.958542 |
| aeep-hybrid | holdout / process-cold / 25 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.628667 / 1.852375 / 6.227709 / 0 / 13.185416 |
| direct-http-mock | holdout / process-cold / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.326583 / 0 / 0.326583 |
| local-cli | holdout / process-cold / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.502083 / 0 / 27.502083 |
| local-mcp-stdio | holdout / process-cold / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.074791 / 0 / 26.074791 |
| local-python | holdout / process-cold / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.034375 / 0 / 0.034375 |
| subscription-baseline-unknown-cash | holdout / process-cold / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031958 / 0 / 0.031958 |
| usage-priced-reference | holdout / process-cold / 25 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.012083 / 1.696583 / 6.835583 / 0.079500 / 10.875166 |
| aeep-hybrid | holdout / process-cold / 26 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.764958 / 1.653250 / 6.472625 / 0 / 13.324791 |
| direct-http-mock | holdout / process-cold / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.393000 / 0 / 0.393000 |
| local-cli | holdout / process-cold / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.078083 / 0 / 26.078083 |
| local-mcp-stdio | holdout / process-cold / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.647375 / 0 / 26.647375 |
| local-python | holdout / process-cold / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.041375 / 0 / 0.041375 |
| subscription-baseline-unknown-cash | holdout / process-cold / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033042 / 0 / 0.033042 |
| usage-priced-reference | holdout / process-cold / 26 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.043709 / 1.831750 / 6.802959 / 0.073875 / 11.023458 |
| aeep-hybrid | holdout / process-cold / 27 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 5.073625 / 2.024042 / 5.874333 / 0 / 13.481584 |
| direct-http-mock | holdout / process-cold / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.362458 / 0 / 0.362458 |
| local-cli | holdout / process-cold / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 24.999958 / 0 / 24.999958 |
| local-mcp-stdio | holdout / process-cold / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.392166 / 0 / 25.392166 |
| local-python | holdout / process-cold / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.040958 / 0 / 0.040958 |
| subscription-baseline-unknown-cash | holdout / process-cold / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.035541 / 0 / 0.035541 |
| usage-priced-reference | holdout / process-cold / 27 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.335541 / 1.884250 / 6.386083 / 0.075125 / 10.964416 |
| aeep-hybrid | holdout / process-cold / 28 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.943958 / 1.599417 / 5.531167 / 0 / 12.585833 |
| direct-http-mock | holdout / process-cold / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.356042 / 0 / 0.356042 |
| local-cli | holdout / process-cold / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.656334 / 0 / 25.656334 |
| local-mcp-stdio | holdout / process-cold / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.536375 / 0 / 25.536375 |
| local-python | holdout / process-cold / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.037000 / 0 / 0.037000 |
| subscription-baseline-unknown-cash | holdout / process-cold / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031167 / 0 / 0.031167 |
| usage-priced-reference | holdout / process-cold / 28 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.044666 / 1.697875 / 6.884750 / 0.079875 / 11.009000 |
| aeep-hybrid | holdout / process-cold / 29 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.921499 / 1.789417 / 5.412334 / 0 / 12.528209 |
| direct-http-mock | holdout / process-cold / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.337625 / 0 / 0.337625 |
| local-cli | holdout / process-cold / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.615875 / 0 / 25.615875 |
| local-mcp-stdio | holdout / process-cold / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 23.996000 / 0 / 23.996000 |
| local-python | holdout / process-cold / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.034334 / 0 / 0.034334 |
| subscription-baseline-unknown-cash | holdout / process-cold / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031584 / 0 / 0.031584 |
| usage-priced-reference | holdout / process-cold / 29 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.120292 / 1.904833 / 6.252916 / 0.071084 / 10.628834 |
| aeep-hybrid | qualification / process-cold / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.354166 / 2.137542 / 10.047499 / 0.108834 / 15.136125 |
| direct-http-mock | qualification / process-cold / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.600792 / 0 / 0.600792 |
| local-cli | qualification / process-cold / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.788542 / 0 / 26.788542 |
| local-mcp-stdio | qualification / process-cold / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.635583 / 0 / 25.635583 |
| local-python | qualification / process-cold / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.044083 / 0 / 0.044083 |
| subscription-baseline-unknown-cash | qualification / process-cold / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031375 / 0 / 0.031375 |
| usage-priced-reference | qualification / process-cold / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.952041 / 1.981792 / 5.921583 / 0.091667 / 10.228000 |
| aeep-hybrid | qualification / process-cold / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.487792 / 1.937500 / 10.024750 / 0.086042 / 14.937417 |
| direct-http-mock | qualification / process-cold / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.420583 / 0 / 0.420583 |
| local-cli | qualification / process-cold / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.002333 / 0 / 26.002333 |
| local-mcp-stdio | qualification / process-cold / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.996708 / 0 / 25.996708 |
| local-python | qualification / process-cold / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.043500 / 0 / 0.043500 |
| subscription-baseline-unknown-cash | qualification / process-cold / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033375 / 0 / 0.033375 |
| usage-priced-reference | qualification / process-cold / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.957958 / 1.770542 / 5.950959 / 0.072333 / 10.026625 |
| aeep-hybrid | qualification / process-cold / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.261166 / 2.051334 / 10.617792 / 0.085500 / 16.482167 |
| direct-http-mock | qualification / process-cold / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.342375 / 0 / 0.342375 |
| local-cli | qualification / process-cold / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.553791 / 0 / 26.553791 |
| local-mcp-stdio | qualification / process-cold / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.081292 / 0 / 25.081292 |
| local-python | qualification / process-cold / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.047667 / 0 / 0.047667 |
| subscription-baseline-unknown-cash | qualification / process-cold / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.036791 / 0 / 0.036791 |
| usage-priced-reference | qualification / process-cold / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.071792 / 1.852125 / 6.968126 / 0.074208 / 11.236583 |
| aeep-hybrid | qualification / process-cold / 3 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.245334 / 1.899166 / 4.657542 / 0 / 10.253417 |
| direct-http-mock | qualification / process-cold / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.368750 / 0 / 0.368750 |
| local-cli | qualification / process-cold / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.934792 / 0 / 25.934792 |
| local-mcp-stdio | qualification / process-cold / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.995250 / 0 / 26.995250 |
| local-python | qualification / process-cold / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.045625 / 0 / 0.045625 |
| subscription-baseline-unknown-cash | qualification / process-cold / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032709 / 0 / 0.032709 |
| usage-priced-reference | qualification / process-cold / 3 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.733625 / 1.932209 / 7.261417 / 0.084791 / 11.310708 |
| aeep-hybrid | qualification / process-cold / 4 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.750292 / 2.058750 / 4.848459 / 0 / 10.076958 |
| direct-http-mock | qualification / process-cold / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.373917 / 0 / 0.373917 |
| local-cli | qualification / process-cold / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.369042 / 0 / 26.369042 |
| local-mcp-stdio | qualification / process-cold / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.415625 / 0 / 25.415625 |
| local-python | qualification / process-cold / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.051084 / 0 / 0.051084 |
| subscription-baseline-unknown-cash | qualification / process-cold / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.034292 / 0 / 0.034292 |
| usage-priced-reference | qualification / process-cold / 4 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.933501 / 1.723166 / 6.399709 / 0.074333 / 10.392167 |
| aeep-hybrid | qualification / process-cold / 5 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.720791 / 1.960250 / 6.064625 / 0 / 11.221292 |
| direct-http-mock | qualification / process-cold / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.375709 / 0 / 0.375709 |
| local-cli | qualification / process-cold / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.195084 / 0 / 27.195084 |
| local-mcp-stdio | qualification / process-cold / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.327459 / 0 / 25.327459 |
| local-python | qualification / process-cold / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.045000 / 0 / 0.045000 |
| subscription-baseline-unknown-cash | qualification / process-cold / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032833 / 0 / 0.032833 |
| usage-priced-reference | qualification / process-cold / 5 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.858208 / 1.682708 / 6.069042 / 0.075041 / 9.937417 |
| aeep-hybrid | qualification / process-cold / 6 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.554708 / 2.011000 / 4.383750 / 0 / 10.456500 |
| direct-http-mock | qualification / process-cold / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.392542 / 0 / 0.392542 |
| local-cli | qualification / process-cold / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.012709 / 0 / 26.012709 |
| local-mcp-stdio | qualification / process-cold / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.548209 / 0 / 25.548209 |
| local-python | qualification / process-cold / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.044666 / 0 / 0.044666 |
| subscription-baseline-unknown-cash | qualification / process-cold / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033333 / 0 / 0.033333 |
| usage-priced-reference | qualification / process-cold / 6 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.915792 / 1.768292 / 7.253792 / 0.079250 / 11.279208 |
| aeep-hybrid | qualification / process-cold / 7 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.832834 / 2.139541 / 4.135125 / 0 / 9.543625 |
| direct-http-mock | qualification / process-cold / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.435250 / 0 / 0.435250 |
| local-cli | qualification / process-cold / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.325958 / 0 / 26.325958 |
| local-mcp-stdio | qualification / process-cold / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.090375 / 0 / 26.090375 |
| local-python | qualification / process-cold / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.055750 / 0 / 0.055750 |
| subscription-baseline-unknown-cash | qualification / process-cold / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031041 / 0 / 0.031041 |
| usage-priced-reference | qualification / process-cold / 7 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.782042 / 1.767000 / 6.237875 / 0.070042 / 10.091208 |
| aeep-hybrid | qualification / process-cold / 8 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.422000 / 1.994875 / 4.711042 / 0 / 10.581000 |
| direct-http-mock | qualification / process-cold / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.387209 / 0 / 0.387209 |
| local-cli | qualification / process-cold / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.957792 / 0 / 25.957792 |
| local-mcp-stdio | qualification / process-cold / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 24.886625 / 0 / 24.886625 |
| local-python | qualification / process-cold / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.038250 / 0 / 0.038250 |
| subscription-baseline-unknown-cash | qualification / process-cold / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030125 / 0 / 0.030125 |
| usage-priced-reference | qualification / process-cold / 8 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.737333 / 1.673833 / 6.818125 / 0.073625 / 10.553333 |
| aeep-hybrid | qualification / process-cold / 9 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.935167 / 1.998042 / 4.364042 / 0 / 9.756875 |
| direct-http-mock | qualification / process-cold / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.346708 / 0 / 0.346708 |
| local-cli | qualification / process-cold / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.866875 / 0 / 26.866875 |
| local-mcp-stdio | qualification / process-cold / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.005208 / 0 / 26.005208 |
| local-python | qualification / process-cold / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.060625 / 0 / 0.060625 |
| subscription-baseline-unknown-cash | qualification / process-cold / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031167 / 0 / 0.031167 |
| usage-priced-reference | qualification / process-cold / 9 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.781917 / 1.848500 / 5.781084 / 0.066083 / 9.726000 |
| aeep-hybrid | training / process-cold / 10 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.966542 / 2.044083 / 4.890125 / 0 / 10.310625 |
| direct-http-mock | training / process-cold / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.332958 / 0 / 0.332958 |
| local-cli | training / process-cold / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.264500 / 0 / 26.264500 |
| local-mcp-stdio | training / process-cold / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.779167 / 0 / 25.779167 |
| local-python | training / process-cold / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.038042 / 0 / 0.038042 |
| subscription-baseline-unknown-cash | training / process-cold / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031292 / 0 / 0.031292 |
| usage-priced-reference | training / process-cold / 10 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.854292 / 1.883417 / 5.898583 / 0.067292 / 9.946625 |
| aeep-hybrid | training / process-cold / 11 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.549750 / 2.034917 / 5.176500 / 0 / 11.358959 |
| direct-http-mock | training / process-cold / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.382917 / 0 / 0.382917 |
| local-cli | training / process-cold / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.486500 / 0 / 25.486500 |
| local-mcp-stdio | training / process-cold / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.725792 / 0 / 25.725792 |
| local-python | training / process-cold / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.057541 / 0 / 0.057541 |
| subscription-baseline-unknown-cash | training / process-cold / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.029084 / 0 / 0.029084 |
| usage-priced-reference | training / process-cold / 11 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.884917 / 1.688083 / 7.169875 / 0.072458 / 11.080583 |
| aeep-hybrid | training / process-cold / 12 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.482750 / 2.196958 / 6.502708 / 0 / 12.867833 |
| direct-http-mock | training / process-cold / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.398042 / 0 / 0.398042 |
| local-cli | training / process-cold / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 35.960083 / 0 / 35.960083 |
| local-mcp-stdio | training / process-cold / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 38.546542 / 0 / 38.546542 |
| local-python | training / process-cold / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.045292 / 0 / 0.045292 |
| subscription-baseline-unknown-cash | training / process-cold / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.034750 / 0 / 0.034750 |
| usage-priced-reference | training / process-cold / 12 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.624375 / 1.935708 / 5.792458 / 0.069292 / 9.656625 |
| aeep-hybrid | training / process-cold / 13 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.353500 / 2.058417 / 5.324917 / 0 / 11.337250 |
| direct-http-mock | training / process-cold / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.438833 / 0 / 0.438833 |
| local-cli | training / process-cold / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 47.506291 / 0 / 47.506291 |
| local-mcp-stdio | training / process-cold / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 38.751875 / 0 / 38.751875 |
| local-python | training / process-cold / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.052750 / 0 / 0.052750 |
| subscription-baseline-unknown-cash | training / process-cold / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.037625 / 0 / 0.037625 |
| usage-priced-reference | training / process-cold / 13 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.842709 / 2.716208 / 5.864916 / 0.075417 / 10.774542 |
| aeep-hybrid | training / process-cold / 14 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.891749 / 1.802167 / 5.722250 / 0 / 12.162250 |
| direct-http-mock | training / process-cold / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.557584 / 0 / 0.557584 |
| local-cli | training / process-cold / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 31.857833 / 0 / 31.857833 |
| local-mcp-stdio | training / process-cold / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 31.132125 / 0 / 31.132125 |
| local-python | training / process-cold / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.033209 / 0 / 0.033209 |
| subscription-baseline-unknown-cash | training / process-cold / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.042042 / 0 / 0.042042 |
| usage-priced-reference | training / process-cold / 14 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.992626 / 1.787041 / 5.955500 / 0.076416 / 10.063959 |
| aeep-hybrid | training / process-cold / 15 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.672125 / 2.126042 / 6.105083 / 0 / 12.449500 |
| direct-http-mock | training / process-cold / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.483000 / 0 / 0.483000 |
| local-cli | training / process-cold / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 28.141041 / 0 / 28.141041 |
| local-mcp-stdio | training / process-cold / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 29.351125 / 0 / 29.351125 |
| local-python | training / process-cold / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.035542 / 0 / 0.035542 |
| subscription-baseline-unknown-cash | training / process-cold / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031959 / 0 / 0.031959 |
| usage-priced-reference | training / process-cold / 15 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.060251 / 2.180083 / 6.804542 / 0.080542 / 11.378000 |
| aeep-hybrid | training / process-cold / 16 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.032457 / 2.107959 / 5.626042 / 0 / 12.188041 |
| direct-http-mock | training / process-cold / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.422250 / 0 / 0.422250 |
| local-cli | training / process-cold / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.021250 / 0 / 26.021250 |
| local-mcp-stdio | training / process-cold / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 41.039875 / 0 / 41.039875 |
| local-python | training / process-cold / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.070083 / 0 / 0.070083 |
| subscription-baseline-unknown-cash | training / process-cold / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.055625 / 0 / 0.055625 |
| usage-priced-reference | training / process-cold / 16 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.753333 / 1.703709 / 6.910208 / 0.075750 / 10.673708 |
| aeep-hybrid | training / process-cold / 17 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.061083 / 1.901042 / 6.456125 / 0 / 12.923208 |
| direct-http-mock | training / process-cold / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.345667 / 0 / 0.345667 |
| local-cli | training / process-cold / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 31.662958 / 0 / 31.662958 |
| local-mcp-stdio | training / process-cold / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 31.280833 / 0 / 31.280833 |
| local-python | training / process-cold / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.040833 / 0 / 0.040833 |
| subscription-baseline-unknown-cash | training / process-cold / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031417 / 0 / 0.031417 |
| usage-priced-reference | training / process-cold / 17 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.881042 / 1.764708 / 6.391291 / 0.074084 / 10.340167 |
| aeep-hybrid | training / process-cold / 18 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.273625 / 1.873500 / 6.086708 / 0 / 12.746084 |
| direct-http-mock | training / process-cold / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.370958 / 0 / 0.370958 |
| local-cli | training / process-cold / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 34.351333 / 0 / 34.351333 |
| local-mcp-stdio | training / process-cold / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 34.269542 / 0 / 34.269542 |
| local-python | training / process-cold / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.037750 / 0 / 0.037750 |
| subscription-baseline-unknown-cash | training / process-cold / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031000 / 0 / 0.031000 |
| usage-priced-reference | training / process-cold / 18 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.938167 / 1.652375 / 5.922417 / 0.078042 / 9.823667 |
| aeep-hybrid | training / process-cold / 19 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.695709 / 1.935333 / 11.384000 / 0 / 17.528417 |
| direct-http-mock | training / process-cold / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.438125 / 0 / 0.438125 |
| local-cli | training / process-cold / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 34.077291 / 0 / 34.077291 |
| local-mcp-stdio | training / process-cold / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 32.076375 / 0 / 32.076375 |
| local-python | training / process-cold / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.060042 / 0 / 0.060042 |
| subscription-baseline-unknown-cash | training / process-cold / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033792 / 0 / 0.033792 |
| usage-priced-reference | training / process-cold / 19 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.874000 / 1.851250 / 6.001666 / 0.077542 / 10.149416 |
| aeep-hybrid | holdout / router-warm / 20 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.078750 / 1.659042 / 4.624459 / 0 / 10.684541 |
| direct-http-mock | holdout / router-warm / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.580708 / 0 / 0.580708 |
| local-cli | holdout / router-warm / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.019333 / 0 / 25.019333 |
| local-mcp-stdio | holdout / router-warm / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.617500 / 0 / 25.617500 |
| local-python | holdout / router-warm / 20 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.032625 / 0 / 0.032625 |
| subscription-baseline-unknown-cash | holdout / router-warm / 20 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030583 / 0 / 0.030583 |
| usage-priced-reference | holdout / router-warm / 20 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.846125 / 1.934500 / 8.272125 / 0.084167 / 14.381084 |
| aeep-hybrid | holdout / router-warm / 21 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.283750 / 1.633875 / 5.096417 / 0 / 11.358875 |
| direct-http-mock | holdout / router-warm / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.526500 / 0 / 0.526500 |
| local-cli | holdout / router-warm / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 35.842916 / 0 / 35.842916 |
| local-mcp-stdio | holdout / router-warm / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 61.429583 / 0 / 61.429583 |
| local-python | holdout / router-warm / 21 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031583 / 0 / 0.031583 |
| subscription-baseline-unknown-cash | holdout / router-warm / 21 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.049417 / 0 / 0.049417 |
| usage-priced-reference | holdout / router-warm / 21 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.702250 / 1.848125 / 7.936541 / 0.087167 / 13.828542 |
| aeep-hybrid | holdout / router-warm / 22 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.805250 / 1.639875 / 4.693750 / 0 / 11.540666 |
| direct-http-mock | holdout / router-warm / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 1.304750 / 0 / 1.304750 |
| local-cli | holdout / router-warm / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 60.093333 / 0 / 60.093333 |
| local-mcp-stdio | holdout / router-warm / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 55.825666 / 0 / 55.825666 |
| local-python | holdout / router-warm / 22 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.032250 / 0 / 0.032250 |
| subscription-baseline-unknown-cash | holdout / router-warm / 22 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032750 / 0 / 0.032750 |
| usage-priced-reference | holdout / router-warm / 22 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 10.009709 / 15.317125 / 11.222958 / 0.081875 / 37.327541 |
| aeep-hybrid | holdout / router-warm / 23 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.342625 / 1.559625 / 4.880292 / 0 / 11.052375 |
| direct-http-mock | holdout / router-warm / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.758750 / 0 / 0.758750 |
| local-cli | holdout / router-warm / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 31.525917 / 0 / 31.525917 |
| local-mcp-stdio | holdout / router-warm / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 33.306875 / 0 / 33.306875 |
| local-python | holdout / router-warm / 23 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030833 / 0 / 0.030833 |
| subscription-baseline-unknown-cash | holdout / router-warm / 23 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032958 / 0 / 0.032958 |
| usage-priced-reference | holdout / router-warm / 23 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.829875 / 2.138083 / 9.198542 / 0.073125 / 16.541875 |
| aeep-hybrid | holdout / router-warm / 24 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.876916 / 1.741625 / 5.727042 / 0 / 11.620083 |
| direct-http-mock | holdout / router-warm / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.580916 / 0 / 0.580916 |
| local-cli | holdout / router-warm / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 37.265542 / 0 / 37.265542 |
| local-mcp-stdio | holdout / router-warm / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 37.138500 / 0 / 37.138500 |
| local-python | holdout / router-warm / 24 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031167 / 0 / 0.031167 |
| subscription-baseline-unknown-cash | holdout / router-warm / 24 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.051916 / 0 / 0.051916 |
| usage-priced-reference | holdout / router-warm / 24 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.919291 / 1.872959 / 8.039625 / 0.072542 / 14.298125 |
| aeep-hybrid | holdout / router-warm / 25 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.999333 / 1.543292 / 5.357583 / 0 / 12.332417 |
| direct-http-mock | holdout / router-warm / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.686333 / 0 / 0.686333 |
| local-cli | holdout / router-warm / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 42.189000 / 0 / 42.189000 |
| local-mcp-stdio | holdout / router-warm / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 39.532167 / 0 / 39.532167 |
| local-python | holdout / router-warm / 25 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030834 / 0 / 0.030834 |
| subscription-baseline-unknown-cash | holdout / router-warm / 25 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032541 / 0 / 0.032541 |
| usage-priced-reference | holdout / router-warm / 25 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.667083 / 1.996250 / 8.530167 / 0.075375 / 15.510458 |
| aeep-hybrid | holdout / router-warm / 26 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.379500 / 1.764250 / 4.698000 / 0 / 11.230083 |
| direct-http-mock | holdout / router-warm / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.521542 / 0 / 0.521542 |
| local-cli | holdout / router-warm / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 37.780666 / 0 / 37.780666 |
| local-mcp-stdio | holdout / router-warm / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 38.944166 / 0 / 38.944166 |
| local-python | holdout / router-warm / 26 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030750 / 0 / 0.030750 |
| subscription-baseline-unknown-cash | holdout / router-warm / 26 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031917 / 0 / 0.031917 |
| usage-priced-reference | holdout / router-warm / 26 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 5.274459 / 2.732208 / 10.674792 / 0.071333 / 19.063959 |
| aeep-hybrid | holdout / router-warm / 27 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.273251 / 1.498041 / 4.848625 / 0 / 10.950667 |
| direct-http-mock | holdout / router-warm / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.598042 / 0 / 0.598042 |
| local-cli | holdout / router-warm / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 35.466291 / 0 / 35.466291 |
| local-mcp-stdio | holdout / router-warm / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 31.035083 / 0 / 31.035083 |
| local-python | holdout / router-warm / 27 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030916 / 0 / 0.030916 |
| subscription-baseline-unknown-cash | holdout / router-warm / 27 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033250 / 0 / 0.033250 |
| usage-priced-reference | holdout / router-warm / 27 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.051583 / 2.042625 / 7.677209 / 0.068291 / 14.089083 |
| aeep-hybrid | holdout / router-warm / 28 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.521958 / 1.910167 / 5.133250 / 0 / 11.904833 |
| direct-http-mock | holdout / router-warm / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.498292 / 0 / 0.498292 |
| local-cli | holdout / router-warm / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 31.804333 / 0 / 31.804333 |
| local-mcp-stdio | holdout / router-warm / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.771500 / 0 / 25.771500 |
| local-python | holdout / router-warm / 28 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030750 / 0 / 0.030750 |
| subscription-baseline-unknown-cash | holdout / router-warm / 28 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031209 / 0 / 0.031209 |
| usage-priced-reference | holdout / router-warm / 28 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 4.152376 / 1.946708 / 8.054208 / 0.072250 / 14.475875 |
| aeep-hybrid | holdout / router-warm / 29 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.485376 / 1.883958 / 5.373084 / 0 / 12.075209 |
| direct-http-mock | holdout / router-warm / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.501000 / 0 / 0.501000 |
| local-cli | holdout / router-warm / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 39.555125 / 0 / 39.555125 |
| local-mcp-stdio | holdout / router-warm / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 28.010833 / 0 / 28.010833 |
| local-python | holdout / router-warm / 29 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031333 / 0 / 0.031333 |
| subscription-baseline-unknown-cash | holdout / router-warm / 29 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.061125 / 0 / 0.061125 |
| usage-priced-reference | holdout / router-warm / 29 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.820083 / 2.073542 / 10.241833 / 0.077750 / 16.502417 |
| aeep-hybrid | qualification / router-warm / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.354459 / 1.785666 / 5.933457 / 0.057709 / 10.397791 |
| direct-http-mock | qualification / router-warm / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.479208 / 0 / 0.479208 |
| local-cli | qualification / router-warm / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 24.499542 / 0 / 24.499542 |
| local-mcp-stdio | qualification / router-warm / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 24.661333 / 0 / 24.661333 |
| local-python | qualification / router-warm / 0 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.040833 / 0 / 0.040833 |
| subscription-baseline-unknown-cash | qualification / router-warm / 0 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.036291 / 0 / 0.036291 |
| usage-priced-reference | qualification / router-warm / 0 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.876208 / 1.953500 / 6.912834 / 0.076625 / 11.092333 |
| aeep-hybrid | qualification / router-warm / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.204250 / 1.777750 / 6.746583 / 0.069000 / 11.094958 |
| direct-http-mock | qualification / router-warm / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.442416 / 0 / 0.442416 |
| local-cli | qualification / router-warm / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.855250 / 0 / 25.855250 |
| local-mcp-stdio | qualification / router-warm / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.320000 / 0 / 25.320000 |
| local-python | qualification / router-warm / 1 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.028792 / 0 / 0.028792 |
| subscription-baseline-unknown-cash | qualification / router-warm / 1 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031916 / 0 / 0.031916 |
| usage-priced-reference | qualification / router-warm / 1 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.551166 / 1.891167 / 5.934833 / 0.070667 / 9.660667 |
| aeep-hybrid | qualification / router-warm / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.866292 / 1.886583 / 7.035083 / 0.069584 / 12.147875 |
| direct-http-mock | qualification / router-warm / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.494000 / 0 / 0.494000 |
| local-cli | qualification / router-warm / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.587875 / 0 / 26.587875 |
| local-mcp-stdio | qualification / router-warm / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.447125 / 0 / 25.447125 |
| local-python | qualification / router-warm / 2 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.028958 / 0 / 0.028958 |
| subscription-baseline-unknown-cash | qualification / router-warm / 2 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031625 / 0 / 0.031625 |
| usage-priced-reference | qualification / router-warm / 2 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.682958 / 1.970667 / 7.256209 / 0.081333 / 11.303666 |
| aeep-hybrid | qualification / router-warm / 3 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.429750 / 1.901500 / 3.566542 / 0 / 8.261500 |
| direct-http-mock | qualification / router-warm / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.455041 / 0 / 0.455041 |
| local-cli | qualification / router-warm / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.541084 / 0 / 25.541084 |
| local-mcp-stdio | qualification / router-warm / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.344291 / 0 / 26.344291 |
| local-python | qualification / router-warm / 3 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030291 / 0 / 0.030291 |
| subscription-baseline-unknown-cash | qualification / router-warm / 3 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032208 / 0 / 0.032208 |
| usage-priced-reference | qualification / router-warm / 3 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.743166 / 1.909334 / 6.560708 / 0.077250 / 10.523917 |
| aeep-hybrid | qualification / router-warm / 4 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.928917 / 1.746667 / 3.265584 / 0 / 8.180167 |
| direct-http-mock | qualification / router-warm / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.487959 / 0 / 0.487959 |
| local-cli | qualification / router-warm / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 24.926541 / 0 / 24.926541 |
| local-mcp-stdio | qualification / router-warm / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.221417 / 0 / 26.221417 |
| local-python | qualification / router-warm / 4 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031042 / 0 / 0.031042 |
| subscription-baseline-unknown-cash | qualification / router-warm / 4 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.049708 / 0 / 0.049708 |
| usage-priced-reference | qualification / router-warm / 4 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.017750 / 2.113458 / 7.309042 / 0.075667 / 11.808417 |
| aeep-hybrid | qualification / router-warm / 5 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.663416 / 1.666792 / 3.345000 / 0 / 7.914375 |
| direct-http-mock | qualification / router-warm / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.568458 / 0 / 0.568458 |
| local-cli | qualification / router-warm / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.258750 / 0 / 26.258750 |
| local-mcp-stdio | qualification / router-warm / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 27.424167 / 0 / 27.424167 |
| local-python | qualification / router-warm / 5 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030917 / 0 / 0.030917 |
| subscription-baseline-unknown-cash | qualification / router-warm / 5 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.029333 / 0 / 0.029333 |
| usage-priced-reference | qualification / router-warm / 5 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.247584 / 1.906416 / 7.052624 / 0.073209 / 11.533250 |
| aeep-hybrid | qualification / router-warm / 6 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.502125 / 1.673333 / 3.607458 / 0 / 8.105958 |
| direct-http-mock | qualification / router-warm / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.552500 / 0 / 0.552500 |
| local-cli | qualification / router-warm / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.932000 / 0 / 25.932000 |
| local-mcp-stdio | qualification / router-warm / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.317333 / 0 / 25.317333 |
| local-python | qualification / router-warm / 6 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.035833 / 0 / 0.035833 |
| subscription-baseline-unknown-cash | qualification / router-warm / 6 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.038667 / 0 / 0.038667 |
| usage-priced-reference | qualification / router-warm / 6 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 1.857291 / 1.825709 / 5.968542 / 0.067333 / 9.934417 |
| aeep-hybrid | qualification / router-warm / 7 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.993917 / 1.568625 / 3.654834 / 0 / 8.493333 |
| direct-http-mock | qualification / router-warm / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.536042 / 0 / 0.536042 |
| local-cli | qualification / router-warm / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.375792 / 0 / 25.375792 |
| local-mcp-stdio | qualification / router-warm / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.780500 / 0 / 25.780500 |
| local-python | qualification / router-warm / 7 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.038291 / 0 / 0.038291 |
| subscription-baseline-unknown-cash | qualification / router-warm / 7 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031792 / 0 / 0.031792 |
| usage-priced-reference | qualification / router-warm / 7 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.002000 / 2.039250 / 7.185124 / 0.072209 / 11.595875 |
| aeep-hybrid | qualification / router-warm / 8 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.107000 / 1.850541 / 4.055083 / 0 / 9.351000 |
| direct-http-mock | qualification / router-warm / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.658584 / 0 / 0.658584 |
| local-cli | qualification / router-warm / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.540084 / 0 / 26.540084 |
| local-mcp-stdio | qualification / router-warm / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.407000 / 0 / 25.407000 |
| local-python | qualification / router-warm / 8 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030459 / 0 / 0.030459 |
| subscription-baseline-unknown-cash | qualification / router-warm / 8 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.049042 / 0 / 0.049042 |
| usage-priced-reference | qualification / router-warm / 8 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.204917 / 1.822208 / 6.809000 / 0.072125 / 11.112583 |
| aeep-hybrid | qualification / router-warm / 9 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 2.680250 / 1.764875 / 4.056166 / 0 / 8.802875 |
| direct-http-mock | qualification / router-warm / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.534375 / 0 / 0.534375 |
| local-cli | qualification / router-warm / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.257208 / 0 / 25.257208 |
| local-mcp-stdio | qualification / router-warm / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.759000 / 0 / 26.759000 |
| local-python | qualification / router-warm / 9 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031417 / 0 / 0.031417 |
| subscription-baseline-unknown-cash | qualification / router-warm / 9 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030791 / 0 / 0.030791 |
| usage-priced-reference | qualification / router-warm / 9 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.211250 / 1.681000 / 6.262749 / 0.069459 / 10.432250 |
| aeep-hybrid | training / router-warm / 10 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.020709 / 1.734708 / 4.260291 / 0 / 9.334334 |
| direct-http-mock | training / router-warm / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.502167 / 0 / 0.502167 |
| local-cli | training / router-warm / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 26.001709 / 0 / 26.001709 |
| local-mcp-stdio | training / router-warm / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.168625 / 0 / 26.168625 |
| local-python | training / router-warm / 10 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029750 / 0 / 0.029750 |
| subscription-baseline-unknown-cash | training / router-warm / 10 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.036250 / 0 / 0.036250 |
| usage-priced-reference | training / router-warm / 10 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.266334 / 1.991000 / 6.828167 / 0.075250 / 11.453125 |
| aeep-hybrid | training / router-warm / 11 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.251876 / 1.783416 / 3.904750 / 0 / 9.228625 |
| direct-http-mock | training / router-warm / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.489125 / 0 / 0.489125 |
| local-cli | training / router-warm / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.928833 / 0 / 27.928833 |
| local-mcp-stdio | training / router-warm / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.358458 / 0 / 25.358458 |
| local-python | training / router-warm / 11 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.029833 / 0 / 0.029833 |
| subscription-baseline-unknown-cash | training / router-warm / 11 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031084 / 0 / 0.031084 |
| usage-priced-reference | training / router-warm / 11 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.520416 / 2.174084 / 8.882416 / 0.076167 / 13.902458 |
| aeep-hybrid | training / router-warm / 12 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.227874 / 1.658417 / 4.109375 / 0 / 9.333792 |
| direct-http-mock | training / router-warm / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.477834 / 0 / 0.477834 |
| local-cli | training / router-warm / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.172083 / 0 / 27.172083 |
| local-mcp-stdio | training / router-warm / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.336792 / 0 / 25.336792 |
| local-python | training / router-warm / 12 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.032500 / 0 / 0.032500 |
| subscription-baseline-unknown-cash | training / router-warm / 12 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030750 / 0 / 0.030750 |
| usage-priced-reference | training / router-warm / 12 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.242832 / 1.524334 / 6.802250 / 0.067792 / 10.861000 |
| aeep-hybrid | training / router-warm / 13 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.233958 / 1.492875 / 4.620541 / 0 / 9.637833 |
| direct-http-mock | training / router-warm / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.501416 / 0 / 0.501416 |
| local-cli | training / router-warm / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.832792 / 0 / 25.832792 |
| local-mcp-stdio | training / router-warm / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.207458 / 0 / 25.207458 |
| local-python | training / router-warm / 13 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031417 / 0 / 0.031417 |
| subscription-baseline-unknown-cash | training / router-warm / 13 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.033792 / 0 / 0.033792 |
| usage-priced-reference | training / router-warm / 13 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.495792 / 1.908375 / 7.017917 / 0.072375 / 11.683833 |
| aeep-hybrid | training / router-warm / 14 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.607208 / 1.759125 / 4.373417 / 0 / 10.051667 |
| direct-http-mock | training / router-warm / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.494375 / 0 / 0.494375 |
| local-cli | training / router-warm / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.981208 / 0 / 25.981208 |
| local-mcp-stdio | training / router-warm / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.363958 / 0 / 25.363958 |
| local-python | training / router-warm / 14 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.032625 / 0 / 0.032625 |
| subscription-baseline-unknown-cash | training / router-warm / 14 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031541 / 0 / 0.031541 |
| usage-priced-reference | training / router-warm / 14 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.470334 / 2.001166 / 8.190791 / 0.081125 / 13.029875 |
| aeep-hybrid | training / router-warm / 15 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.473958 / 1.576375 / 4.031833 / 0 / 9.319209 |
| direct-http-mock | training / router-warm / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.496542 / 0 / 0.496542 |
| local-cli | training / router-warm / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.740041 / 0 / 27.740041 |
| local-mcp-stdio | training / router-warm / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.216584 / 0 / 25.216584 |
| local-python | training / router-warm / 15 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030833 / 0 / 0.030833 |
| subscription-baseline-unknown-cash | training / router-warm / 15 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.030417 / 0 / 0.030417 |
| usage-priced-reference | training / router-warm / 15 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.601501 / 1.886666 / 7.276333 / 0.068000 / 12.085792 |
| aeep-hybrid | training / router-warm / 16 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.249834 / 1.689708 / 3.633000 / 0 / 8.814917 |
| direct-http-mock | training / router-warm / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.556459 / 0 / 0.556459 |
| local-cli | training / router-warm / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.364708 / 0 / 25.364708 |
| local-mcp-stdio | training / router-warm / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.494000 / 0 / 26.494000 |
| local-python | training / router-warm / 16 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.033250 / 0 / 0.033250 |
| subscription-baseline-unknown-cash | training / router-warm / 16 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031500 / 0 / 0.031500 |
| usage-priced-reference | training / router-warm / 16 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.340833 / 1.905500 / 7.659292 / 0.069500 / 12.214041 |
| aeep-hybrid | training / router-warm / 17 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.322583 / 1.721334 / 4.533083 / 0 / 9.884041 |
| direct-http-mock | training / router-warm / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.526000 / 0 / 0.526000 |
| local-cli | training / router-warm / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 27.219334 / 0 / 27.219334 |
| local-mcp-stdio | training / router-warm / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.924583 / 0 / 25.924583 |
| local-python | training / router-warm / 17 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.030166 / 0 / 0.030166 |
| subscription-baseline-unknown-cash | training / router-warm / 17 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.032375 / 0 / 0.032375 |
| usage-priced-reference | training / router-warm / 17 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.654542 / 1.863083 / 7.835374 / 0.068959 / 12.659833 |
| aeep-hybrid | training / router-warm / 18 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 3.853959 / 1.769583 / 4.281750 / 0 / 10.186500 |
| direct-http-mock | training / router-warm / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.513458 / 0 / 0.513458 |
| local-cli | training / router-warm / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.717250 / 0 / 25.717250 |
| local-mcp-stdio | training / router-warm / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 25.656292 / 0 / 25.656292 |
| local-python | training / router-warm / 18 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.031500 / 0 / 0.031500 |
| subscription-baseline-unknown-cash | training / router-warm / 18 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.031625 / 0 / 0.031625 |
| usage-priced-reference | training / router-warm / 18 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.691625 / 1.852500 / 7.520083 / 0.072709 / 12.321375 |
| aeep-hybrid | training / router-warm / 19 | yes | USD 0.0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 4.081293 / 1.672916 / 4.744458 / 0 / 10.797958 |
| direct-http-mock | training / router-warm / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.421458 / 0 / 0.421458 |
| local-cli | training / router-warm / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 25.288417 / 0 / 25.288417 |
| local-mcp-stdio | training / router-warm / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 26.200084 / 0 / 26.200084 |
| local-python | training / router-warm / 19 | yes | USD 0 | USD 0 | unknown | unknown | unknown | OPERATOR_ATTESTED | 0 / 0 / 0.036792 / 0 / 0.036792 |
| subscription-baseline-unknown-cash | training / router-warm / 19 | yes | unknown | unknown | unknown | unknown | unknown | UNKNOWN | 0 / 0 / 0.038708 / 0 / 0.038708 |
| usage-priced-reference | training / router-warm / 19 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 2.664333 / 1.897417 / 7.724791 / 0.073000 / 12.616500 |

## Prepared hybrid workflow proof

These multi-step DAG measurements are not included in the single-action route oracle.

| Workflow | Split / condition / repetition | Steps prepared | Quotes | Settlements | Dependency bytes | Valid | Expected | Maximum | Reserved | Captured | Released | Evidence | Prep / quote / execute / settle / total ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| prepared-hybrid-workflow-29 | holdout / process-cold / 29 | 2/2 | 1 | 1 | 14347 | yes | USD 0.0040 | USD 0.0050 | USD 0.0050 | USD 0.0038 | USD 0.0012 | PAYMENT_SETTLEMENT | 3.521792 / 1.635083 / 0 / 0.083959 / 19.247250 |

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
- FAIL — deterministic-domain total-time target: AEEP median 11.2256875 ms, fastest measured baseline 0.032354 ms, reduction -34596.444025%.
- NOT EVALUATED — two-domain 20% model-token target: this local campaign covers one domain and 240 trial(s) with complete model-usage measurement; synthetic subscription usage is excluded from claims.
