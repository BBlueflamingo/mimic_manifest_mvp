# MIMIC Manifest MVP

Standalone Python MVP for building a patient-safe 10k subset from MIMIC-CXR-JPG + Chest ImaGenome + MS-CXR.

This version now supports two outputs at once:

- manifest files for training
- a physically copied subset of the selected images and txt reports

## Project Layout

```text
mimic_manifest_mvp/
  README.md
  pyproject.toml
  configs/
    config.yaml
  data/
    __init__.py
    build_manifest.py
    config.py
    io_utils.py
    report_utils.py
    sampling.py
    stats.py
  scripts/
    __init__.py
    compute_stats.py
  tests/
    conftest.py
    test_manifest.py
```

## Main Command

Run from inside `mimic_manifest_mvp/`:

```bash
python -m data.build_manifest --config configs/config.yaml
```

## Optional Stats Recompute

```bash
python -m scripts.compute_stats --manifest outputs/mimic_manifest_mvp/usable_samples.csv --output outputs/mimic_manifest_mvp/stats.json
```

## Outputs

- `usable_samples.csv`
- `usable_samples.jsonl`
- `claims_gold.jsonl`
- `stats.json`
- `subject_splits/train_subjects.txt`
- `subject_splits/val_subjects.txt`
- `subject_splits/test_subjects.txt`
- `copied_subset/train/images/...`
- `copied_subset/train/reports/...`
- `copied_subset/val/images/...`
- `copied_subset/val/reports/...`
- `copied_subset/test/images/...`
- `copied_subset/test/reports/...`

If `asset_copy.enabled = true`, the builder copies the final selected image files and txt report files into `asset_copy.output_dir`, organized by split.

## Expected Files And Columns

`configs/config.yaml` is intentionally JSON-compatible YAML so the project can run without requiring PyYAML.

Required config paths:

- `io.metadata_csv`
- `io.mimic_jpg_root`
- `io.reports`
- `io.chest_imagenome_annotations.path`
- `io.mscxr_annotations.path`

Required metadata columns:

- `subject_id`
- `study_id`
- `dicom_id`
- `ViewPosition`

Required annotation columns:

- Chest ImaGenome file must expose the configured `dicom_id_column`
- MS-CXR file must expose the configured `dicom_id_column`

For Chest ImaGenome scene graph directories, use:

```json
"chest_imagenome_annotations": {
  "path": "D:/research/dataset/scene_graph/scene_graph",
  "format": "scene_graph_dir",
  "dicom_id_column": "image_id"
}
```

In that format, each `*_SceneGraph.json` is scanned and the top-level `image_id` is treated as the MIMIC-CXR `dicom_id`.

If `io.reports.mode = "csv"`, the report CSV must expose:

- the configured `study_id_column`
- the configured `findings_column`
- the configured `impression_column`

If `io.reports.mode = "directory"`, the report directory must contain files matching:

- `io.reports.root / io.reports.path_template`

The builder fails fast with clear error messages when a required path is missing or when configured columns cannot be found.
