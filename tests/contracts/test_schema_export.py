"""The committed JSON Schema under `schema/v1/` must be valid and match regeneration.

This is a regression guard against someone hand-editing the schema or forgetting to
run the export step after a model change.
"""

import json

import jsonschema
import pytest

from pcbpick.contracts.export_schema import MODELS, export_all, schema_dir


def test_schema_dir_has_one_file_per_model() -> None:
    committed = {path.stem for path in schema_dir().glob("*.json")}

    assert committed == {model.__name__ for model in MODELS}


@pytest.mark.parametrize("model_cls", MODELS, ids=lambda m: m.__name__)
def test_committed_schema_is_valid_json_schema(model_cls: type) -> None:
    schema = json.loads((schema_dir() / f"{model_cls.__name__}.json").read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator.check_schema(schema)


def test_committed_schema_matches_regeneration(tmp_path) -> None:
    regenerated = export_all(target_dir=tmp_path)

    for name, path in regenerated.items():
        committed_text = (schema_dir() / f"{name}.json").read_text(encoding="utf-8")
        regenerated_text = path.read_text(encoding="utf-8")
        assert regenerated_text == committed_text, f"{name}.json is stale — rerun export_schema"
