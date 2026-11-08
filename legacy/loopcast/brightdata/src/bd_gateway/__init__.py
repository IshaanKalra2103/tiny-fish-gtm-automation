from .gateway import PLATFORMS, BrightDataError, BrightDataGateway

__all__ = ["PLATFORMS", "BrightDataError", "BrightDataGateway", "main"]


def main() -> None:
    from .cli import main as cli_main

    raise SystemExit(cli_main())
