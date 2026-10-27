"""Tighten two operator edit scopes without altering source or test identities."""
from pathlib import Path

HERE=Path(__file__).resolve().parent
s=(HERE/'prepare-cases.py').read_text()
s=s.replace("ROOT / '.aeep/repository-large-cases-20261027'","ROOT / '.aeep/repository-large-networkx-cases-20261027'")
s=s.replace("if record['repository'] != 'agronholm/anyio'","if record['repository'] == 'networkx/networkx'")
s=s.replace("prefixes = {n.split('/')[0] + '/' for n in source_names if '/' in n}","prefixes = {str(Path(n).parent) + '/' for n in source_names if '/' in n}")
s=s.replace("(HERE / 'prepared-cases.json').write_text","(HERE / 'networkx-scoped-cases.json').write_text")
s=s.replace("'omitted_non_source_reference_changes': omitted,","'omitted_non_source_reference_changes': omitted, 'edit_scope_adaptation': 'Only existing Python files under published changed-source parent directories; avoids a package-wide editable list over256. Full source/tests and every assertion/identity remain unchanged.',")
(HERE/'prepare-networkx-cases.py').write_text(s)
