PYTHON ?= /usr/bin/python3
SWIFTC ?= /usr/bin/swiftc

SOURCE := scripts/codex_attention_overlay.swift
OVERLAY := scripts/codex-attention-overlay

.PHONY: build check clean

build: $(OVERLAY)

$(OVERLAY): $(SOURCE)
	$(SWIFTC) -O $(SOURCE) -o $(OVERLAY)

check: build
	$(PYTHON) -m py_compile scripts/notify.py
	$(PYTHON) scripts/notify.py --kind attention --message "Repository check" --session-id "repo-check" --dry-run

clean:
	rm -f $(OVERLAY)
	rm -rf scripts/__pycache__
