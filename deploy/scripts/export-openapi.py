import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.api import create_app
from app.settings import Settings

schema = create_app(Settings(environment="development")).openapi()
schema.setdefault("components", {})["securitySchemes"] = {"session": {"type": "apiKey", "in": "cookie", "name": "vimag_session"}}
for path, methods in schema["paths"].items():
    public = path in {"/api/v1/health/live", "/api/v1/auth/setup", "/api/v1/auth/login"}
    for method, operation in methods.items():
        if not isinstance(operation, dict):
            continue
        if not public:
            operation["security"] = [{"session": []}]
        if method in {"post", "put"} and not public:
            operation.setdefault("parameters", []).extend([
                {"name": "X-CSRF-Token", "in": "header", "required": True, "schema": {"type": "string"}},
                {"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string", "minLength": 16, "maxLength": 128}},
                {"name": "Origin", "in": "header", "required": True, "schema": {"type": "string"}},
            ])
destination = Path(__file__).resolve().parents[2] / "docs/api-contract-v1.yaml"
destination.write_text(yaml.safe_dump(schema, sort_keys=False, allow_unicode=True), encoding="utf-8")
print("Generated OpenAPI contract")
