import hashlib
import logging
import re
from logging import getLogger
from pathlib import Path

import sqlparse
import yaml
from black.trans import defaultdict
from jinja2 import Template
from sqlalchemy import Engine

from monotome import AppliedStatus, MigrationPage, Page
from monotome.graph import topological_sort
from monotome.tracking import (
    apply_migration_content,
    get_tracked_migrations,
)

logger = getLogger(__name__)
logging.basicConfig(level=logging.INFO)

FRONTMATTER_RE = re.compile(r"--+\s*(\w+)\s*:\s*(.+)")


def extract_frontmatter(f) -> dict:
    frontmatter = defaultdict(list)
    for line in f.splitlines():
        if not line.startswith("---"):
            break
        m = FRONTMATTER_RE.search(line)
        if m:
            key, value = m.groups()

            match key:
                case "requires":
                    frontmatter["requires"].append(value)

    return frontmatter


def extract_pages(
    document: dict, root: Path, stack_name: str
) -> list[MigrationPage]:
    pages = []
    root_folder = document.get("migrations_root", ".")
    root = (root / root_folder).resolve()
    for source in root.glob("**/*.sql"):
        feature = source.parent

        with source.open("r") as f:
            content = f.read()
            frontmatter = extract_frontmatter(content)
            requires = frontmatter.get("requires", [])

            page = MigrationPage(
                id=f"{feature.name}.{source.name}",
                feature=feature.name,
                stack=stack_name,
                full_path=source.resolve(),
                content=content,
                requires=requires,
                checksum=hashlib.sha256(content.encode()).hexdigest(),
            )
            pages.append(page)
    return pages


def get_migrations_info(root: Path) -> dict:
    document_name = root / "migrations.yaml"
    if not document_name.exists():
        raise FileNotFoundError(f"migrations.yaml not found in {root}")

    with document_name.open("r") as f:
        document = yaml.load(f, Loader=yaml.SafeLoader)
    if document is None:
        logger.info(f"Found empty migration in {root}")
    return document


def detect_migrations(
    root: Path,
    stack_name: str = "root",
    _depth: int = 0,
) -> list[MigrationPage]:
    migrations = []
    document = get_migrations_info(root=root)

    if document is not None:
        for sub in document.get("stacks", []):
            sub_name = sub["name"]
            sub_root = (root / sub["path"]).resolve()
            sub_migrations = detect_migrations(
                root=sub_root,
                stack_name=sub_name,
                _depth=_depth + 1,
            )
            excludes = sub.get("excludes", [])
            migrations.extend(
                [m for m in sub_migrations if m.id not in excludes]
            )

    migrations.extend(
        extract_pages(
            document=document or {},
            root=root,
            stack_name=stack_name,
        )
    )

    if not _depth:
        local_lookup = defaultdict(dict)
        lookup = defaultdict(list)

        for page in migrations:
            local_lookup[page.feature][page.full_path.name] = page

            lookup[page.feature].append(page)
            lookup[page.id].append(page)
            lookup[f"{page.stack}.{page.id}"].append(page)
            lookup[f"{page.stack}/{page.feature}"].append(page)

        for page in migrations:
            resolved_requirements = []
            for req in page.requires:
                candidate = local_lookup[page.feature].get(req)
                if candidate:
                    resolved_requirements.append(candidate.id)
                    continue
                candidate = lookup.get(req)
                if candidate:
                    resolved_requirements.extend([r.id for r in candidate])
                    continue
                raise ValueError(f"Unresolved requirement: {req}")
            page.requires = resolved_requirements
    return migrations


def get_all_migrations(root: Path) -> list[MigrationPage]:
    pages = detect_migrations(root=root)
    sorted_pages = topological_sort(pages=pages)
    return sorted_pages


def get_applied_migrations(engine: Engine) -> list[Page]:
    return get_tracked_migrations(engine=engine)


def get_status(root: Path, engine: Engine) -> list[MigrationPage]:
    pages = get_all_migrations(root=root)
    tracked = get_tracked_migrations(engine=engine)
    tracked_by_id = {t.id: t for t in tracked}
    for page in pages:
        if page.id in tracked_by_id:
            if page.checksum == tracked_by_id[page.id].checksum:
                page.status = AppliedStatus.applied
            else:
                page.status = AppliedStatus.conflict
    return topological_sort(pages=pages)


def apply_migrations(engine: Engine, pages: list[MigrationPage]):
    tracked = get_tracked_migrations(engine=engine)
    updated_pages = []
    with engine.connect() as conn:
        opts = engine.get_execution_options()
        target_schema = opts.get("schema_translate_map", {}).get(None, "public")
        for page in topological_sort(pages=pages):
            if page not in tracked:
                new_page = page.clone()
                if apply_migration_content(
                    conn=conn,
                    page=page,
                    target_schema=target_schema,
                ):
                    new_page.status = AppliedStatus.applied
                    conn.commit()
                else:
                    new_page.applied = False
                    conn.rollback()
                updated_pages.append(new_page)
            else:
                updated_pages.append(page)
    return pages


def upgrade(root: Path, engine: Engine):
    pages = get_all_migrations(root=root)
    apply_migrations(engine=engine, pages=pages)


def add_migration_to_stack(root: Path, migration_type: str, name: str):
    document = get_migrations_info(root=root)
    output_root = root / document.get("migrations_root", ".") / name

    if not output_root.exists():
        output_root.mkdir(parents=False)

    templates = (
        document.get("templates", {}).get(migration_type, {}).get("files", [])
    )

    for template in templates:
        output_file = output_root / template["name"]

        if output_file.exists() and output_file.read_text().strip():
            raise ValueError(
                f"File {output_file} already exists and is not empty"
            )

        with (output_root / template["name"]).open("w") as f:
            source = template.get("content", "")
            content = Template(source=source).render(name=name)
            pretty = sqlparse.format(
                content,
                reindent=True,
                keyword_case="upper",
                wrap_after=80,
                strip_comments=False,
            )
            f.write(pretty)
