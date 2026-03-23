"""CLI entry for agent-rms."""

from __future__ import annotations

import click

from .commands import auth, history, market, portfolio


@click.group()
@click.version_option(version="0.1.0", prog_name="agent-rms")
def cli() -> None:
    """Agent-friendly RMS data CLI."""


cli.add_command(auth.auth)
cli.add_command(market.market)
cli.add_command(history.history)
cli.add_command(portfolio.portfolio)


if __name__ == "__main__":
    cli()
