#!/usr/bin/env python3
#
# Copyright 2026 Arne Magnus Tveita Løken
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://apache.org
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Render CV pipeline.

All paths and configuration passed explicitly — no hardcoded project structure.

Usage:
    python scripts/render.py \
        --cv data/cv.yaml \
        --config config/moderncv_casual.yaml \
        --locale data/locale/nb.yaml \
        --templates templates \
        --output output \
        --lang nb

    python scripts/render.py ... --public
    python scripts/render.py ... --no-compile
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

# ── CLI ──────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the CV rendering pipeline."""
    parser = argparse.ArgumentParser(
        description="Render CV from YAML + Jinja2 template to PDF"
    )
    parser.add_argument(
        "--cv", type=Path, required=True, help="Path to cv.yaml"
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to typesetting config YAML",
    )
    parser.add_argument(
        "--locale", type=Path, required=True, help="Path to locale YAML"
    )
    parser.add_argument(
        "--templates",
        type=Path,
        required=True,
        help="Path to templates directory",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Path to output directory"
    )
    parser.add_argument(
        "--lang", required=True, help="Language code (e.g. nb, en)"
    )
    parser.add_argument(
        "--ignored-keys",
        nargs="*",
        default=["anchors", "meta"],
        help="Top-level cv.yaml keys to ignore (default: anchors meta)",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Public build — omit secret contact details",
    )
    parser.add_argument(
        "--no-compile",
        action="store_true",
        help="Render .tex only, skip PDF compilation",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Path to typesetting schema YAML (e.g. config/schema.yaml)",
    )
    parser.add_argument(
        "--letter",
        type=Path,
        default=None,
        help="Path to letter YAML (enables letter mode)"
    )
    return parser.parse_args()


# ── Loaders ──────────────────────────────────────────────────────────────────


