from pydantic import Base64Bytes, BaseModel, ConfigDict, Field, HttpUrl


class _ApiModel(BaseModel):
    """Shared configuration: field docstrings are exposed as descriptions."""

    model_config = ConfigDict(use_attribute_docstrings=True)


class ProductResponse(_ApiModel):
    """Full cover art record (GET /api/product/{isbn})."""

    title: str
    """Title of the edition, e.g. ``"Breaking Bad - Intégrale de la série + El Camino : un film \"Breaking Bad\"``."""

    title_vo: str
    """Title of the edition in the original language, e.g. ``"Breaking Bad + El Camino: A Breaking Bad Movie"``."""

    annee: str
    """Year of the film or series, e.g. ``"2008"``."""

    description: str
    """Synopsis, e.g. ``"Walter White, 50 ans, est professeur de chimie dans un lycée du Nouveau-Mexique..."``."""

    image: HttpUrl
    """URL of the cover art, e.g. ``"https://images.epagine.fr/5298/529876c88590b26470b6a8f19bb0955a_1_v.jpg"``."""

    categorie: str
    """DVDFr category, e.g. ``"Série"``."""

    duree: str
    """Duration , e.g. ``"3070 mn"``."""

    sortie: str
    """Online release date / media release date displayed on DVDFr, e.g. ``"5 Octobre 2022"``."""

    isbn: int
    """EAN barcode, as an integer, e.g. ``3333290016961``."""

    barcode: Base64Bytes = Field(..., repr=False)  # PNG bytes, decoded from base64
    """PNG image of the EAN-13 barcode, encoded in Base64, e.g. ``b'iVBORw0KGgoAAAANSUhEUgAAAGQAA..."``."""

    editeur: str
    """Publisher, e.g. ``"Sony Pictures"``."""

    distributeur: str
    """Distributor, e.g. ``"ESCD"``."""

    collection: str
    """Collection, e.g. ``"Metropolitan Edition Haute Définition"``."""

    media: str
    """Media type : Blu-ray, DVD, 4K Ultra HD... e.g. ``"Blu-ray"``."""

    edition: str
    """Collection / Edition (also known as a collection), e.g. ``"Metropolitan Edition Haute Définition"``."""

    acteurs: list[str] = Field(default_factory=list)
    """Actors, when available on the page, e.g. ``["Bryan Cranston", "Aaron Paul", "Anna Gunn"]``."""

    producteurs: list[str] = Field(default_factory=list)
    """Producers, when available on the page, e.g. ``["Vince Gilligan", "Mark Johnson"]``."""

    prix: str
    """Recommended price as displayed, e.g. ``"49.91 €"``."""

    date_sortie: str
    """Theatrical release date / premiere date, e.g. ``"20/01/2008"``."""

    date_parution: str
    """Release date of the media cover, e.g. ``"05/10/2022"``."""

    genres: list[str] = Field(default_factory=list)
    """Genres (rayons DVDFr), e.g. ``["Drame"]``."""

    source: HttpUrl
    """DVDFr product page URL, e.g. ``"https://www.dvdfr.com/dvd/3333290016961-breaking-bad-integrale-de-la-serie/"``."""


class SearchItem(_ApiModel):
    """Single search result (GET /api/search/{query})."""

    isbn: str
    """EAN barcode, as a string, e.g. ``"3333290016961"``."""

    title: str
    """Title of the edition, e.g. ``"Breaking Bad - Intégrale de la série + El Camino : un film \"Breaking Bad\"``."""

    annee: str
    """Year of the film or series, e.g. ``"2008"``."""

    image: HttpUrl
    """URL of the cover art, e.g. ``"https://images.epagine.fr/5298/529876c88590b26470b6a8f19bb0955a_1_v.jpg"``."""

    editeur: str
    """Publisher, e.g. ``"Sony Pictures"``."""

    media: str
    """Media type : Blu-ray, DVD, 4K Ultra HD... e.g. ``"Blu-ray"``."""

    prix: str
    """Recommended price as displayed, e.g. ``"49.91 €"``."""

    date_parution: str
    """Release date of the media cover, e.g. ``"5 Octobre 2022"``."""

    description: str
    """Synopsis, e.g. ``"Walter White, 50 ans, est professeur de chimie..."``."""

    genres: list[str] = Field(default_factory=list)
    """DVDFr genres, when available on the page, e.g. ``["Fantastique / Science-fiction"]``."""

    url: HttpUrl
    """URL of the DVDFr page for this edition, e.g. ``"https://www.dvdfr.com/dvd/3333290016961-breaking-bad-integrale-de-la-serie/"``."""

    source: HttpUrl
    """URL of the DVDFr page for this edition, e.g. ``"https://www.dvdfr.com/dvd/3333290016961-breaking-bad-integrale-de-la-serie/"``."""


class SearchResponse(_ApiModel):
    """Search results by title (GET /api/search/{query}).

    Iterating over it yields the editions in :attr:`results`.
    """

    query: str
    """The title that was searched."""

    total: int  # titles/editions returned, including other editions
    """Number of titles/editions returned, other editions included."""

    dvdfr_total: int  # products announced by DVDFr, excluding other editions
    """Number of products announced by DVDFr, other editions excluded."""

    truncated: bool = False  # True if not all DVDFr pages could be crawled
    """``True`` if not all DVDFr pages could be crawled: the list is incomplete."""

    results: list[SearchItem] = Field(default_factory=list)
    """The editions found."""

    def __iter__(self):
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


class ApiErrorBody(_ApiModel):
    """Error response body."""

    error: str
    """Human-readable error message."""

    isbn: int | None = None
    """The barcode that was requested, when the error relates to one."""

    query: str | None = None
    """The title that was searched, when the error relates to a search."""
