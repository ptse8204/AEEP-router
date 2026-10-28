"""Authored from issue1132's RootEle/Bar/Baz/Foo parent-path example.

Check observable decorator selection for matching and nonmatching parents. No
private matcher method or published patch text is asserted.
"""
from xsdata.formats.dataclass.filters import Filters
from xsdata.models.config import ExtensionType, GeneratorConfig, GeneratorExtension
from xsdata.models.enums import Tag
from xsdata.utils.testing import ClassFactory


def test_decorator_matches_only_the_requested_parent_path():
    root = ClassFactory.create(qname="RootEle", tag=Tag.COMPLEX_TYPE)
    direct = ClassFactory.create(qname="Foo", parent=root, tag=Tag.COMPLEX_TYPE)
    bar = ClassFactory.create(qname="Bar", parent=root, tag=Tag.COMPLEX_TYPE)
    nested = ClassFactory.create(qname="Foo", parent=bar, tag=Tag.COMPLEX_TYPE)
    baz = ClassFactory.create(qname="Baz", parent=bar, tag=Tag.COMPLEX_TYPE)
    deeper = ClassFactory.create(qname="Foo", parent=baz, tag=Tag.COMPLEX_TYPE)

    config = GeneratorConfig()
    config.extensions.extension = [
        GeneratorExtension(
            type=ExtensionType.DECORATOR,
            class_name="Foo",
            parent_path=r"RootEle\.Bar$",
            import_string="my_decs.my_foo_decorator",
            apply_if_derived=False,
            prepend=False,
        )
    ]
    filters = Filters(config)
    filters.default_class_annotation = None
    assert filters.class_annotations(direct, "Foo") == []
    assert filters.class_annotations(nested, "Foo") == ["@my_foo_decorator"]
    assert filters.class_annotations(deeper, "Foo") == []
