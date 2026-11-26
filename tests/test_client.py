"""Client behaviour against a scripted fake server."""

import importlib
from datetime import date
from importlib import metadata
from importlib.metadata import PackageNotFoundError
from unittest.mock import Mock

import httpx
import pytest

from jaquette import (
    APIError,
    BadRequestError,
    Client,
    InvalidISBNError,
    InvalidQueryError,
    InvalidResponseError,
    JaquetteException,
    NotFoundError,
    ServerError,
    clients,
)

from .helpers import PNG_SIGNATURE, PRODUCT, SEARCH_ITEM, Script, reply, search_payload


def test_version_is_unknown_when_package_is_not_installed(monkeypatch):
    mock_version = Mock(side_effect=PackageNotFoundError)

    monkeypatch.setattr(metadata, "version", mock_version)

    try:
        importlib.reload(clients)

        assert clients._VERSION == "unknown"
        mock_version.assert_called_once_with("jaquette")
    finally:
        # Restaurer le module pour ne pas affecter les autres tests.
        monkeypatch.undo()
        importlib.reload(clients)


class TestGetProduct:
    def test_returns_a_typed_record(self, make_client):
        script = Script(reply(200, PRODUCT))
        product = make_client(script).get_product("3333290016961")

        assert len(script.requests) == 1
        assert script.requests[0].method == "GET"
        assert script.requests[0].url.path == "/api/product/3333290016961"
        assert product.title.startswith("Breaking Bad")
        assert product.isbn == 3333290016961
        assert product.barcode.startswith(PNG_SIGNATURE)
        assert str(product.image) == "https://images.example/cover.jpg"
        assert product.acteurs == ["Bryan Cranston", "Aaron Paul"]

    def test_leading_zeros_are_kept_in_the_path(self, make_client):
        script = Script(reply(200, {**PRODUCT, "isbn": 12345678}))
        make_client(script).get_product("00012345678")
        assert script.requests[0].url.path == "/api/product/00012345678"

    @pytest.mark.parametrize("value", ["abc", "", "1234567", 3333290016961, None])
    def test_invalid_isbn_sends_nothing(self, make_client, value):
        script = Script()
        with pytest.raises(InvalidISBNError):
            make_client(script).get_product(value)
        assert script.requests == []


class TestSearch:
    def test_returns_results_that_can_be_iterated(self, make_client):
        script = Script(reply(200, search_payload(SEARCH_ITEM, SEARCH_ITEM)))
        results = make_client(script).search("Breaking Bad")

        assert script.requests[0].url.path == "/api/search/"
        assert script.requests[0].url.params["q"] == "Breaking Bad"
        assert len(results) == 2
        assert [item.isbn for item in results] == ["3333290016961"] * 2
        assert results.truncated is False

    def test_all_filters_are_sent(self, make_client):
        script = Script(reply(200, search_payload()))
        make_client(script).search(
            "Alien",
            media=["DVD", "Blu-ray"],
            editeur="Sony Pictures",
            genre=["Horreur"],
            parution_min=date(2015, 1, 1),
            parution_max="2020-12-31",
        )
        params = script.requests[0].url.params
        assert params["q"] == "Alien"
        assert params.get_list("media") == ["DVD", "Blu-ray"]
        assert params.get_list("editeur") == ["Sony Pictures"]
        assert params.get_list("genre") == ["Horreur"]
        assert params["parution_min"] == "2015-01-01"
        assert params["parution_max"] == "2020-12-31"

    def test_unset_filters_are_not_in_the_url(self, make_client):
        script = Script(reply(200, search_payload()))
        make_client(script).search("Alien")
        assert set(script.requests[0].url.params) == {"q"}

    def test_a_title_with_special_characters_stays_intact(self, make_client):
        script = Script(reply(200, search_payload()))
        make_client(script).search("AC/DC ? Live & more")
        assert script.requests[0].url.params["q"] == "AC/DC ? Live & more"
        assert script.requests[0].url.path == "/api/search/"

    def test_truncated_flag_is_exposed(self, make_client):
        script = Script(reply(200, search_payload(truncated=True)))
        assert make_client(script).search("Alien").truncated is True

    @pytest.mark.parametrize("query", ["", "   ", "a"])
    def test_a_too_short_title_sends_nothing(self, make_client, query):
        script = Script()
        with pytest.raises(InvalidQueryError):
            make_client(script).search(query)
        assert script.requests == []

    def test_a_malformed_date_sends_nothing(self, make_client):
        script = Script()
        with pytest.raises(InvalidQueryError):
            make_client(script).search("Alien", parution_min="05/01/2015")
        assert script.requests == []


