"""Reuse the reviewed bounded package/docs driver with this review's inputs."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
old=HERE.parent/'skillrank-build-preparation-20261103/run-components.py'
spec=importlib.util.spec_from_file_location('aeep_retained_component_driver',old)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE=HERE
module.ROOT=HERE.parents[3]
if __name__=='__main__':module.main()
