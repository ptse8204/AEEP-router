"""Finite synthetic independence probe; no routing service may initialize."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'integrations/toolkit'))
from aeep.router import Router


def prohibited(*args, **kwargs):
    raise AssertionError('Essentials must not construct Router')


Router.__init__ = prohibited
import evaluate

evaluate.main()