class TestHttpErrors:
    def test_404_becomes_not_found_with_the_api_message(self, make_client):
        script = Script(
            reply(404, {"error": "Aucun résultat trouvé pour ce code-barres"})
        )
        with pytest.raises(NotFoundError) as exc:
            make_client(script).get_product("9999999999999")
        assert exc.value.status_code == 404
        assert exc.value.message == "Aucun résultat trouvé pour ce code-barres"
        assert exc.value.payload == {
            "error": "Aucun résultat trouvé pour ce code-barres"
        }
        assert len(script.requests) == 1  # a 404 is never retried

    @pytest.mark.parametrize("status", [400, 422])
    def test_400_and_422_become_bad_request(self, make_client, status):
        script = Script(reply(status, {"error": "Requête trop courte"}))
        with pytest.raises(BadRequestError) as exc:
            make_client(script).search("Alien")
        assert exc.value.message == "Requête trop courte"
        assert len(script.requests) == 1

    def test_500_is_a_server_error_and_is_not_retried(self, make_client):
        script = Script(reply(500, {"error": "boom"}))
        with pytest.raises(ServerError):
            make_client(script).get_product("3333290016961")
        assert len(script.requests) == 1

    def test_other_statuses_fall_back_to_api_error(self, make_client):
        script = Script(reply(403, {"error": "forbidden"}))
        with pytest.raises(APIError) as exc:
            make_client(script).get_product("3333290016961")
        assert type(exc.value) is APIError
        assert exc.value.status_code == 403

    def test_a_non_json_error_body_is_kept_as_the_message(self, make_client):
        script = Script(httpx.Response(404, text="<html>Not found</html>"))
        with pytest.raises(NotFoundError) as exc:
            make_client(script).get_product("3333290016961")
        assert exc.value.message == "<html>Not found</html>"

    def test_a_json_error_without_error_field_keeps_its_payload(self, make_client):
        script = Script(reply(404, {"detail": "nope"}))
        with pytest.raises(NotFoundError) as exc:
            make_client(script).get_product("3333290016961")
        assert exc.value.payload == {"detail": "nope"}

    def test_every_error_is_a_jaquette_exception(self, make_client):
        script = Script(reply(404, {"error": "x"}))
        with pytest.raises(JaquetteException):
            make_client(script).get_product("3333290016961")


class TestInvalidResponse:
    def test_missing_required_fields(self, make_client):
        script = Script(reply(200, {}))
        with pytest.raises(InvalidResponseError):
            make_client(script).get_product("3333290016961")

    def test_a_non_json_body(self, make_client):
        script = Script(httpx.Response(200, text="<html>maintenance</html>"))
        with pytest.raises(InvalidResponseError):
            make_client(script).get_product("3333290016961")

    def test_wrong_field_type(self, make_client):
        script = Script(reply(200, search_payload(total="many")))
        with pytest.raises(InvalidResponseError):
            make_client(script).search("Alien")

    def test_the_original_error_is_chained(self, make_client):
        script = Script(reply(200, {}))
        with pytest.raises(InvalidResponseError) as exc:
            make_client(script).get_product("3333290016961")
        assert exc.value.__cause__ is not None


class TestLifecycle:
    def test_default_http_client_is_configured(self):
        client = Client()
        try:
            assert str(client._http.base_url).startswith("https://mybluray.fr")
            assert client._http.headers["accept"] == "application/json"
            assert client._http.headers["user-agent"].startswith("jaquette/")
            assert client._http.follow_redirects is True
            assert client._http.timeout.read == 15.0
        finally:
            client.close()

    def test_options_are_forwarded(self):
        client = Client("https://example.org", timeout=3.0)
        try:
            assert str(client._http.base_url).startswith("https://example.org")
            assert client._http.timeout.read == 3.0
        finally:
            client.close()

    def test_close_closes_a_client_it_created(self):
        client = Client()
        client.close()
        assert client._http.is_closed

    def test_close_leaves_a_client_you_passed_open(self):
        http = httpx.Client(transport=httpx.MockTransport(Script()))
        Client(client=http).close()
        assert not http.is_closed
        http.close()

    def test_context_manager_closes_on_exit(self):
        with Client() as client:
            assert not client._http.is_closed
        assert client._http.is_closed

    def test_context_manager_closes_and_propagates_errors(self):
        with pytest.raises(RuntimeError, match="boom"), Client() as client:
            raise RuntimeError("boom")
        assert client._http.is_closed

    def test_negative_max_retries_is_rejected(self):
        with pytest.raises(ValueError, match="max_retries"):
            Client(max_retries=-1)

    def test_repr(self):
        with Client() as client:
            assert repr(client) == "Client(base_url='https://mybluray.fr')"
