"""Models: parsing, derived values and documentation."""

import pydantic
import pytest

from jaquette import ProductResponse, SearchItem, SearchResponse
from jaquette.models import ApiErrorBody

from .helpers import PNG_SIGNATURE, PRODUCT, SEARCH_ITEM, search_payload


class TestProductResponse:
    def test_parses_a_full_record(self):
        product = ProductResponse.model_validate(PRODUCT)
        assert product.isbn == 3333290016961
        assert product.barcode.startswith(PNG_SIGNATURE)  # decoded from base64
        assert product.genres == ["Drame"]

    def test_unknown_fields_are_ignored(self):
        ProductResponse.model_validate({**PRODUCT, "a_new_field": 1})

    @pytest.mark.parametrize("field", ["title", "isbn", "image", "barcode", "source"])
    def test_a_missing_required_field_fails(self, field):
        payload = {k: v for k, v in PRODUCT.items() if k != field}
        with pytest.raises(pydantic.ValidationError, match=field):
            ProductResponse.model_validate(payload)

    def test_lists_default_to_empty(self):
        payload = {
            k: v
            for k, v in PRODUCT.items()
            if k not in {"acteurs", "producteurs", "genres"}
        }
        product = ProductResponse.model_validate(payload)
        assert product.acteurs == product.producteurs == product.genres == []

    def test_an_invalid_url_fails(self):
        with pytest.raises(pydantic.ValidationError):
            ProductResponse.model_validate({**PRODUCT, "image": "not a url"})

    def test_the_barcode_is_left_out_of_repr(self):
        assert "barcode" not in repr(ProductResponse.model_validate(PRODUCT))

    def test_the_barcode_round_trips_through_json(self):
        product = ProductResponse.model_validate(PRODUCT)
        again = ProductResponse.model_validate_json(product.model_dump_json())
        assert again.barcode == product.barcode


class TestSearchModels:
    def test_search_item(self):
        item = SearchItem.model_validate(SEARCH_ITEM)
        assert item.isbn == "3333290016961"  # a string here, unlike ProductResponse
        assert str(item.url).startswith("https://www.dvdfr.com/")

    def test_response_can_be_iterated_and_measured(self):
        response = SearchResponse.model_validate(
            search_payload(SEARCH_ITEM, SEARCH_ITEM)
        )
        assert len(response) == 2
        assert all(isinstance(item, SearchItem) for item in response)

    def test_truncated_defaults_to_false(self):
        payload = search_payload()
        del payload["truncated"]
        assert SearchResponse.model_validate(payload).truncated is False

    def test_an_empty_result_list_is_valid(self):
        response = SearchResponse.model_validate(search_payload())
        assert len(response) == 0
        assert list(response) == []


class TestApiErrorBody:
    def test_only_the_message_is_required(self):
        body = ApiErrorBody.model_validate({"error": "nope"})
        assert body.isbn is None
        assert body.query is None

    def test_it_accepts_the_optional_context(self):
        body = ApiErrorBody.model_validate(
            {"error": "nope", "isbn": 123, "query": "Alien"}
        )
        assert (body.isbn, body.query) == (123, "Alien")


@pytest.mark.parametrize(
    "model", [ProductResponse, SearchItem, SearchResponse, ApiErrorBody]
)
def test_every_field_is_documented(model):
    """Field docstrings feed the generated API reference."""
    undocumented = [
        name for name, field in model.model_fields.items() if not field.description
    ]
    assert not undocumented, f"{model.__name__}: no docstring for {undocumented}"
