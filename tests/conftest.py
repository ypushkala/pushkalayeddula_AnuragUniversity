import pytest

from prativimb import config

needs_data = pytest.mark.skipif(not config.DB_PATH.exists(), reason="run `make data` first")
needs_models = pytest.mark.skipif(not (config.ARTIFACT_DIR / "glucose_models.joblib").exists(),
                                  reason="run `make train` first")
