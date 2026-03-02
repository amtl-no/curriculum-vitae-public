# Min dynamiske CV-motor

![Yamllint status](https://github.com/amtl-no/curriculum-vitae/actions/workflows/lint-yaml.yaml/badge.svg)

## Struktur
- `data/`: Her bor `cv.yaml` (selve innholdet).
- `templates/`: LaTeX-maler med Jinja2-logikk.
- `scripts/`: Python-motoren (`uv` + `jinja2`).
- `.github/workflows/`: Automatiseringen som bygger PDFene.

## Kjør lokalt
Krev `uv` installert:
```bash
uv run scrips/render.py
```

## Lisens
Dette prosjektet er lisensiert under:
- **Kode (Python/YAML/actions):** [Apache-2.0.](LICENSE-Apache-2.0)
- **Innhold (CV-data/tekst):** [CC-BY-4.0](LICENSE-CC-BY-4.0)
