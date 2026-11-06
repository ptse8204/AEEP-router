#!/bin/bash
set -euo pipefail
umask 077
/usr/bin/python3 -I -B /aeep/boundary.py
cp -- /inputs/invoices.pdf /inputs/vendors.xlsx /inputs/purchase_orders.csv /root/
cd /root
/bin/bash /aeep/solve.sh >&2
test -f /root/fraud_report.json
test "$(stat -c %s -- /root/fraud_report.json)" -le 65536
exec cat -- /root/fraud_report.json
