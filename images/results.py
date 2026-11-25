from dataclasses import dataclass

# Thumbnails per page of results: a grid of 4×3 on the edit form.
PAGE_SIZE = 12


@dataclass(frozen=True)
class ImageHit:
    """One image found, with the URLs the app needs at each step.

    `thumb_url` (about 150 px) is for the grid of results and `preview_url`
    (about 640 px) for the picked image on the form. Both are the API's own
    URLs: shown while the user chooses, never saved. `download_url` (up to
    1280 px) is what the server downloads and stores when the word is saved.
    `width` and `height` give the shape of the image (every size has the same).
    `page_url` and `author` are for credit.
    """

    id: str
    thumb_url: str
    preview_url: str
    download_url: str
    width: int
    height: int
    page_url: str
    author: str


@dataclass(frozen=True)
class ImageResults:
    """One page of results. `total` counts the results reachable by paging, not every match."""

    items: list[ImageHit]
    total: int
    page: int

    @property
    def has_more(self) -> bool:
        return self.page * PAGE_SIZE < self.total
