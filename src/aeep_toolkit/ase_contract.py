"""Static source identities from the selected ASE0.7.0 source/wheel audit."""

from __future__ import annotations

import hashlib
from importlib.metadata import distribution
from pathlib import Path

ASE_REVISION = "59de161f657b82bfaf8f6abe83dfff38552deb21"
ASE_ARTIFACT = "5e29aff9fc354475c7e3e652659475e89cbb438603ee55d0392f0c845dbcf07f"
ASE_SOURCE_FILES = {
    "agent_skill_eval/__init__.py": "cea726bf89140d96cd24fe459bf58988801e3c1cbbc0da57cad577821ddd44fe",
    "agent_skill_eval/__main__.py": "c9ddeaab5083783ab6f90721dd6ef063c4ee78c5cfdd989ceb22168c7e6ca2f4",
    "agent_skill_eval/cli.py": "7877e62d8a3fd5aa821c1359e721a2bbf8fff5429bb856995bc7ee394a4a3c0f",
    "agent_skill_eval/fixtures.py": "5adc40b3f9f91d7d4d7599ee0f890a59058b0881505c46a8a2f0d7145435234c",
    "agent_skill_eval/git_state.py": "d06f4cda0f859fa038f0da9799aabb54cc371d83995a939cf725eb79cc3f8f32",
    "agent_skill_eval/graders/__init__.py": "28d30ab74122cc45ea9d4b98191fb59698e8b4b71d41e694e5702de8bb122c7a",
    "agent_skill_eval/harnesses/__init__.py": "348b9cc731fb6470a6dfe38000c090bb743094cdc183156e27ba2b37a8a11bb0",
    "agent_skill_eval/hooks.py": "6a47adab2c6037dfcc15b2a831085c03b68f73e9d31cfae7c22bf796e0eefe39",
    "agent_skill_eval/models.py": "210f95b99f035092564d5503da7e228b4a1d13c9c4f96f5744ce22df8b6b443c",
    "agent_skill_eval/openrouter.py": "eec81fb1714cae82d276626884184e23ca718098adef3ad4cbf009a3b84373c2",
    "agent_skill_eval/progress.py": "369f0c0e00fd38e19ef1327d022861ce543d10632ea859843cabbbe8b77fc807",
    "agent_skill_eval/runner.py": "a37df1cddbfcf4d0437835c2f582ee539724758d9d257f86ac47e8c39484ca27",
    "agent_skill_eval/skills.py": "977cb376bfdd2954361abf5fa39abb657aa2b2613443cac122da35a36fdf9c64",
    "agent_skill_eval/summary.py": "035ef3946a8f92d3c0822caaa7f407745e7ec5299af8cd8290605cebe7f140ff",
    "agent_skill_eval/validation.py": "ddf201c8564b8671693a054033f8ead3ebced257b817a7f28d9201605720c874",
    "agent_skill_eval/workspace.py": "a2969a72e74860d6c0117e8506819cd4e79c5061ee5bc191501a025bf47224e3",
}


def verify_runtime_source() -> None:
    from .cli import read_bytes

    installed = distribution("agent-skill-eval")
    if installed.version != "0.7.0":
        raise ValueError("unreviewed agent-skill-eval version")
    for name, expected in ASE_SOURCE_FILES.items():
        path = Path(str(installed.locate_file(name)))
        if hashlib.sha256(read_bytes(path)).hexdigest() != expected:
            raise ValueError("agent-skill-eval source changed")
