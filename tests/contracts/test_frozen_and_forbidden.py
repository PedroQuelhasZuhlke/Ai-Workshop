"""Every contract model is frozen and rejects fields it does not declare."""

import pytest
from pydantic import ValidationError

from pcbpick.contracts.export_schema import MODELS
from tests.contracts.conftest import ALL_MODEL_FACTORIES


@pytest.mark.parametrize("model_cls", MODELS, ids=lambda m: m.__name__)
def test_rejects_unknown_fields(model_cls: type) -> None:
    instance = ALL_MODEL_FACTORIES[model_cls.__name__]()
    payload = instance.model_dump()
    payload["__not_a_real_field__"] = "surprise"

    with pytest.raises(ValidationError):
        model_cls.model_validate(payload)


@pytest.mark.parametrize("model_cls", MODELS, ids=lambda m: m.__name__)
def test_is_frozen(model_cls: type) -> None:
    instance = ALL_MODEL_FACTORIES[model_cls.__name__]()
    field_name = next(iter(model_cls.model_fields))

    with pytest.raises(ValidationError):
        setattr(instance, field_name, getattr(instance, field_name))
