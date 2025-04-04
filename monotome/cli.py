import os
from pathlib import Path

import click
from prettytable import HRuleStyle, PrettyTable
from sqlalchemy import create_engine, Engine
from sqlalchemy.exc import ProgrammingError

from monotome import AppliedStatus, MigrationPage, migrations
from monotome.migrations import write_lockfile, assert_lockfile_consistency

cwd = os.getcwd()

STATUS_STYLE = {
    AppliedStatus.applied: click.style("Applied", fg="green"),
    AppliedStatus.unapplied: click.style("Unapplied", fg="yellow"),
    AppliedStatus.conflict: click.style("Conflict", fg="red"),
}


def get_engine_from_url(
    url: str,
    echo: bool = False,
    schema_name: str = "public",
) -> Engine:
    engine = create_engine(url=url, echo=echo)

    return engine.execution_options(
        schema_translate_map={
            None: schema_name,
        }
    )


def print_pages(pages: list[MigrationPage], show_applied: bool, title: str):
    field_names = ["Order", "Stack", "Feature", "ID", "Requires", "Checksum"]

    if show_applied:
        field_names.append("Status")

    table = PrettyTable(
        field_names=field_names,
        title=title,
        hrules=HRuleStyle.ALL,
        align="l",
    )

    for idx, page in enumerate(pages, start=1):
        row = [
            idx,
            page.stack,
            page.feature,
            page.id,
            "\n".join([f"- {r}" for r in page.requires]),
            page.checksum[:6],
        ]

        if show_applied:
            row.append(STATUS_STYLE[page.status])

        table.add_row(row)

    click.echo(table)


@click.group()
def main():
    pass


@main.command()
@click.argument("url")
@click.argument("root", default=cwd)
@click.option("--debug", default=False, is_flag=True)
@click.option("--schema", default="public")
def status(url: str, root: str, debug: bool, schema: str):  # noqa
    engine = get_engine_from_url(url=url, echo=debug, schema_name=schema)
    try:
        pages = migrations.get_status(engine=engine, root=Path(root))
        print_pages(pages=pages, show_applied=True, title="Status")
    except Exception as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        if debug:
            raise


@main.command()
@click.argument("url")
@click.argument("root", default=cwd)
@click.option("--debug", default=False, is_flag=True)
@click.option("--schema", default="public")
def apply(url: str, root: str, debug: bool, schema: str):  # noqa
    engine = get_engine_from_url(url=url, echo=debug, schema_name=schema)
    try:
        pages = migrations.get_status(engine=engine, root=Path(root))
        print_pages(
            pages=pages,
            show_applied=True,
            title="Current Status",
        )
        updated_pages = migrations.apply_migrations(engine=engine, pages=pages)
        print_pages(
            pages=updated_pages,
            show_applied=True,
            title="After Migration",
        )
        # confirm = click.prompt(
        #     text="Apply migrations?",
        #     type=click.Choice(["yes", "no"]),
        # )
        # if confirm == "yes":
        #     migrations.apply_migrations(url=url, pages=pages)

    except ProgrammingError as e:
        msg = f"An error occured while processing {e.page.id}"
        click.echo(click.style(msg, fg="red", bold=True), err=True)
        click.echo(click.style(str(e), fg="red"), err=True)
    except Exception as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        if debug:
            raise


@main.command()
@click.argument("type")
@click.argument("root")
@click.argument("name")
@click.option("--debug", default=False, is_flag=True)
def add(type: str, root: str, name: str, debug: bool):  # noqa
    try:
        migrations.add_migration_to_stack(
            root=Path(root),
            migration_type=type,
            name=name,
        )
    except Exception as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        if debug:
            raise


@main.command()
@click.argument("root", default=cwd)
@click.option("--debug", default=False, is_flag=True)
def lock(root: str, debug: bool):  # noqa
    try:
        path = Path(root)
        pages = migrations.detect_migrations(root=path)
        write_lockfile(path=path, pages=pages)
    except Exception as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        if debug:
            raise


@main.command()
@click.argument("root", default=cwd)
@click.option("--debug", default=False, is_flag=True)
def check(root: str, debug: bool):  # noqa
    try:
        path = Path(root)
        pages = migrations.detect_migrations(root=path)
        assert_lockfile_consistency(root=path, pages=pages)
    except Exception as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        if debug:
            raise


if __name__ == "__main__":
    main()
