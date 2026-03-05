# ── CV Render Pipeline ────────────────────────────────────────────────────────
# Usage:
#   make                          # render nb + en, private, casual
#   make nb                       # Norwegian private
#   make en-public                # English public (no personal data)
#   make all-public               # all public variants
#   make classic                  # all variants, classic theme
#   make CONFIG=config/foo.yaml   # arbitrary config hot-swap
#   make help                     # show this help

# ── Project layout ────────────────────────────────────────────────────────────

CV        := data/cv.yaml
TEMPLATES := templates
OUTPUT    := output
LOCALES   := data/locale
CONFIGS   := config
SCRIPT    := scripts/render.py
PYTHON    := uv run

# ── Defaults ─────────────────────────────────────────────────────────────────

CONFIG    ?= $(CONFIGS)/moderncv_casual.yaml
SCHEMA    ?= $(CONFIGS)/moderncv_schema.yaml

# ── Base render command ───────────────────────────────────────────────────────
# All path knowledge lives here. The script itself is path-agnostic.

define RENDER
	$(PYTHON) $(SCRIPT) \
		--cv $(CV) \
		--config $(1) \
		--schema $(SCHEMA) \
		--locale $(LOCALES)/$(2).yaml \
		--templates $(TEMPLATES) \
		--output $(OUTPUT) \
		--lang $(2) \
		--env-file .env \
		$(3)
endef

# ── Primary targets ───────────────────────────────────────────────────────────

.PHONY: all nb en nb-public en-public all-public tex-only \
        casual classic casual-public classic-public release clean help

## all: Render nb + en private builds (default)
all: nb en

## nb: Norwegian private build
nb:
	$(call RENDER,$(CONFIG),nb,)

## en: English private build
en:
	$(call RENDER,$(CONFIG),en,)

## nb-public: Norwegian public build (no personal data)
nb-public:
	$(call RENDER,$(CONFIG),nb,--public)

## en-public: English public build (no personal data)
en-public:
	$(call RENDER,$(CONFIG),en,--public)

## all-public: All public builds
all-public: nb-public en-public

## tex-only: Render .tex files only, skip PDF compilation
tex-only:
	$(call RENDER,$(CONFIG),nb,--no-compile)
	$(call RENDER,$(CONFIG),en,--no-compile)

# ── Theme shortcuts ───────────────────────────────────────────────────────────

## casual: All private builds with casual theme
casual:
	$(MAKE) all CONFIG=$(CONFIGS)/moderncv_casual.yaml

## classic: All private builds with classic theme
classic:
	$(MAKE) all CONFIG=$(CONFIGS)/moderncv_classic.yaml

## casual-public: All public builds with casual theme
casual-public:
	$(MAKE) all-public CONFIG=$(CONFIGS)/moderncv_casual.yaml

## classic-public: All public builds with classic theme
classic-public:
	$(MAKE) all-public CONFIG=$(CONFIGS)/moderncv_classic.yaml

# ── Release ───────────────────────────────────────────────────────────────────

## release: Build all public variants for deployment
release: all-public
	@echo "Release artifacts in $(OUTPUT)/"

# ── Housekeeping ──────────────────────────────────────────────────────────────

## clean: Remove all generated output
clean:
	rm -rf $(OUTPUT)


## help: Show available targets
help:
	@echo "Available targets:"
	@grep -E '^## ' Makefile | sed 's/## /  /'
