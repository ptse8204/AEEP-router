"""Pinned MCP task metadata with real state outputs; no database access or execution."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .benchmarks import TaskAsset
from .models import ContractModel, Digest, Identifier, SourcePin

SQLName = Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")]


class TableOutput(ContractModel):
    """An opaque reviewed backend alias and table identity, never SQL or credentials."""

    kind: Literal["postgresql_table"] = "postgresql_table"
    backend_id: Identifier
    schema_name: SQLName = "public"
    table_name: SQLName


class MCPStateTask(ContractModel):
    task_id: Identifier
    domain: Literal["mcp"] = "mcp"
    difficulty: Literal["easy", "medium", "hard", "unknown"]
    assets: tuple[TaskAsset, ...] = Field(min_length=4, max_length=4096)
    instruction_json_key: Identifier | None = None
    oracle_layout: Literal["separate_asset", "embedded_in_verifier"]
    state_outputs: tuple[TableOutput, ...] = Field(min_length=1, max_length=128)
    upstream_score: Literal["binary", "native_reward"]
    rights_review_ref: Digest | None = None
    adaptations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def separated_state_assets(self) -> MCPStateTask:
        names = [asset.path.casefold() for asset in self.assets]
        roles = {asset.role for asset in self.assets}
        if (
            len(names) != len(set(names))
            or not {"instruction", "environment", "verifier", "license"} <= roles
            or sum(a.role == "instruction" for a in self.assets) != 1
            or sum(a.bytes for a in self.assets) > 2 * 1024**3
        ):
            raise ValueError(
                "state tasks require unique original instructions, protected environment/verifier and notices"
            )
        if (self.oracle_layout == "separate_asset") != ("oracle" in roles):
            raise ValueError("state-task oracle location must match its protected assets")
        selectors = [(o.backend_id, o.schema_name, o.table_name) for o in self.state_outputs]
        if len(selectors) != len(set(selectors)):
            raise ValueError("state-output identities must be distinct")
        return self


class MCPStatePack(ContractModel):
    schema_version: Literal["aeep.toolkit.mcp-state-pack.v1"] = "aeep.toolkit.mcp-state-pack.v1"
    pack_id: Literal["mcpmark", "mcp-universe"]
    source: SourcePin
    tasks: tuple[MCPStateTask, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def pinned_pack(self) -> MCPStatePack:
        from .stack_readiness import source_revisions

        if self.source.revision != source_revisions("0" * 64)[self.pack_id]:
            raise ValueError("state pack differs from the selected reviewed pin")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate state task identities")
        return self

    def task(self, task_id: str) -> MCPStateTask:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise ValueError("unknown benchmark task")
