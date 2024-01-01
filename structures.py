from collections.abc import Mapping, MutableMapping, Iterable, Iterator, MutableSet
from typing import TypeVar, Optional

_T = TypeVar('_T')
_VT = TypeVar('_VT')


class CaselessDict(MutableMapping[str, _VT]):
    _store: dict[str, tuple[str, _VT]]

    def __init__(self, m: Optional[Mapping[str, _VT] | Iterable[tuple[str, _VT]]] = None,
                 **kwargs):
        self._store = dict()
        if m is None:
            self.update(**kwargs)
        else:
            self.update(m, **kwargs)

    def __len__(self):
        return len(self._store)

    def __getitem__(self, key: str) -> _VT:
        return self._store[key.casefold()][1]

    def __iter__(self) -> Iterator[str]:
        return (cased_key for cased_key, mapped_value in self._store.values())

    def __setitem__(self, key: str, value: _VT):
        # store original key too
        self._store[key.casefold()] = (key, value)

    def __delitem__(self, key: str):
        del self._store[key.casefold()]

    def clear(self):
        self._store.clear()

    def items_caseless(self):
        """Like items(), but with the caseless keys."""
        return (
            (caseless_key, value_tuple[1])
            for caseless_key, value_tuple
            in self._store.items()
        )

    def __eq__(self, other):
        if isinstance(other, Mapping):
            other = CaselessDict(other)
        else:
            return NotImplemented
        return dict(self.items_caseless()) == dict(other.items_caseless())

    def __repr__(self):
        return str(dict(self.items()))


class CaselessSet(MutableSet[str]):
    # caseless key -> cased key
    _store: dict[str, str]

    def __init__(self, m: Optional[Iterable[str]] = None):
        self._store = dict()

        if m is not None:
            for i in m:
                self.add(i)

    def __len__(self):
        return len(self._store)

    def __contains__(self, x: str):
        return x.casefold() in self._store

    def __iter__(self) -> Iterator[str]:
        return (cased_key for cased_key in self._store.values())

    def add(self, value: str):
        self._store.setdefault(value.casefold(), value)

    def discard(self, value: str):
        try:
            del self._store[value.casefold()]
        except KeyError:
            pass

    def remove(self, value: str):
        del self._store[value.casefold()]

    def clear(self):
        self._store.clear()

    def iter_caseless(self):
        """Like __iters__(), but with the caseless values."""
        return (caseless_key for caseless_key in self._store.keys())

    def __eq__(self, other):
        if isinstance(other, AbstractSet):
            other = CaselessSet(other)
        else:
            return NotImplemented
        return set(self.iter_caseless()) == set(other.iter_caseless())

    def __repr__(self):
        return str(set(self.__iter__()))
