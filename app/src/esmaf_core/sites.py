"""Sites: the places the samples came from, and how their names are read.

One spreadsheet may hold samples from several places, and two places rarely
share a soil. Since the factor classes are what tune every scoring curve to a
soil, each place needs its own set of them; scoring a clayey Oxisol under a
sandy site's description is exactly the bias the analysis check exists to
prevent.

The awkward part is that a site is identified by whatever the user typed. The
same farm arrives as "Fazenda do Seu Zé", "FAZENDA DO SEU ZE" and "Fazenda Seu
Zé", and treating those as three places would make the user describe the same
soil three times. So the names are tidied in two tiers, and the tiers are kept
strictly apart:

* **Merged automatically** — spellings that are identical once case, accents,
  punctuation and the connecting words are set aside. That is orthography, not
  judgement: it cannot fuse two places that were actually named differently.
  Every merge is reported, so a surprise is visible rather than silent.
* **Proposed, never applied** — names that are merely *similar* once the words
  they share are set aside: "Fazenda Guaraci" and "Fazenda Guarasi", or
  "Sítio São João" and "Sítio São João II". They may well be the same farm,
  but deciding that is a claim about the world, not about spelling. They stay
  separate, each asking for its own factor classes, until the user says
  otherwise; a confirmed merge is then stored in the project and travels with
  it.

Nothing here computes a score. It only decides which rows share a description.
"""

from __future__ import annotations

import difflib
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

#: The name used when the spreadsheet has no site column at all. A file
#: without one is a single unnamed place, which is how every earlier version
#: of eSMAF behaved.
SINGLE_SITE = "All samples"

#: Words that carry no identity of their own in a place name. Dropping them
#: makes "Fazenda do Seu Zé" and "Fazenda Seu Zé" the same string without
#: making any two distinct names collide.
CONNECTIVES = frozenset({
    "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
    "of", "the", "at", "a", "o", "as", "os",
})

#: Above this, the *distinctive* parts of two names -- what is left once the
#: words they share are set aside -- are close enough to be worth proposing as
#: one place. Comparing the whole string instead is what a first version did,
#: and it proposed almost everything: "Fazenda" is more than half the
#: characters of a short farm name, so "Fazenda Apiai" and "Fazenda Areiao"
#: scored 0.82 on two farms that have nothing in common. A warning raised on
#: every pair is a warning nobody reads.
SIMILARITY = 0.70


def canonical(name: str) -> str:
    """The comparison form of a site name: orthography only.

    Case, accents, punctuation, repeated spaces and connecting words are set
    aside. What survives is the sequence of meaningful words, lowercased.
    """
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = "".join(ch if ch.isalnum() else " " for ch in text).lower()
    raw = text.split()
    words = [w for position, w in enumerate(raw)
             if not _is_connective(w, position, len(raw))]
    return " ".join(words) or " ".join(raw)


def _is_connective(word: str, position: int, total: int) -> bool:
    """Is this word a connector, or is it the name itself?

    Two exceptions keep "Talhao A" and "Fazenda B" apart. A single letter is
    an identifier, not a preposition -- and so is a connective in final
    position: "Gleba E" is the fifth plot, while the "e" of "Santa Rita e Sao
    Jose" joins two words that both follow it. Without this, "Fazenda A" tidies
    down to "fazenda" and merges silently with a site actually called
    "Fazenda", which is the one mistake this module must not make.
    """
    if len(word) == 1 or position == total - 1:
        return False
    return word in CONNECTIVES


@dataclass(frozen=True)
class Site:
    """One place, with every spelling that was read as it."""

    name: str                        # the spelling shown everywhere
    spellings: tuple[str, ...]       # all spellings, most frequent first
    rows: int

    @property
    def merged(self) -> bool:
        return len(self.spellings) > 1


@dataclass(frozen=True)
class Suggestion:
    """Two sites that look like one place. Never applied on its own."""

    first: str
    second: str
    similarity: float

    @property
    def message(self) -> str:
        return (f"'{self.first}' and '{self.second}' are spelled almost the "
                f"same. If they are the same place, say so and they will share "
                f"one set of factor classes; otherwise describe each of them.")


@dataclass
class SiteIndex:
    """The sites in a dataset and how each raw spelling reaches one."""

    sites: tuple[Site, ...] = ()
    mapping: Mapping[str, str] = field(default_factory=dict)
    suggestions: tuple[Suggestion, ...] = ()
    from_column: bool = True

    @property
    def names(self) -> list[str]:
        return [site.name for site in self.sites]

    @property
    def several(self) -> bool:
        return len(self.sites) > 1

    def resolve(self, raw: object) -> str:
        text = "" if raw is None else str(raw).strip()
        if not text:
            return SINGLE_SITE
        return self.mapping.get(canonical(text), text)

    def spelling_notes(self) -> list[str]:
        """One line per site whose spellings were tidied into one."""
        notes = []
        for site in self.sites:
            if site.merged:
                others = ", ".join(f"'{s}'" for s in site.spellings[1:])
                notes.append(
                    f"{others} {'were' if len(site.spellings) > 2 else 'was'} "
                    f"read as '{site.name}' — the same name written differently."
                )
        return notes


