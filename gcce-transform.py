#!/usr/bin/env python3
"""GCCE deterministic transformer for UCloudAmp static site."""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import shutil
import sys
from pathlib import Path
from string import Template
from urllib.parse import urlparse

import yaml

SECTION_MARKER_PATTERN = re.compile(r"^<!-- §section:\s*([A-Z]+)\s*\|\s*id:\s*([a-z0-9-]+)\s*-->\s*$")
FRONTMATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
RAW_HTML_PATTERN = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

SUPPORTED_THEMES = {"dark"}


class BuildError(ValueError):
    """Raised when source content fails validation."""


def parse_frontmatter(document_text: str) -> tuple[dict, str]:
    match = FRONTMATTER_PATTERN.match(document_text)
    if not match:
        raise BuildError("Missing or malformed YAML frontmatter. Expected opening and closing --- lines.")

    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise BuildError(f"Malformed YAML frontmatter: {exc}") from exc

    if not isinstance(metadata, dict):
        raise BuildError("YAML frontmatter must be a mapping/object.")

    return metadata, document_text[match.end() :]


def parse_sections(body: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    buffer: list[str] = []

    for line_number, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.rstrip("\n")

        if "§section" in line:
            marker_match = SECTION_MARKER_PATTERN.match(line)
            if not marker_match:
                raise BuildError(
                    f"Malformed section delimiter at body line {line_number}: "
                    "expected '<!-- §section: TYPE | id: ID -->'."
                )

            if current:
                current["content"] = "\n".join(buffer).strip()
                sections.append(current)

            current = {"type": marker_match.group(1), "id": marker_match.group(2), "content": ""}
            buffer = []
            continue

        if current is None and line.strip():
            raise BuildError(
                f"Content found before first section marker at body line {line_number}. "
                "Add a section delimiter before body text."
            )

        if current is not None:
            buffer.append(line)

    if current:
        current["content"] = "\n".join(buffer).strip()
        sections.append(current)

    if not sections:
        raise BuildError("No sections found. Add delimiters like '<!-- §section: TYPE | id: ID -->'.")

    seen_ids: set[str] = set()
    for section in sections:
        section_id = section["id"]
        if section_id in seen_ids:
            raise BuildError(f"Duplicate section id '{section_id}' found. Section ids must be unique.")
        seen_ids.add(section_id)

    return sections


def ensure_safe_url(url: str, context: str) -> None:
    cleaned = url.strip()
    if not cleaned:
        raise BuildError(f"Empty URL is not allowed ({context}).")
    if cleaned.startswith("#"):
        return

    parsed = urlparse(cleaned)
    if parsed.scheme != "https" or not parsed.netloc:
        raise BuildError(f"Unsafe URL in {context}: '{cleaned}'. Only absolute https URLs are allowed.")


def validate_asset_reference(asset_path: str, repo_root: Path, context: str) -> Path:
    candidate = Path(asset_path)

    if candidate.is_absolute() or ".." in candidate.parts:
        raise BuildError(f"Asset path escapes assets directory in {context}: '{asset_path}'.")

    if not candidate.parts or candidate.parts[0] != "assets":
        raise BuildError(f"Asset path must start with 'assets/' in {context}: '{asset_path}'.")

    assets_root = (repo_root / "assets").resolve()
    resolved = (repo_root / candidate).resolve()

    if assets_root not in resolved.parents and resolved != assets_root:
        raise BuildError(f"Asset path escapes assets directory in {context}: '{asset_path}'.")

    if not resolved.is_file():
        raise BuildError(f"Referenced asset is missing in {context}: '{asset_path}'.")

    return resolved


def validate_master(metadata: dict, sections: list[dict[str, str]], repo_root: Path) -> None:
    required = [
        "site_title",
        "legal_name",
        "brand",
        "founder_name",
        "founder_title",
        "location",
        "domain",
        "theme",
        "tagline",
        "meta_description",
        "contact_url",
        "logo_path",
        "navigation",
    ]
    missing = [name for name in required if name not in metadata]
    if missing:
        raise BuildError(f"Missing required metadata fields: {', '.join(missing)}")

    if metadata["theme"] not in SUPPORTED_THEMES:
        raise BuildError(
            f"Invalid theme '{metadata['theme']}'. Supported themes: {', '.join(sorted(SUPPORTED_THEMES))}."
        )

    ensure_safe_url(str(metadata["contact_url"]), "metadata.contact_url")
    validate_asset_reference(str(metadata["logo_path"]), repo_root, "metadata.logo_path")

    navigation = metadata["navigation"]
    if not isinstance(navigation, list) or not navigation:
        raise BuildError("metadata.navigation must be a non-empty list of {label, id} items.")

    section_ids = {section["id"] for section in sections}
    nav_seen: set[str] = set()

    for idx, item in enumerate(navigation, start=1):
        if not isinstance(item, dict):
            raise BuildError(f"metadata.navigation item {idx} must be an object with 'label' and 'id'.")
        label = str(item.get("label", "")).strip()
        anchor_id = str(item.get("id", "")).strip()
        if not label or not anchor_id:
            raise BuildError(f"metadata.navigation item {idx} must include non-empty 'label' and 'id'.")
        if anchor_id in nav_seen:
            raise BuildError(f"Duplicate navigation anchor id '{anchor_id}' found.")
        nav_seen.add(anchor_id)
        if anchor_id not in section_ids:
            raise BuildError(f"Unresolved navigation anchor '#{anchor_id}' does not match any section id.")

    for section in sections:
        content = section["content"]
        if RAW_HTML_PATTERN.search(content):
            raise BuildError(
                f"Unsupported raw HTML found in section '{section['id']}'. "
                "Use Markdown/plain text instead."
            )
        for _, url in LINK_PATTERN.findall(content):
            cleaned = url.strip()
            if cleaned.startswith("assets/"):
                validate_asset_reference(cleaned, repo_root, f"section '{section['id']}'")
            elif cleaned.startswith("#"):
                anchor = cleaned[1:]
                if anchor not in section_ids:
                    raise BuildError(f"Unresolved anchor '{cleaned}' in section '{section['id']}'.")
            else:
                ensure_safe_url(cleaned, f"section '{section['id']}' link")


def render_inline(text: str) -> str:
    chunks: list[str] = []
    cursor = 0
    for match in LINK_PATTERN.finditer(text):
        chunks.append(html.escape(text[cursor : match.start()], quote=False))
        label = html.escape(match.group(1), quote=False)
        raw_href = match.group(2).strip()
        if raw_href.startswith("assets/"):
            # Local asset path validity is checked during validate_master.
            pass
        elif raw_href.startswith("#"):
            # Anchor validity is checked during validate_master.
            pass
        else:
            ensure_safe_url(raw_href, "rendered markdown link")
        href = html.escape(raw_href, quote=True)
        chunks.append(f'<a href="{href}">{label}</a>')
        cursor = match.end()
    chunks.append(html.escape(text[cursor:], quote=False))
    return "".join(chunks)


def render_markdown(content: str) -> str:
    lines = content.splitlines()
    rendered: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            rendered.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.strip()

        if not line:
            close_list()
            continue

        if line.startswith("### "):
            close_list()
            rendered.append(f"<h3>{render_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list()
            rendered.append(f"<h2>{render_inline(line[3:])}</h2>")
        elif line.startswith("- "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append(f"<li>{render_inline(line[2:])}</li>")
        else:
            close_list()
            rendered.append(f"<p>{render_inline(line)}</p>")

    close_list()
    return "\n".join(rendered)


def render_page(metadata: dict, sections: list[dict[str, str]], repo_root: Path) -> str:
    template_path = repo_root / "templates" / "base.html"
    if not template_path.is_file():
        raise BuildError(f"Template not found: {template_path}")

    nav_items = "\n".join(
        f'          <li><a href="#{html.escape(str(item["id"]), quote=True)}">'
        f'{html.escape(str(item["label"]), quote=True)}</a></li>'
        for item in metadata["navigation"]
    )

    sections_html = "\n".join(
        (
            f'      <section id="{html.escape(section["id"], quote=True)}" '
            f'class="section section-{html.escape(section["type"].lower(), quote=True)}">\n'
            f"{render_markdown(section['content'])}\n"
            "      </section>"
        )
        for section in sections
    )

    template = Template(template_path.read_text(encoding="utf-8"))
    substitutions = {
        "page_title": html.escape(str(metadata["site_title"]), quote=True),
        "meta_description": html.escape(str(metadata["meta_description"]), quote=True),
        "brand": html.escape(str(metadata["brand"]), quote=True),
        "tagline": html.escape(str(metadata["tagline"]), quote=True),
        "nav_items": nav_items,
        "sections_html": sections_html,
        "footer_text": html.escape(
            f"{metadata['legal_name']} · {metadata['location']} · Domain reference: {metadata['domain']}",
            quote=False,
        ),
    }
    try:
        return template.substitute(substitutions)
    except (KeyError, ValueError) as exc:
        raise BuildError(f"Template rendering failed: {exc}") from exc


def prepare_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.is_symlink():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def write_manifest(output_dir: Path) -> None:
    manifest_path = output_dir / "manifest-sha256.txt"
    records: list[tuple[str, str]] = []

    for file_path in sorted(output_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path == manifest_path:
            continue
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        records.append((digest, file_path.relative_to(output_dir).as_posix()))

    content = "\n".join(f"{digest}  {relative_path}" for digest, relative_path in records)
    if content:
        content += "\n"
    manifest_path.write_text(content, encoding="utf-8", newline="\n")


def build(source_path: Path, output_dir: Path) -> None:
    repo_root = source_path.parent.resolve()
    metadata, body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
    sections = parse_sections(body)
    validate_master(metadata, sections, repo_root)

    html_output = render_page(metadata, sections, repo_root)

    prepare_output_dir(output_dir)

    (output_dir / "index.html").write_text(html_output + "\n", encoding="utf-8", newline="\n")

    css_source = repo_root / "templates" / "style.css"
    if not css_source.is_file():
        raise BuildError(f"Stylesheet template missing: {css_source}")
    shutil.copyfile(css_source, output_dir / "style.css")

    assets_source = repo_root / "assets"
    if not assets_source.is_dir():
        raise BuildError(f"Assets directory missing: {assets_source}")
    shutil.copytree(assets_source, output_dir / "assets", dirs_exist_ok=True)

    static_config = repo_root / "staticwebapp.config.json"
    if not static_config.is_file():
        raise BuildError(f"Missing staticwebapp.config.json at {static_config}")
    shutil.copyfile(static_config, output_dir / "staticwebapp.config.json")

    write_manifest(output_dir)


def validate_only(source_path: Path) -> None:
    repo_root = source_path.parent.resolve()
    metadata, body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
    sections = parse_sections(body)
    validate_master(metadata, sections, repo_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic static site from master.md")
    parser.add_argument("--source", default="master.md", help="Path to source markdown with frontmatter")
    parser.add_argument("--dist", default="dist", help="Output directory for generated static files")
    parser.add_argument("--validate-only", action="store_true", help="Validate source and exit without writing dist")
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    output_dir = Path(args.dist).resolve()

    try:
        if args.validate_only:
            validate_only(source_path)
            print("Validation succeeded.")
        else:
            build(source_path, output_dir)
            print(f"Build succeeded: {output_dir}")
    except FileNotFoundError as exc:
        print(f"Build failed: missing file {exc.filename}", file=sys.stderr)
        return 1
    except BuildError as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
