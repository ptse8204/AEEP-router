"""Verify the pinned Postgres MCP tool contract and classify its textual errors."""
import hashlib
import json


def schema_digest(result):
    tools = [tool for tool in result['tools'] if tool['name']=='execute_sql']
    assert len(tools)==1
    schema = tools[0]['inputSchema']
    assert schema.get('type')=='object' and schema.get('required',[])==[]
    properties = schema['properties']
    assert set(properties)=={'sql'}
    assert properties['sql'].get('type')=='string' and properties['sql'].get('default')=='all'
    return hashlib.sha256(json.dumps(schema,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def has_tool_error(result):
    content = result.get('content')
    assert isinstance(content,list) and content
    assert all(isinstance(item,dict) and item.get('type')=='text' and isinstance(item.get('text'),str)
               for item in content)
    return bool(result.get('isError')) or any(item['text'].lstrip().startswith('Error:') for item in content)