def build(values: Iterable[object] | None,
          merges: Sequence[Sequence[str]] = ()) -> SiteIndex:
    """Group the raw site values of a dataset into sites.

    ``merges`` are the groupings the user has confirmed, as lists of site
    names that mean one place. They are applied after the automatic tidying
    and are the only way two differently-named places ever become one.
    """
    if values is None:
        return SiteIndex(
            sites=(Site(SINGLE_SITE, (SINGLE_SITE,), 0),),
            mapping={canonical(SINGLE_SITE): SINGLE_SITE},
            from_column=False,
        )

    raw = [str(v).strip() for v in values
           if v is not None and str(v).strip() and str(v).strip().lower() != "nan"]
    if not raw:
        return SiteIndex(
            sites=(Site(SINGLE_SITE, (SINGLE_SITE,), 0),),
            mapping={canonical(SINGLE_SITE): SINGLE_SITE},
            from_column=False,
        )

    # --- tier one: spellings that tidy to the same string ------------------
    buckets: dict[str, Counter] = {}
    for value in raw:
        buckets.setdefault(canonical(value), Counter())[value] += 1

    # --- the confirmed merges join whole buckets --------------------------
    union = _Union(buckets)
    for group in merges:
        keys = [canonical(name) for name in group if canonical(name) in buckets]
        for other in keys[1:]:
            union.join(keys[0], other)

    grouped: dict[str, Counter] = {}
    for key, counter in buckets.items():
        grouped.setdefault(union.find(key), Counter()).update(counter)

    sites: list[Site] = []
    mapping: dict[str, str] = {}
    for key, counter in grouped.items():
        spellings = tuple(name for name, _ in
                          sorted(counter.items(),
                                 key=lambda kv: (-kv[1], _typography(kv[0]),
                                                 -len(kv[0]), kv[0])))
        site = Site(name=spellings[0], spellings=spellings,
                    rows=sum(counter.values()))
        sites.append(site)
        for spelling in spellings:
            mapping[canonical(spelling)] = site.name
    sites.sort(key=lambda s: s.name.lower())

    return SiteIndex(sites=tuple(sites), mapping=mapping,
                     suggestions=_suggest(sites), from_column=True)


def _typography(name: str) -> int:
    """Rank spellings by how much they look like a name, lower being better.

    When the same place was written the same number of times two ways, the one
    shown everywhere afterwards should be the one a person would write by hand:
    "Fazenda do Seu Zé" rather than "FAZENDA DO SEU ZE".
    """
    letters = [ch for ch in name if ch.isalpha()]
    if not letters:
        return 3
    if all(ch.isupper() for ch in letters):
        return 2
    if all(ch.islower() for ch in letters):
        return 1
    return 0


def _suggest(sites: Sequence[Site]) -> tuple[Suggestion, ...]:
    """Pairs close enough to be worth asking about, closest first.

    The comparison is made on what the two names do *not* share. Farm names in
    one file almost always open with the same word -- Fazenda, Sitio, Talhao,
    Gleba, Area -- and that word is long enough to carry a pair of unrelated
    names over any sensible threshold. Setting the shared words aside leaves
    the part that actually identifies the place, and a proposal is made when
    one name contains the other ("Sitio Sao Joao" and "Sitio Sao Joao II") or
    when the distinctive parts are near-spellings of each other ("Guaraci" and
    "Guarasi").

    What this deliberately does not catch is two different words for one place:
    "Fazenda Seu Ze" and "Fazenda seu Jose" are the same farm to a Brazilian
    reader and nothing to a character comparison. Proposing that pair means
    proposing every pair, which is worse. Both sites appear in Setup asking for
    their own factor classes, so a duplicate is visible there.
    """
    out: list[Suggestion] = []
    for i, first in enumerate(sites):
        for second in sites[i + 1:]:
            ratio = _closeness(canonical(first.name), canonical(second.name))
            if ratio < SIMILARITY:
                continue
            out.append(Suggestion(first.name, second.name, round(ratio, 3)))
    out.sort(key=lambda s: -s.similarity)
    return tuple(out)


def _closeness(a: str, b: str) -> float:
    """How alike two tidied names are, once the words they share are removed."""
    first, second = a.split(), b.split()
    head = 0
    while head < min(len(first), len(second)) and first[head] == second[head]:
        head += 1
    tail = 0
    while (tail < min(len(first), len(second)) - head
           and first[len(first) - 1 - tail] == second[len(second) - 1 - tail]):
        tail += 1
    left = " ".join(first[head:len(first) - tail])
    right = " ".join(second[head:len(second) - tail])
    if not left or not right:
        # One name is the other with a word added or removed. Genuinely
        # ambiguous, and the user is the only one who can settle it.
        return 1.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _unused_shares_all_but_one_word(a: str, b: str) -> bool:
    first, second = a.split(), b.split()
    if len(first) != len(second) or len(first) < 2:
        return False
    differing = [(x, y) for x, y in zip(first, second) if x != y]
    if len(differing) != 1:
        return False
    x, y = differing[0]
    return difflib.SequenceMatcher(None, x, y).ratio() >= 0.5


class _Union:
    """Smallest possible union-find, for applying the confirmed merges."""

    def __init__(self, keys: Iterable[str]) -> None:
        self._parent = {key: key for key in keys}

    def find(self, key: str) -> str:
        while self._parent[key] != key:
            self._parent[key] = self._parent[self._parent[key]]
            key = self._parent[key]
        return key

    def join(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra
