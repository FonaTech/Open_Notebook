# Ownership and License Statement

This statement defines the ownership boundary for the Open_Notebook repository.

## Repository Code

The application code, documentation, tests, launcher, and project-specific
workflow implementation in this repository are provided under the MIT License
in `LICENSE`.

Copyright ownership is attributed to Open_Notebook contributors unless a file
states otherwise.

## Referenced Third-Party Projects

Open_Notebook can interoperate with external SenseNova components, but those
components keep their own ownership and license terms.

- SenseNova-U1 source code belongs to its upstream authors and is governed by
  the upstream license published by that project.
- SenseNova-U1 model weights are not included in this repository. Users must
  download and use them according to the terms published with the model.
- SenseNova-Skills belongs to its upstream authors and is governed by its
  upstream license.
- Clouds_Coder.py was used as a local reference for compatible LLM profile
  behavior. Open_Notebook reimplements the configuration and routing behavior;
  it does not redistribute that file.

The default local SenseNova-U1 source checkout is outside this repository at
`../SenseNova-U1-main`. Open_Notebook may clone the upstream source there on
demand when the local U1 driver is used and the source tree is missing. That
external checkout is not part of this repository and is not covered by the
Open_Notebook MIT license.

## Model Weights

Model files, including `.safetensors`, `.bin`, checkpoints, tokenizer files,
and downloaded model repositories under `models/`, are runtime assets. They are
ignored by git and are not redistributed by Open_Notebook.

Users are responsible for reviewing and complying with the model card, license,
acceptable-use policy, and any access terms from the model provider before
downloading or using the model.

## User Data and Generated Outputs

Uploaded documents, uploaded images, local sessions, SQLite databases, prompts,
intermediate plans, generated images, PPTX exports, PDF exports, and runtime
artifacts under `data/` are user-controlled runtime data. They are not part of
the repository distribution.

Users are responsible for ensuring they have the rights to upload source
materials and to use, publish, or distribute generated outputs.

## API Keys and Credentials

API keys, tokens, private endpoints, and account-specific LLM configuration
must be stored locally through `.env` or the application settings database.
They must not be committed to git.

## Trademarks and Names

SenseNova, OpenSenseNova, Hugging Face, Ollama, and other names may be
trademarks or service marks of their respective owners. This project does not
claim ownership of those names.

## 中文声明

本仓库中的应用代码、文档、测试、启动器和 Open_Notebook 专属工作流实现采用
`LICENSE` 中的 MIT License 授权，除非单个文件另有说明，版权归
Open_Notebook contributors 所有。

SenseNova-U1 源码、SenseNova-U1 模型权重、SenseNova-Skills 以及相关上游
材料均保留其原始权利归属和许可条款。本仓库不会把这些上游项目的源码或模型
权重纳入 Open_Notebook 的 MIT 授权范围。

默认的 SenseNova-U1 源码目录是仓库外部的 `../SenseNova-U1-main`。当本地
U1 driver 需要源码且该目录缺失时，Open_Notebook 可以自动从上游 GitHub 仓库
克隆到该外部目录。该外部目录不是本仓库的一部分，也不应随本仓库提交。

`models/` 下的模型权重、`data/` 下的用户上传资料、会话数据库、生成图片、
PPTX/PDF 导出和其它运行时产物均属于用户本地运行数据，不作为本仓库内容发布。
用户需要自行确认上传资料、模型使用和生成内容发布符合相应权利和许可要求。
