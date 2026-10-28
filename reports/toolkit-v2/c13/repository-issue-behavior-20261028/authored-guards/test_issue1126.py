"""Authored from issue1126: same-named nested enums must remain distinct.

This exercises the existing promotion/lookup flow, not a new helper signature or
the exact spelling of the published fix. The two enum objects may be renamed by
a valid implementation; each parent's attribute must still resolve to its own.
"""
from xsdata.codegen.container import ClassContainer
from xsdata.codegen.handlers import ProcessAttributeTypes, UnnestInnerClasses
from xsdata.models.config import GeneratorConfig
from xsdata.models.enums import Tag
from xsdata.utils.testing import AttrFactory, ClassFactory


def test_distinct_nested_enums_after_promotion_and_lookup():
    container = ClassContainer(config=GeneratorConfig())
    parents = []
    expected_values = [{"Rejected", "Completed"}, {"Pending", "Approved"}]
    for values in (("Rejected", "Completed"), ("Pending", "Approved")):
        parent = ClassFactory.create(qname="{urn:aeep:issue1126}Value", tag=Tag.COMPLEX_TYPE)
        inner = ClassFactory.enumeration(2, qname="{urn:aeep:issue1126}Status")
        for attribute, value in zip(inner.attrs, values):
            attribute.default = value
        parent.inner.append(inner)
        inner.parent = parent
        parent.attrs.append(AttrFactory.reference(inner.qname, forward=True))
        container.add(parent)
        parents.append(parent)

    promote = UnnestInnerClasses(container=container)
    for parent in parents:
        promote.process(parent)

    lookup = ProcessAttributeTypes(container=container)
    resolved = [
        lookup.find_dependency(parent, parent.attrs[0].types[0], Tag.ELEMENT)
        for parent in parents
    ]
    assert [{attribute.default for attribute in item.attrs} for item in resolved] == expected_values
