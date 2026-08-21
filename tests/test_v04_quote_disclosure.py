from __future__ import annotations

import pytest
from pydantic import ValidationError

from aeep.economic.disclosure import (
    QuoteDisclosureError,
    QuoteDisclosureField,
    QuoteDisclosurePolicy,
    disclose_quote_features,
)
from aeep.models import ActionFeatures


def features() -> ActionFeatures:
    return ActionFeatures(
        input_bytes=14_336,
        input_items=1,
        text_characters=14_200,
        max_depth=2,
        size_bucket="2^14",
    )


def test_only_operator_declared_bounded_features_are_disclosed() -> None:
    policy = QuoteDisclosurePolicy(
        fields=(
            QuoteDisclosureField(source="action_features.input_bytes", name="input_bytes"),
            QuoteDisclosureField(
                source="action_features.text_characters",
                name="text_characters",
            ),
            QuoteDisclosureField(
                source="action_input.page_count",
                name="page_count",
                type="integer",
                maximum=1000,
            ),
            QuoteDisclosureField(source="action_features.size_bucket", name="input_bucket"),
            QuoteDisclosureField(
                source="action_input.category",
                name="category",
                type="enum",
                allowed_values=("resume", "invoice"),
            ),
        )
    )
    action_input = {
        "page_count": 14,
        "category": "resume",
        "resume": "private resume text",
        "access_token": "secret",
        "email": "person@example.test",
        "url": "https://example.test/?token=secret",
    }

    disclosed = disclose_quote_features(
        policy,
        action_input=action_input,
        action_features=features(),
    )

    assert disclosed == {
        "category": "resume",
        "input_bucket": "2^14",
        "input_bytes": 14_336,
        "page_count": 14,
        "text_characters": 14_200,
    }
    assert "private resume text" not in str(disclosed)
    assert "secret" not in str(disclosed)


@pytest.mark.parametrize(
    "source",
    [
        "action_input.resume",
        "action_input.access_token",
        "action_input.email",
        "action_input.profile_url",
        "action_input.user_name",
        "action_input.document.content",
        "action_input..page_count",
    ],
)
def test_sensitive_free_form_and_nested_sources_are_denied(source: str) -> None:
    with pytest.raises(ValidationError):
        QuoteDisclosureField(source=source, name="safe_count", type="integer")


def test_arbitrary_strings_are_denied_without_an_enum_allowlist() -> None:
    with pytest.raises(ValidationError, match="operator allowlist"):
        QuoteDisclosureField(
            source="action_input.category",
            name="category",
            type="enum",
        )

    policy = QuoteDisclosurePolicy(
        fields=(
            QuoteDisclosureField(
                source="action_input.category",
                name="category",
                type="enum",
                allowed_values=("small", "large"),
            ),
        )
    )
    with pytest.raises(QuoteDisclosureError, match=r"whitespace|not allowlisted"):
        disclose_quote_features(
            policy,
            action_input={"category": "arbitrary free-form text"},
            action_features=features(),
        )


def test_disclosure_enforces_numeric_and_total_size_bounds() -> None:
    count = QuoteDisclosureField(
        source="action_input.page_count",
        name="pages",
        type="integer",
        maximum=20,
    )
    with pytest.raises(QuoteDisclosureError, match="outside its bounds"):
        disclose_quote_features(
            QuoteDisclosurePolicy(fields=(count,)),
            action_input={"page_count": 21},
            action_features=features(),
        )

    with pytest.raises(QuoteDisclosureError, match="encoded size"):
        disclose_quote_features(
            QuoteDisclosurePolicy(fields=(count,), maximum_encoded_bytes=2),
            action_input={"page_count": 1},
            action_features=features(),
        )


def test_optional_missing_field_is_omitted_and_required_field_fails() -> None:
    optional = QuoteDisclosureField(
        source="action_input.page_count",
        name="pages",
        type="integer",
    )
    assert disclose_quote_features(
        QuoteDisclosurePolicy(fields=(optional,)),
        action_input={},
        action_features=features(),
    ) == {}

    required = optional.model_copy(update={"required": True})
    with pytest.raises(QuoteDisclosureError, match="unavailable"):
        disclose_quote_features(
            QuoteDisclosurePolicy(fields=(required,)),
            action_input={},
            action_features=features(),
        )
