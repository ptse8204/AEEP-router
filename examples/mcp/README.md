# MCP executor example

Use an MCP tool through AEEP and inspect its verified result and context
overhead. This example runs a local text-statistics server, giving developers
a small transport integration to try before connecting a larger service.

Install AEEP and run from the repository root with the environment available
to child processes. No remote server, model account or credential is needed.

[Documentation index](../../docs/README.md).

This example launches a real newline-delimited stdio MCP server and discovers its schema. It calls `text_stats`, measures the schema and result context overhead, validates the output, and stores a receipt.

```bash
pip install -e .
aeep doctor -m examples/mcp/aeep.yaml
aeep run text.stats -i '{"text":"one two three"}' -m examples/mcp/aeep.yaml
```

## Expected result and limits

For `one two three`, expect 13 characters, 3 words and 1 line, plus a verified
receipt. Successful stdio transport does not qualify an unrelated MCP server.
See [integration guidance](../../docs/INTEGRATIONS.md) for a host connection.
