"""Reuse AST and patch-data checks without running subject code."""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    specification = importlib.util.spec_from_file_location('inert_repository_data_audit', HERE.parent / 'repository-workload-batch-20261022/audit-source-data.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module.HERE = HERE
    module.main()


if __name__ == '__main__':
    main()
