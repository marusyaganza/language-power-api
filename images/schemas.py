from pydantic import BaseModel

from core.image_source import ImageSource


class ImageHitOut(BaseModel):
    """One image found. The URLs are the search API's own: show them while choosing, never save them."""

    # Send it, with `source`, as the pick when saving the word (I5).
    id: str
    # About 150 px, for the grid of results.
    thumb_url: str
    # About 640 px, for the picked image on the form.
    preview_url: str
    # The shape of the image, to lay out the grid before the thumbnails load.
    width: int
    height: int
    # The image's page on the source's site, and who made it.
    page_url: str
    author: str


class ImageSearchOut(BaseModel):
    source: ImageSource
    items: list[ImageHitOut]
    # Results that can be paged through (Pixabay: at most 500), not every match.
    total: int
    page: int
    has_more: bool


class UsedImageOut(BaseModel):
    word_id: int
    img_url: str


class ImageSuggestionsOut(BaseModel):
    # The word's English meaning, to start the search box with; "" if it has none usable.
    query: str
    # Images already saved with the user's words of the same meaning (empty for now).
    used_before: list[UsedImageOut]
