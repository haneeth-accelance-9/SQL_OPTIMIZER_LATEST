"""
Root conftest.py — applies project-wide pytest configuration.

Fixes Django 4.2 + Python 3.14 incompatibility:
In Python 3.14, copy(super()) returns a super-proxy object instead of
copying the underlying instance, breaking BaseContext.__copy__.
"""
from copy import copy as _copy

from django.template.context import BaseContext


def _py314_compatible_base_context_copy(self):
    cls = self.__class__
    duplicate = cls.__new__(cls)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate


BaseContext.__copy__ = _py314_compatible_base_context_copy
