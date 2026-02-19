import argparse
import warnings

from birdsnet_dash.generate import generate


def main():
    parser = argparse.ArgumentParser(description="BirdNET-Pi aggregator dashboard generator")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Run health checks and generate dashboard HTML")
    gen.add_argument(
        "--output-dir",
        default="./site",
        help="Directory to write index.html (default: ./site)",
    )

    args = parser.parse_args()

    if args.command == "generate":
        # Suppress InsecureRequestWarning from urllib3 (httpx verify=False)
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        generate(args.output_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
