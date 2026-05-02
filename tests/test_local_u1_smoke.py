from pathlib import Path

from open_notebook.core.image_driver import (
    DEFAULT_U1_SOURCE_ROOT,
    LocalU1ImageDriver,
    REPO_ROOT,
    resolve_local_u1_source,
    resolve_local_u1_source_root,
)


def test_local_u1_source_root_is_repo_relative_candidate():
    source_root = resolve_local_u1_source_root()
    assert not source_root.is_absolute() or source_root == source_root.resolve()
    assert DEFAULT_U1_SOURCE_ROOT == "../SenseNova-U1-main/src"


def test_local_u1_source_info_uses_external_default():
    info = resolve_local_u1_source()
    assert str(info["configured"]) == "../SenseNova-U1-main/src"
    assert str(info["source_root"]).endswith("SenseNova-U1-main/src")


def test_local_u1_smoke_metadata():
    model_path = Path("models/Full")
    if not model_path.exists():
        return
    assert (model_path / "config.json").exists()
    assert (model_path / "model.safetensors.index.json").exists()
    assert len(list(model_path.glob("*.safetensors"))) == 8
    source_root = resolve_local_u1_source_root()
    if (source_root / "sensenova_u1" / "__init__.py").exists():
        info = LocalU1ImageDriver(model_path=str(model_path)).smoke_check()
        assert info["config"] is True
