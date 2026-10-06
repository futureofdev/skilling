"""Installed metadata keeps optional storage drivers out of the core dependency set."""

import pytest

from .package_smoke import DEPENDENCIES, _metadata_dependencies

REQUIREMENTS = [
    "pydantic>=2.9",
    "pyyaml>=6.0",
    "typer>=0.15",
    "rich>=13.0",
    "tzdata",
    "psycopg-pool<3.4,>=3.3.3; extra == 'postgres'",
    'psycopg[binary]<3.4,>=3.3.6; extra == "postgres"',
    "boto3<1.44,>=1.43.107; extra == 's3'",
]


def test_storage_extras_are_validated_separately_from_core_dependencies() -> None:
    assert _metadata_dependencies(REQUIREMENTS, ["postgres", "s3"]) == DEPENDENCIES


@pytest.mark.parametrize(
    "replacement",
    [
        "boto3<1.44,>=1.43.107",
        "boto3; extra == 'unknown'",
        "boto3; python_version >= '3.11'",
        "boto3; extra == 's3' or python_version >= '3.11'",
        "unexpected-driver; extra == 's3'",
    ],
)
def test_storage_dependency_drift_refuses(replacement: str) -> None:
    with pytest.raises(AssertionError):
        _metadata_dependencies([*REQUIREMENTS[:-1], replacement], ["postgres", "s3"])


def test_missing_storage_driver_refuses() -> None:
    with pytest.raises(AssertionError):
        _metadata_dependencies(REQUIREMENTS[:-1], ["postgres", "s3"])
