# Standard library
import os
import tempfile

# Third-party
import pytest


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d
