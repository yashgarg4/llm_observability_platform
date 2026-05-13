.PHONY: sdk-install server ui demo test

SDK_DIR    := meridian-sdk
SERVER_DIR := meridian-server
UI_DIR     := meridian-ui

sdk-install:
	pip install -e $(SDK_DIR)/

server:
	cd $(SERVER_DIR) && DB_PATH=./meridian.db .venv/Scripts/python -m uvicorn server.main:app \
		--host 0.0.0.0 --port 8001 --reload

ui:
	cd $(UI_DIR) && npm run dev

demo:
	@echo "Starting server..."
	cd $(SERVER_DIR) && DB_PATH=./meridian.db .venv/Scripts/python -m uvicorn server.main:app \
		--host 0.0.0.0 --port 8001 &
	@echo "Starting UI..."
	cd $(UI_DIR) && npm run dev &
	@sleep 3
	@echo "Running demo..."
	cd $(SDK_DIR) && OTLP_ENDPOINT=http://localhost:8001/v1/traces \
		.venv/Scripts/python scripts/demo_instrument_mock.py

test:
	cd $(SDK_DIR)    && .venv/Scripts/pytest tests/ -v
	cd $(SERVER_DIR) && .venv/Scripts/pytest tests/ -v
