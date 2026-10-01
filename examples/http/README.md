# HTTP executor example

Start the example server in one terminal:

```bash
python examples/http/server.py
```

Run the action in another terminal:

```bash
aeep run text.stats -i '{"text":"one two"}' -m examples/http/aeep.yaml
```

AEEP records the API's trusted cost header as observed monetary usage.