def load_yaml(path: Path) -> dict:
    """Load and parse a YAML file from a given path."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(config_path: Path, schema_path: Path | None = None) -> dict:
    """Load configuration and optionally validate it against a schema."""
    cfg = load_yaml(config_path)
    cfg["_name"] = config_path.name

    # Validate and expand theme block against schema if provided
    theme = cfg.get("theme", {})
    if theme and schema_path:
        schema = load_yaml(schema_path)
        palettes = schema.get("palettes", {})
        styles = schema.get("styles", [])
        style = theme.get("style")
        color = theme.get("color")
        if style not in styles:
            raise ValueError(
                f"Unknown moderncv style: {style!r}. Valid: {sorted(styles)}"
            )
        if color not in palettes:
            raise ValueError(
                f"Unknown moderncv color: {color!r}. Valid: {sorted(palettes)}"
            )
        theme.update(palettes[color])

    # Interpolate {key} placeholders in pre_commands and commands wrt theme.
    # Regex substitution leaves LaTeX braces like {\footskip} untouched —
    # only exact matches against known theme keys are replaced.
    def interpolate(cmd: str) -> str:
        if not theme:
            return cmd
        pattern = r"\{(" + "|".join(re.escape(k) for k in theme) + r")\}"
        return re.sub(pattern, lambda m: theme[m.group(1)], cmd)

    cfg["pre_commands"] = [
        interpolate(cmd) for cmd in cfg.get("pre_commands", [])
    ]
    cfg["commands"] = [interpolate(cmd) for cmd in cfg.get("commands", [])]
    return cfg


def inject_secrets(cv: dict, public: bool) -> None:
    """
    Inject secrets from environment into contact fields.
    
    No-op on public builds.

    Env var conventions:
        email / phone        -> EMAIL, PHONE
        socials              -> SOCIAL_<PLATFORM>  (e.g. SOCIAL_SIGNAL)
        address sub-fields   -> ADDRESS_STREET, ADDRESS_CITY, ADDRESS_POSTCODE
    """
    if public:
        return
    contact = cv["contact"]

    # email and phone — {value, visible, secret}
    for field in ("email", "phone"):
        node = contact.get(field) or {}
        if isinstance(node, dict) and node.get("secret"):
            value = os.getenv(field.upper())
            if value:
                node["value"] = value

    # socials — {handle, visible, secret}
    for platform, node in (contact.get("socials") or {}).items():
        if isinstance(node, dict) and node.get("secret"):
            value = os.getenv(f"SOCIAL_{platform.upper()}")
            if value:
                node["handle"] = value

    # address sub-fields — {value, secret}
    addr = contact.get("address") or {}
    for field in ("street", "city", "postcode"):
        node = addr.get(field) or {}
        if isinstance(node, dict) and node.get("secret"):
            value = os.getenv(f"ADDRESS_{field.upper()}")
            if value:
                node["value"] = value


# ── Language resolution ──────────────────────────────────────────────────────


def make_resolver(lang_keys: set):
    """
    Return a recursive resolver function for the given set of language keys.
    
    Collapses {nb: ..., en: ...} dicts to the requested language.
    Leaves all other structures intact — inc. {value, secret, visible} nodes.
    """

    def resolve_lang(node, lang: str):
        if isinstance(node, dict):
            if node.keys() <= lang_keys and lang in node:
                return node[lang]
            return {k: resolve_lang(v, lang) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve_lang(i, lang) for i in node]
        return node

    return resolve_lang


# ── Contact helpers ──────────────────────────────────────────────────────────


def build_moderncv_name(name: dict) -> tuple[str, str]:
    """
    Build moderncv firstname / familyname from structured name dict.
    
    Combines given + middle (if present) into firstname, family to familyname.
    """
    given = name.get("given", "")
    middle = name.get("middle")
    family = name.get("family", "")
    firstname = f"{given} {middle}".strip() if middle else given
    return firstname, family


# ── Union display ────────────────────────────────────────────────────────────


def build_union_displays(raw: dict, lang_keys: set) -> None:
    """
    Construct union_display strings for extracurricular entries.
    
    The entries must have a union field.
    Must run before resolve_lang.
    """
    for entry in raw.get("extracurricular", []):
        if "union" not in entry:
            continue
        displays = {}
        for lang in lang_keys:
            union_short = entry["union"]["short"].get(lang, "")
            org_short = entry["organisation"]["short"].get(lang, "")
            if lang == "nb":
                displays[lang] = f"{union_short}-foreningen ved {org_short}"
            else:
                displays[lang] = f"{union_short} branch at {org_short}"
        entry["union_display"] = displays


# ── Jinja2 filters ───────────────────────────────────────────────────────────


def make_format_date(locale: dict):
    """
    Return a Jinja2 filter for date formatting.
    
    Handles structured dicts {year, month, day}, date objects, and ISO strings.
    Driven entirely by locale data.
    """

    def format_date(value) -> str:
        if isinstance(value, dict):
            year = value.get("year") or 0
            month = value.get("month") or 1
            day = value.get("day") or 1
        elif isinstance(value, date):
            year, month, day = value.year, value.month, value.day
        elif isinstance(value, str):
            parts = value.split("-")
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            day = int(parts[2]) if len(parts) > 2 else 1
        else:
            return str(value)
        month_name = locale["months"][month]
        return locale["date_format"].format(
            day=day, month=month_name, year=year
        )

    return format_date


def make_render_package(lang: str):
    """
    Return a Jinja2 filter for rendering LaTeX usepackage commands.
    
    Handles plain strings, option lists, key=value mappings, and babel.
    """

    def render_package(pkg) -> str:
        if isinstance(pkg, str):
            return f"\\usepackage{{{pkg}}}"
        name = pkg["name"]
        if "options" not in pkg:
            return f"\\usepackage{{{name}}}"
        opts = pkg["options"]
        if isinstance(opts, dict) and opts.get("lang"):
            locale_str = "norsk" if lang == "nb" else "english"
            return f"\\usepackage[{locale_str}]{{{name}}}"
        if isinstance(opts, dict):
            opt_str = ",".join(f"{k}={v}" for k, v in opts.items())
            return f"\\usepackage[{opt_str}]{{{name}}}"
        if isinstance(opts, list):
            opt_str = ",".join(str(o) for o in opts)
            return f"\\usepackage[{opt_str}]{{{name}}}"
        return f"\\usepackage{{{name}}}"

    return render_package


def latex_escape(value: str) -> str:
    """Escape special LaTeX characters in user-supplied strings."""
    if not isinstance(value, str):
        return value
    for char, escaped in [
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]:
        value = value.replace(char, escaped)
    return value


def make_period_str(locale: dict):
    """
    Return a Jinja2 filter that formats a date range as a period string.
    
    start and end are structured dicts {year, month} or None for open end.
    """

    def fmt(d: dict) -> str:
        if not d:
            return ""
        year = d.get("year") or ""
        month = d.get("month")
        return f"{month:02d}/{year}" if month else str(year)

    def period_str(start, end) -> str:
        start_str = fmt(start)
        if end is None:
            end_str = locale["present"]
        else:
            if (
                start
                and end
                and start.get("year") == end.get("year")
                and not start.get("month")
                and not end.get("month")
            ):
                return str(start.get("year", ""))
            end_str = fmt(end)
        return f"{start_str} -- {end_str}"

    return period_str


# ── Rendering ────────────────────────────────────────────────────────────────


def build_jinja_env(templates_dir: Path) -> Environment:
    """
    Initialize the Jinja2 environment.

    Uses the specified templates directory.
    """
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        block_start_string="((*",
        block_end_string="*))",
        variable_start_string="(((",
        variable_end_string=")))",
        comment_start_string="((#",
        comment_end_string="#))",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render(
    cv: dict, cfg: dict, locale: dict, lang: str, templates_dir: Path
) -> str:
    """Render the CV data into a LaTeX string using Jinja2."""
    env = build_jinja_env(templates_dir)
    env.filters["format_date"] = make_format_date(locale)
    env.filters["render_package"] = make_render_package(lang)
    env.filters["period_str"] = make_period_str(locale)
    env.filters["latex_escape"] = latex_escape
    template = env.get_template(cfg["template"])
    return template.render(
        cv=cv, cfg=cfg, locale=locale, lang=lang, cfg_name=cfg["_name"]
    )

def render_letter(
    cv: dict,
    letter: dict,
    cfg: dict,
    locale: dict,
    lang: str,
    templates_dir: Path,
) -> str:
    """Render a letter from CV and letter data into a LaTeX string."""
    env = build_jinja_env(templates_dir)
    env.filters["format_date"] = make_format_date(locale)
    env.filters["render_package"] = make_render_package(lang)
    env.filters["period_str"] = make_period_str(locale)
    env.filters["latex_escape"] = latex_escape
    template = env.get_template("moderncv/letter.tex.j2")
    return template.render(
        cv=cv,
        letter=letter,
        cfg=cfg,
        locale=locale,
        lang=lang,
        cfg_name=cfg["_name"],
        today=date.today(),
    )


# ── Compilation ──────────────────────────────────────────────────────────────


def write_xmpdata(tex_path: Path, xmp: dict) -> None:
    """
    Write a .xmpdata file alongside the .tex file for pdfx PDF/A compliance.
    
    Receives a flat dict — all structure-awareness lives in the caller.
    """
    lines = [
        f"\\Title{{{xmp['title']}}}",
        f"\\Author{{{xmp['author']}}}",
        f"\\Language{{{xmp['lang_tag']}}}",
        f"\\Subject{{{xmp['title']}}}",
        f"\\Keywords{{{xmp['keywords']}}}",
        f"\\Publisher{{{xmp['author']}}}",
    ]
    tex_path.with_suffix(".xmpdata").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def compile_pdf(tex_path: Path) -> None:
    """Compile a LaTeX file to PDF using latexmk."""
    result = subprocess.run(
        ["latexmk", "-lualatex", "-interaction=nonstopmode", tex_path.name],
        cwd=tex_path.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("── LaTeX stdout ──────────────────────────────")
        print(result.stdout[-3000:])
        print("── LaTeX stderr ──────────────────────────────")
        print(result.stderr)
        sys.exit(1)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    """Execute the main entry point for the CV rendering pipeline."""
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    ignored_keys = set(args.ignored_keys)

    # Load .env from explicit path if provided, or search upward from cwd
    load_dotenv(args.env_file)

    raw = load_yaml(args.cv)
    lang_keys = set(raw.get("meta", {}).get("languages", [args.lang]))

    build_union_displays(raw, lang_keys)

    cv = {k: v for k, v in raw.items() if k not in ignored_keys}

    inject_secrets(cv, args.public)

    firstname, familyname = build_moderncv_name(cv["contact"]["name"])
    cv["contact"]["firstname"] = firstname
    cv["contact"]["familyname"] = familyname

    resolve_lang = make_resolver(lang_keys)
    cv = resolve_lang(cv, args.lang)

    cfg = load_config(args.config, schema_path=args.schema)
    locale = load_yaml(args.locale)

    if args.letter:
        raw_letter = load_yaml(args.letter)
        letter_lang_keys = {"nb", "en"}
        letter_resolver = make_resolver(letter_lang_keys)
        letter = letter_resolver(raw_letter, args.lang)

        tex_source = render_letter(
            cv, letter, cfg, locale, args.lang, args.templates
        )
        letter_id = raw_letter["meta"]["id"]
        visibility = "public" if args.public else "private"
        stem = f"letter_{letter_id}_{args.lang}_{visibility}"
    else:
        # ── CV mode ───────────────────────────────────────────────────
        tex_source = render(cv, cfg, locale, args.lang, args.templates)
        config_stem = args.config.stem
        visibility = "public" if args.public else "private"
        stem = f"cv_{args.lang}_{visibility}_{config_stem}"

    tex_path = args.output / f"{stem}.tex"
    tex_path.write_text(tex_source, encoding="utf-8")
    author = raw["meta"]["author"]
    xmp_meta = raw["meta"]["xmp"]
    xmp = {
        "title": xmp_meta["title"][args.lang].format(author=author),
        "author": author,
        "lang_tag": xmp_meta["lang_tag"][args.lang],
        "keywords": xmp_meta["keywords"][args.lang],
    }
    write_xmpdata(tex_path, xmp)

    print(f"Rendered  -> {tex_path}")

    # Copy assets to output so relative paths in .tex resolve correctly
    assets_src = args.cv.parent.parent / "assets"
    if assets_src.is_dir():
        assets_dst = args.output / "assets"
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)

    if not args.no_compile:
        compile_pdf(tex_path)
        print(f"Compiled  -> {tex_path.with_suffix('.pdf')}")
    else:
        print("Skipped PDF compilation (--no-compile)")


if __name__ == "__main__":
    main()
