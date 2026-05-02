# Third-Party Notices

Open_Notebook is MIT licensed. It references interfaces and workflow ideas from
the following materials, but it does not vendor their model weights or large
source trees. Third-party projects retain their own copyright and license terms.

## SenseNova-U1

- Source reference: `SenseNova-U1-main`
- Upstream project: <https://github.com/OpenSenseNova/SenseNova-U1>
- License observed locally: Apache License 2.0
- Usage in Open_Notebook: optional local driver interface, resolution buckets,
  and prompt-driving concepts. Users install/provide SenseNova-U1 separately.
- Default local checkout: `../SenseNova-U1-main`, outside this repository.

## SenseNova-Skills

- Source reference: `SenseNova-Skills-main`
- Upstream project: <https://github.com/OpenSenseNova/SenseNova-Skills>
- License observed locally: MIT
- Usage in Open_Notebook: workflow concepts for full-page PPT image generation,
  infographic prompt expansion, VLM review, and environment variable names.

## Clouds_Coder.py

- Source reference: local `Clouds_Coder.py` provided by the project owner.
- Usage in Open_Notebook: compatible LLM profile parsing and runtime selection
  behavior, reimplemented for this repository.

## Runtime Dependencies

Dependency licenses are managed by their respective projects. See
`pyproject.toml` and `frontend/package.json` for the package list.

## Model Weights and User Data

SenseNova-U1 weights downloaded to `models/Full`, local uploads, session
databases, prompts, plans, generated images, PDF files, and PPTX files are
runtime data. They are ignored by git and are not redistributed by this
repository.

For the full ownership boundary, see `OWNERSHIP_AND_LICENSE.md`.
