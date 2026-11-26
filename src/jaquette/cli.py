import argparse
import sys

from .clients import Client
from .exceptions import JaquetteException
from .models import ProductResponse, SearchResponse


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jaquette",
        description="Query the public MyBluray API (non-commercial use only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    product = sub.add_parser("product", help="show a cover art record by ISBN/EAN")
    product.add_argument("isbn")
    product.add_argument("--json", action="store_true", help="print raw JSON")

    search = sub.add_parser("search", help="search editions by title")
    search.add_argument("query", nargs="+", help="title (quotes optional)")
    search.add_argument("--json", action="store_true", help="print raw JSON")

    # Optional search filters
    search.add_argument("--media", action="append", help="media type (repeatable)")
    search.add_argument("--editeur", action="append", help="publisher (repeatable)")
    search.add_argument("--genre", action="append", help="genre (repeatable)")
    search.add_argument(
        "--from",
        dest="parution_min",
        metavar="YYYY-MM-DD",
        help="earliest release date",
    )
    search.add_argument(
        "--to", dest="parution_max", metavar="YYYY-MM-DD", help="latest release date"
    )

    return parser


def _format_product(p: ProductResponse) -> str:
    title = f"{p.title} ({p.annee})" if p.annee else p.title
    details = " - ".join(part for part in (p.media, p.editeur, p.prix) if part)
    lines = [title, details, str(p.source) if p.source else ""]
    return "\n".join(line for line in lines if line)


def _format_search(r: SearchResponse) -> str:
    lines = [f"{item.isbn}  {item.title}" for item in r.results]
    lines.append(f"{len(r.results)} result(s)")
    if r.truncated:
        lines.append(
            "Warning: results are incomplete (not all pages could be fetched)."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        with Client() as client:
            if args.command == "product":
                product = client.get_product(args.isbn)
                print(
                    product.model_dump_json(indent=2, exclude={"barcode"})
                    if args.json
                    else _format_product(product)
                )
            else:
                results = client.search(
                    " ".join(args.query),
                    media=args.media,
                    editeur=args.editeur,
                    genre=args.genre,
                    parution_min=args.parution_min,
                    parution_max=args.parution_max,
                )
                print(
                    results.model_dump_json(indent=2)
                    if args.json
                    else _format_search(results)
                )
    except JaquetteException as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
