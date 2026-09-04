---
name: bdrc-ocr
description: >
  藏文离线 OCR，基于 BDRC 开源模型（ONNX）对藏文图片或 PDF 做文字识别。
  支持现代印刷体、木刻版、手写乌梅体，按字体选用对应模型。
  当用户说「bdrc ocr」「藏文 ocr」「识别藏文」「ocr 这个藏文」「提取藏文文字」
  「/bdrc-ocr」，或给出藏文图片／扫描 PDF 要求提取文字时触发。
  完全本地离线运行，不联网、不调用任何云端 OCR。
  需先自行安装上游项目 buda-base/tibetan-ocr-app 并下载模型。
allowed-tools: Bash(bdrc-ocr.sh:*) Bash(python3:*) Bash(mkdir:*)
---

# BDRC 藏文离线 OCR

基于 [BDRC](https://www.bdrc.io) 的开源藏文 OCR 模型，完全本地运行。

## 先决条件

本技能是对上游项目 [`buda-base/tibetan-ocr-app`](https://github.com/buda-base/tibetan-ocr-app)（MIT）的调用封装，
**不附带模型，也不附带推理代码**。首次使用需要自行安装：

```bash
git clone https://github.com/buda-base/tibetan-ocr-app.git
cd tibetan-ocr-app
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export BDRC_OCR_HOME="$PWD"
```

模型另行下载，放到 `$BDRC_OCR_HOME/OCRModels/<模型名>/`，
每个模型目录里要有 `model_config.json`。模型见 BDRC 与 OpenPecha 的
Huggingface 账号（<https://huggingface.co/BDRC>）。

> **上游有一处已知 bug**：`cli.py` 里加载模型时用的是
> `import_local_model(os.path.dirname(model_dir))`，会跳到模型目录的**上一层**去加载。
> 若 `--model` 传的是含 `model_config.json` 的目录，需要改成
> `import_local_model(model_dir)` 才能正确加载。遇到模型加载失败先查这一处。

## 环境

```bash
OCR="${CLAUDE_PLUGIN_ROOT}/skills/bdrc-ocr/scripts/bdrc-ocr.sh"
PDF2IMG="${CLAUDE_PLUGIN_ROOT}/skills/bdrc-ocr/scripts/pdf_to_images.py"
export BDRC_OCR_HOME=/path/to/tibetan-ocr-app
```

## 流程

### 一、确认输入类型与字体

输入可以是单张图片（JPG / PNG / TIF）、一个图片目录、或 PDF。

字体决定用哪个模型：

| 字体 | 模型名 |
|---|---|
| 现代印刷 | `Modern` |
| 木刻版 | `Woodblock` |
| 木刻版（行与行重叠） | `Woodblock-Stacks` |
| 手写乌梅 Druma | `Ume_Druma` |
| 手写乌梅 Petsuk | `Ume_Petsuk` |

用自然的方式问用户，比如「这是现代印刷、木刻，还是手写乌梅？」。
若答「手写」或「乌梅」，再追问 Druma 还是 Petsuk。用户不确定时默认 `Modern`，覆盖面最广。

### 二、PDF 先转图片

```bash
python3 "$PDF2IMG" <pdf_path> [output_image_dir] [dpi]
```

默认输出到 PDF 同目录下的 `_ocr_images/`，DPI 默认 300，**木刻版建议 400**。
需要 `pdf2image`（依赖系统的 poppler）。

图片输入跳过这一步。

### 三、跑 OCR

```bash
# 单张
"$OCR" --model Modern --image <image_path> --output <output_dir> --dewarp --merge-lines

# 整个目录
"$OCR" --model Modern --folder <image_dir> --output <output_dir> --dewarp --merge-lines
```

`--dewarp` 做图像纠偏，`--merge-lines` 合并断行，两个都建议开。
要 Wylie 转写输出就加 `--encoding wylie`。

输出目录建议放在输入文件旁边的 `ocr_output/`。

**超过 20 张图时放后台跑**，完成后再通知用户。每张图约 15 秒。

### 四、给结果

报告处理了多少文件、输出在哪、有没有失败的；读第一个输出文件的前 20 行作为样例展示。

## 注意

- 输出是 `.txt` 纯文本（Unicode）
- `kenlm` 的警告无害，忽略
- Apple Silicon 上 ONNX CoreML 的警告属正常，忽略
- OCR 结果需要人工校对，尤其木刻版与手写体；交付前别把未校的 OCR 文本当定本
