"""Every contract model must round-trip through dump/validate without loss."""

import pytest

from pcbpick.contracts.export_schema import MODELS
from tests.contracts.conftest import ALL_MODEL_FACTORIES


@pytest.mark.parametrize("model_cls", MODELS, ids=lambda m: m.__name__)
def test_round_trips_through_model_dump(model_cls: type) -> None:
    instance = ALL_MODEL_FACTORIES[model_cls.__name__]()

    restored = model_cls.model_validate(instance.model_dump())

    assert restored == instance


@pytest.mark.parametrize("model_cls", MODELS, ids=lambda m: m.__name__)
def test_round_trips_through_json(model_cls: type) -> None:
    instance = ALL_MODEL_FACTORIES[model_cls.__name__]()

    restored = model_cls.model_validate_json(instance.model_dump_json())

    assert restored == instance


def test_every_model_has_a_factory() -> None:
    model_names = {model.__name__ for model in MODELS}

    assert model_names == set(ALL_MODEL_FACTORIES)
