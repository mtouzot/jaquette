"""Command line: exit codes, output and options."""

import json

import pytest

from jaquette.cli import main

from .helpers import PRODUCT, SEARCH_ITEM, Script, reply, search_payload


@pytest.fixture
def run(monkeypatch, make_client):
    """Run the CLI against a fake server. Returns (script, run_function)."""

    def _run(script, *argv):
        monkeypatch.setattr("jaquette.cli.Client", lambda: make_client(script))
        return main(list(argv))

    return _run


def test_product_prints_a_summary(run, capsys):
    script = Script(reply(200, PRODUCT))
    assert run(script, "product", "3333290016961") == 0

    out = capsys.readouterr().out
    assert "Breaking Bad" in out
    assert "Sony Pictures" in out
    assert "iVBOR" not in out  # the base64 barcode is never printed


def test_product_json_leaves_the_barcode_out(run, capsys):
    script = Script(reply(200, PRODUCT))
    assert run(script, "product", "3333290016961", "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert data["isbn"] == 3333290016961
    assert "barcode" not in data


def test_search_prints_one_line_per_edition(run, capsys):
    script = Script(reply(200, search_payload(SEARCH_ITEM, SEARCH_ITEM)))
    assert run(script, "search", "Breaking", "Bad") == 0

    assert script.requests[0].url.params["q"] == "Breaking Bad"  # words are joined
    out = capsys.readouterr().out
    assert out.count("3333290016961") == 2
    assert "2 result(s)" in out


def test_search_warns_when_the_list_is_truncated(run, capsys):
    script = Script(reply(200, search_payload(SEARCH_ITEM, truncated=True)))
    assert run(script, "search", "Alien") == 0
    assert "incomplete" in capsys.readouterr().out


def test_search_does_not_warn_when_complete(run, capsys):
    script = Script(reply(200, search_payload(SEARCH_ITEM)))
    run(script, "search", "Alien")
    assert "incomplete" not in capsys.readouterr().out


def test_search_json(run, capsys):
    script = Script(reply(200, search_payload(SEARCH_ITEM)))
    assert run(script, "search", "Alien", "--json") == 0

    data = json.loads(capsys.readouterr().out)
    assert data["total"] == 1
    assert data["results"][0]["isbn"] == "3333290016961"


def test_search_filters_are_forwarded(run):
    script = Script(reply(200, search_payload()))
    run(
        script,
        "search",
        "Alien",
        "--media",
        "Blu-ray",
        "--media",
        "DVD",
        "--editeur",
        "Sony",
        "--from",
        "2015-01-01",
        "--to",
        "2020-12-31",
    )
    params = script.requests[0].url.params
    assert params.get_list("media") == ["Blu-ray", "DVD"]
    assert params["editeur"] == "Sony"
    assert params["parution_min"] == "2015-01-01"
    assert params["parution_max"] == "2020-12-31"
    assert "genre" not in params


def test_an_invalid_isbn_exits_1_without_a_request(run, capsys):
    script = Script()
    assert run(script, "product", "abc") == 1

    captured = capsys.readouterr()
    assert "Invalid ISBN" in captured.err
    assert captured.out == ""  # errors go to stderr only
    assert script.requests == []


def test_an_api_error_exits_1_with_its_message(run, capsys):
    script = Script(reply(404, {"error": "Aucun résultat trouvé pour ce code-barres"}))
    assert run(script, "product", "9999999999999") == 1

    err = capsys.readouterr().err
    assert err.startswith("Error:")
    assert "HTTP 404" in err
    assert "Aucun résultat" in err


def test_a_bad_date_exits_1(run, capsys):
    script = Script()
    assert run(script, "search", "Alien", "--from", "05/01/2015") == 1
    assert "parution_min" in capsys.readouterr().err


def test_no_command_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
