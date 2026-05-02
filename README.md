# Open_Notebook

Open_Notebook is a SenseNova-powered workspace for full-canvas visual generation from
user requests and uploaded sources. It is inspired by NotebookLM-style source-grounded
workflows, but the default output mode relies on SenseNova's strength in complete image
composition and text layout.

## What It Builds

- **Auto**: the LLM classifies the user's intent and dispatches to the right workflow.
- **PPT**: the LLM plans a deck, SenseNova generates one full 16:9 image per slide, and
  Open_Notebook combines those images into both PPTX and PDF.
- **Poster**: sources are summarized into one high-density full-canvas poster prompt,
  then SenseNova generates a complete large poster image.
- **Research Figure**: creates complete architecture diagrams, mechanism diagrams,
  principle diagrams, graphical abstracts, or 3D-style research illustrations.
- **Image Edit**: analyzes the user's edit request and reference sources, then drives an
  image-editing prompt path.

The project stores sessions, uploads, jobs, prompts, plans, events, and artifacts
persistently in SQLite plus a local artifact directory.

## Repository Policy

This repository does not include SenseNova model weights, generated showcase images,
private API keys, or user uploads. Keep large weights such as `.safetensors` outside git.

The repository code is MIT licensed. External SenseNova source checkouts,
SenseNova model weights, user uploads, generated outputs, and provider API
accounts keep their own ownership and license terms.

See `NOTICE`, `OWNERSHIP_AND_LICENSE.md`, and `THIRD_PARTY_NOTICES.md` before
publishing or redistributing a fork.

## Quick Start

```bash
cd Open_Notebook
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Start the Web UI with Python only:

```bash
python start.py
```

Open <http://127.0.0.1:8017>.

Runtime does **not** require Node.js when `frontend/dist` is present. Node.js is
only needed if you want to modify and rebuild the frontend.

For real SenseNova image generation, set:

```ini
SN_IMAGE_GEN_API_KEY="..."
SN_IMAGE_GEN_BASE_URL="https://token.sensenova.cn/v1"
SN_IMAGE_GEN_MODEL="sensenova-u1-fast"
SN_CHAT_API_KEY="..."
SN_CHAT_BASE_URL="https://token.sensenova.cn/v1"
SN_CHAT_MODEL="sensenova-6.7-flash-lite"
```

For a no-key local smoke test:

```bash
python start.py --fake-image
```

Frontend development, optional:

```bash
cd frontend
npm install
npm run dev
```

## Build

```bash
cd frontend
npm run build
cd ..
python start.py
```

If `frontend/dist` exists, FastAPI serves it from `/`.

## LLM Configuration

The backend reimplements the Clouds_Coder-style LLM profile model:

- `profiles`, `model_profiles`, `llm_profiles`, or `llms`
- flat keys like `openai_url`, `openai_model`, `openai_key`
- providers: `openai_compat`, `siliconflow`, `vllm`, `lmstudio`, `anthropic`,
  `glm`, `kimi`, `openrouter`, `custom_http`, `ollama`
- active/default profile selection
- media/capability declarations

You can import or export this JSON from the GUI.

## Local SenseNova-U1

Local U1 inference is optional. For GitHub use, keep weights outside git and
point to them through `.env`. If `models/Full` contains a complete local U1
checkpoint, `python start.py` automatically selects the local U1 image backend.

The Web UI includes a SenseNova model panel with this download link:

<https://huggingface.co/sensenova/SenseNova-U1-8B-MoT>

Clicking download stores the model under the gitignored relative directory
`models/Full`.

The SenseNova-U1 source checkout is kept outside this repository. The default
relative path is `../SenseNova-U1-main/src`. If that directory is missing,
Open_Notebook can clone <https://github.com/OpenSenseNova/SenseNova-U1> into
`../SenseNova-U1-main` on demand when checking model status or using local U1.

Relative paths are resolved from the repository root:

```ini
OPEN_NOTEBOOK_IMAGE_BACKEND=local_u1
SENSENOVA_U1_MODEL_PATH=models/Full
SENSENOVA_U1_SOURCE_ROOT=../SenseNova-U1-main/src
SENSENOVA_U1_DEVICE=mps
```

You can also use absolute paths locally, but do not commit them. The external
SenseNova-U1 checkout and model weights are not covered by this repository's MIT
license; follow the upstream license and model terms.
For local U1 inference, follow the upstream SenseNova-U1 dependency guidance;
Python 3.11 is recommended for the model runtime even though the Web UI itself
can run on Python 3.10+.

Open_Notebook uses the official SenseNova-U1 transformers T2I defaults for
local generation:

```ini
SENSENOVA_U1_DTYPE=bfloat16
SENSENOVA_U1_NUM_STEPS=50
SENSENOVA_U1_CFG_SCALE=4.0
SENSENOVA_U1_CFG_NORM=none
SENSENOVA_U1_TIMESTEP_SHIFT=3.0
SENSENOVA_U1_CFG_INTERVAL=0.0,1.0
```

The upstream local runtime is validated around Python `>=3.11,<3.12`,
`torch==2.8.0`, and `transformers==4.57.1`. CUDA is the recommended backend.
macOS MPS is treated as experimental; if it produces flat, NaN, or patch-noise
images, Open_Notebook rejects the result instead of exporting it into a deck.

## Output Layout

Runtime files are under `data/` by default:

```text
data/
  open_notebook.sqlite3
  projects/<session_id>/
    sources/
    jobs/<job_id>/
      sources_digest.json
      plan.json
      prompts/
      images/
      exports/
```

`data/` is ignored by git.

## Development Checks

```bash
pytest
ruff check backend tests
```
