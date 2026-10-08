# HTTP executor example

Put an HTTP service behind the same routing and receipt interface as a local
tool. This example runs a text-statistics service on loopback so you can inspect
the request's result and recorded usage.

Install AEEP, run from the repository root and leave port 8787 available. Keep
the server terminal open while using the client; stop it with Ctrl-C afterward.

[Documentation index](../../docs/README.md).

Start the example server in one terminal:

```bash
python examples/http/server.py
```

Run the action in another terminal:

```bash
aeep run text.stats -i '{"text":"one two"}' -m examples/http/aeep.yaml
```

The example server returns a fixed `X-AEEP-Cost-USD` header for accounting tests.

## Expected result and limits

For `one two`, expect 7 characters, 2 words and 1 line in the result, plus
a receipt for the HTTP executor. The cost header is synthetic provider-reported
resource usage; it does not establish an actual payment or general savings.
