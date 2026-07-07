"""Unit tests for Phase 1 Pydantic schemas."""

import pytest
from app.schemas.architecture import Feature, FeatureSet, Priority, Layer


def test_feature_set_validation_success():
    """Test valid feature dependencies pass validation."""
    f1 = Feature(
        id="feat_1",
        name="Auth",
        description="User Login",
        user_story="As a user...",
        acceptance_criteria=["login works"],
        priority=Priority.P0,
        layer=Layer.BACKEND,
        depends_on=[],
    )
    f2 = Feature(
        id="feat_2",
        name="Dashboard",
        description="User Dashboard",
        user_story="As a user...",
        acceptance_criteria=["dashboard works"],
        priority=Priority.P1,
        layer=Layer.FRONTEND,
        depends_on=["feat_1"],
    )
    fs = FeatureSet(features=[f1, f2])
    fs.validate_dependency_ids()


def test_feature_set_validation_unknown_dependency():
    """Test invalid dependency ID raises ValueError."""
    f1 = Feature(
        id="feat_1",
        name="Dashboard",
        description="User Dashboard",
        user_story="As a user...",
        acceptance_criteria=["works"],
        priority=Priority.P1,
        layer=Layer.FRONTEND,
        depends_on=["feat_nonexistent"],
    )
    fs = FeatureSet(features=[f1])

    with pytest.raises(ValueError, match="depends on unknown features"):
        fs.validate_dependency_ids()
