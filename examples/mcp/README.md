# MCP executor example

This example launches a real newline-delimited stdio MCP server and discovers its schema. It calls `text_stats`, measures the schema and result context overhead, validates the output, and stores a receipt.

```bash
pip install -e .
aeep doctor -m examples/mcp/aeep.yaml
aeep run text.stats -i '{"text":"one two three"}' -m examples/mcp/aeep.yaml
```
