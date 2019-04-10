from typing import Dict, List, overload, Iterator
from typing_extensions import Literal

class BeautifulSoup:
    def __init__(self, markup: str, features: str):
        pass

    def find(self, name: str, attrs: Dict[str, str]) -> Tag:
        pass

class PageElement:
    pass

class NavigableString(PageElement):
    pass

class Tag(PageElement):
    def __iter__(self) -> Iterator[PageElement]:
        pass

    @property
    def children(self) -> Iterator[PageElement]:
        pass

    @property
    def text(self) -> str:
        pass

    def find(self, name: str, attrs: Dict[str, str] = {}) -> Tag:
        pass

    @overload
    def __getitem__(self, item: Literal["class"]) -> List[str]:
        pass

    @overload
    def __getitem__(self, item: Literal["href", "title"]) -> str:
        pass
