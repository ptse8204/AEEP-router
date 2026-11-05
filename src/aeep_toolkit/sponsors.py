"""Resolve a GitHub repository account from its reviewed funding declaration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from .models import ContractModel, DeveloperIdentity, SourcePin
from .workflow import WorkflowFile, _read

ACCOUNT = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
REPOSITORY = re.compile(rf"https://github\.com/({ACCOUNT})/[A-Za-z0-9_.-]+")


class SponsorReview(ContractModel):
    schema_version: Literal["aeep.toolkit.sponsor-review.v1"]
    source: SourcePin
    funding: WorkflowFile


def resolve(source: SourcePin, review: WorkflowFile, root: Path) -> DeveloperIdentity:
    review_path, raw = _read(review, root)
    details = SponsorReview.model_validate_json(raw)
    repository = REPOSITORY.fullmatch(source.repository)
    if details.source != source or repository is None:
        raise ValueError("Sponsors requires an exact reviewed GitHub candidate source")
    account = repository[1]
    _, funding = _read(details.funding, review_path.parent)
    if len(funding) > 16 * 1024:
        raise ValueError("funding declaration exceeds the metadata limit")
    try:
        document = yaml.compose(funding, Loader=yaml.BaseLoader)
    except (yaml.YAMLError, RecursionError) as error:
        raise ValueError("invalid funding declaration") from error
    if not isinstance(document, MappingNode):
        raise ValueError("funding declaration must be a mapping")
    declarations = [
        value for key, value in document.value
        if isinstance(key, ScalarNode) and key.value == "github"
    ]
    if len(declarations) != 1:
        raise ValueError("funding declaration requires one github entry")
    declaration = declarations[0]
    accounts = declaration.value if isinstance(declaration, SequenceNode) else [declaration]
    if not 1 <= len(accounts) <= 4 or any(
        not isinstance(node, ScalarNode) or re.fullmatch(ACCOUNT, node.value) is None
        for node in accounts
    ):
        raise ValueError("invalid GitHub Sponsors accounts")
    if account.casefold() not in {node.value.casefold() for node in accounts}:
        raise ValueError("funding declaration does not include the source repository account")
    return DeveloperIdentity(
        source=source, identity=account, assertion_ref=review.sha256,
        support_url=f"https://github.com/sponsors/{account}", support_kind="donation",
    )
