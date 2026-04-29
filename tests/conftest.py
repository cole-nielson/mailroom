"""Shared test fixtures."""
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tenants_dir(repo_root) -> Path:
    return repo_root / "tenants"
