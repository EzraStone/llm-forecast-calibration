.PHONY: preflight data pilot run parse test analyze figures all

preflight: ; python -m src.preflight
data:      ; python -m src.fetch_questions --out data/questions.jsonl
pilot:     ; python -m src.runner --conditions B --limit 20 --concurrency 10
run:       ; bash scripts/run_overnight.sh
parse:     ; python -m src.parse
test:      ; pytest -q
analyze:   ; python -m src.analyze
figures:   ; python -m src.figures
all: parse test analyze figures      # everything after this point is offline
