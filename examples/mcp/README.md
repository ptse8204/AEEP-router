# MCP executor example

This example launches a real newline-delimited stdio MCP server, discovers its schema, calls `text_stats`, measures schema/result context overhead, validates output, and stores a receipt.

```bash
pip install -e .
aeep doctor -m examples/mcp/aeep.yaml
aeep run text.stats -i '{"text":"one two three"}' -m examples/mcp/aeep.yaml
```
