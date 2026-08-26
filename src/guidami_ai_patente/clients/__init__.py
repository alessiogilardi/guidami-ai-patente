"""Providers for objects the container cannot build itself (spec 0012, AD-16).

Reserved for classes shared with the pre-pywire packages (`commons/`, `labeling/`)
or owned by a third party. New API code is pywire-native and belongs in
`services/`, `repositories/` or `agents/` instead.
"""

from .labeling_stack_provider import LabelingStackProvider
from .postgres_client_provider import PostgresClientProvider

__all__ = ["LabelingStackProvider", "PostgresClientProvider"]
