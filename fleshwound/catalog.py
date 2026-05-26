"""Catalog registration for Fleshwound kinds."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


Executor = Callable[[Any, Any], Any]


class UnknownKind(KeyError):
    pass


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    executor: Executor
    convention: str
    monty: bool = False


class Catalog:
    def __init__(self) -> None:
        self._entries: dict[str, CatalogEntry] = {}

    def register(
        self, name: str, *, convention: str, monty: bool = False
    ) -> Callable[[Executor], Executor]:
        def decorate(executor: Executor) -> Executor:
            if name in self._entries:
                raise ValueError(f"duplicate catalog kind: {name}")
            self._entries[name] = CatalogEntry(name, executor, convention, monty)
            return executor

        return decorate

    def lookup(self, name: str) -> CatalogEntry:
        try:
            return self._entries[name]
        except KeyError as exc:
            raise UnknownKind(name) from exc

    @property
    def conventions(self) -> Mapping[str, str]:
        return MappingProxyType({name: entry.convention for name, entry in self._entries.items()})

    @property
    def entries(self) -> Mapping[str, CatalogEntry]:
        return MappingProxyType(dict(self._entries))


catalog = Catalog()


def register(
    name: str, *, convention: str, monty: bool = False
) -> Callable[[Executor], Executor]:
    return catalog.register(name, convention=convention, monty=monty)

