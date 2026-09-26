# video-operation-review

[简体中文](README.md) | English

**A layered review skill for software screen recordings: reconstruct operations and preserve video frames.**

Designed for step-by-step software tutorials covering modeling, programming, data processing, and similar tasks. It helps AI assistants with vision capabilities identify menu paths, selected objects, final parameter values, confirmation or cancellation, file handoffs, and visible results, producing operation records that can be checked and refined.

For example, if a video shows someone entering `0.20`, cancelling, then entering `0.02` and applying it, the review should distinguish the temporary input from the final value. Questions remain open when a button is unclear or an execution result is not shown.

> The scripts handle video indexing, evidence management, and record checks. The AI assistant interprets the operations by actually viewing the images.

## Features

- **Complete frame indexing.** Process the video sequentially and record original source frame numbers, original PTS timestamps, exact image identities, and change cues. Supports variable frame rates and nonzero start times.
- **Layered viewing.** Prepare segments and representative images for the entire video, then inspect original images, crops, and before-and-after states for key operations. Waiting, mouse movement, and flicker can be grouped when there is supporting evidence, without requiring detailed review of every distinct pixel state by default.
- **Operation reconstruction.** Record menus, objects, parameters, confirmation or cancellation, inputs and outputs, and visible results. Distinguish temporary inputs, final values, and unknown information.
- **Gap checks and local expansion.** Check for overlaps, state discontinuities, and missing information. Sample merged or lower-priority intervals, and expand the relevant window when an anomaly is found.
- **Subtitles and existing transcripts.** Accept SRT, VTT, embedded text subtitles, and transcript JSON with an explicit time base. Preserve the original text, optional translations, sources, offsets, and overlap warnings.
- **Persistent review progress.** Store indexes, evidence, viewing records, steps, and open questions in SQLite. Resume after a pause and reuse existing results.

## Requirements

- Python 3.10 or later.
- NumPy and Pillow; see [requirements.txt](requirements.txt).
- Accessible FFmpeg and ffprobe executables. FFmpeg must support `-fps_mode passthrough`.
- The host assistant used for semantic review must be able to read files, run local commands, and actually view images.

**Text-only models are incompatible with this skill.** Both the model and the current host must support actual image input.

Validated on Windows with Python 3.10.11 and Python 3.12.10, using FFmpeg 8.1.2.

If you need to install the Python dependencies, use your own virtual environment:

```text
python -m pip install -r requirements.txt
```

## Getting started

### Install in Codex and DeepSeek Harness

Both hosts use the same skill and review records. By default, place the complete repository under `.agents/skills/video-operation-review` in your user directory.

Windows PowerShell:

```powershell
git clone https://github.com/koocmitwho/video-operation-review.git "$env:USERPROFILE\.agents\skills\video-operation-review"
```

macOS / Linux shell:

```bash
git clone https://github.com/koocmitwho/video-operation-review.git "$HOME/.agents/skills/video-operation-review"
```

If the target directory already exists, check its version and local changes first. Alternatively, download the ZIP and place the complete directory there; make sure `SKILL.md` is directly inside `video-operation-review`.

For use in one project only, place it at `<project-root>/.agents/skills/video-operation-review/`. If DeepSeek Harness uses a custom `DSH_AGENTS_HOME`, follow that configuration. For DSH-only use, `<DSH_HOME>/skills/video-operation-review/` is another option.

| Host | Invocation | Image requirements |
|---|---|---|
| Codex | Explicitly use `$video-operation-review`, or let task matching select it | A working image-viewing tool in the current environment, such as `view_image` |
| DeepSeek Harness | Request `video-operation-review`, loaded through the existing skill tool | `read_image`, an attachment service, and a current model that supports image input |

DeepSeek Harness must have local skill discovery and loading enabled. This repository is used as a filesystem skill. See [host adaptation](references/hosts.md) for directory and tool differences and troubleshooting; directory rules follow the [Codex documentation](https://learn.chatgpt.com/docs/build-skills) and [DeepSeek Harness documentation](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem).

### Check the environment first

Run from the repository root:

```text
python scripts/review_video.py doctor
```

The diagnostic checks the current Python, NumPy, Pillow, FFmpeg, and ffprobe, returning JSON. Exit code 0 means local processing dependencies passed; 1 means something is missing or unsuitable. It does not install software or create a review database. Diagnosis and `--help` remain available without NumPy or Pillow.

If the desktop host did not inherit your terminal's PATH, provide executable paths with `--ffmpeg` / `--ffprobe`, or set `VOR_FFMPEG` / `VOR_FFPROBE` in the same process environment. Explicit command arguments take precedence. When using a virtual environment, use the same Python interpreter to install dependencies, diagnose the environment, and run the scripts.

**Passing dependency checks does not establish model vision capability.** Mark text-only models as incompatible and stop the review. For image-capable models, describe the specific blocker, such as a missing tool or inaccessible file.

### New and older model compatibility

This update uses the GPT-6 family in Codex and DeepSeek-V4.1-Flash (`deepseek-flash`) in DeepSeek Harness as the basis for new-model optimizations: organize evidence around related operations, reduce repetitive descriptions, and inspect local crops when image resizing affects readability. The model references are the [OpenAI model catalog](https://developers.openai.com/api/docs/models) and [DeepSeek changelog](https://api-docs.deepseek.com/updates/).

Older models that retain image input and the necessary tool capabilities are also supported: reduce the operation scope of each batch when context is smaller, save progress between batches, and resume from those records. Use sequential execution when asynchronous or subagent tools are unavailable.

See [model adaptation](references/models.en.md) for model strategies, image clarity, and capability checks. Compatibility rules and actual validation results are recorded separately.

### Ask an AI assistant to review a recording

After downloading or cloning this repository, you can ask an assistant with access to the directory:

> Follow the video-operation-review workflow in this directory's `SKILL.md` to review this software tutorial. Check for existing results first, then perform complete indexing, a coarse review of the full timeline, and detailed review of key operations. Deliver reproducible steps, key evidence, and unresolved questions. Report computational coverage, review coverage, and the number of source frames actually viewed separately.

The skill entry point is [SKILL.md](SKILL.md). If it is not installed in a discovery directory, ask the assistant to read that file directly. When the host runs from another working directory, use the script's absolute path and specify the input video and `--work` locations explicitly.

### Prepare evidence from the command line

Run the following commands from the repository root, replacing the input with your own video. Use a dedicated review directory for that video with `--work`.

```text
python scripts/review_video.py --help
python scripts/review_video.py scan ./input/tutorial.mp4 --work ./work/tutorial
python scripts/review_video.py plan --work ./work/tutorial
python scripts/review_video.py candidates --work ./work/tutorial
python scripts/review_video.py extract --candidates --work ./work/tutorial
```

These commands create the index, propose segments, and export images. The host then opens the images, records the views, fills in operation records, and imports them. For complete examples and field definitions, see:

- [Command examples](references/examples.md)
- [Layered review and sampling](references/layered-review.md)
- [Steps, evidence, and statistics](references/records.md)

### Subtitles and transcripts

```text
python scripts/review_video.py tracks --work ./work/tutorial
python scripts/review_video.py subtitles ./input/narration.srt --work ./work/tutorial --language zh-en --offset 0
python scripts/review_video.py transcript ./input/speech.json --work ./work/tutorial
```

Subtitles are aligned to the original video timeline using “subtitle time + explicit offset.” Transcript JSON must declare its time base.

Input and alignment of subtitles and existing transcripts are supported. Speech recognition, OCR inference, and automatic translation have not yet been integrated. See [Language, audio, and subtitles](references/language.md) for module boundaries and planned work.

### Validate and export

```text
python scripts/review_video.py validate --work ./work/tutorial
python scripts/review_video.py audit --work ./work/tutorial --summary
python scripts/review_video.py export --work ./work/tutorial
```

Use `validate --require-coverage` to check the complete-review requirements for the current mode. Partial results can be exported when information is insufficient.

## Output

| File | Contents |
|---|---|
| `review.sqlite3` | Indexes, steps, evidence, viewing records, and review history |
| `layer-plan.json` | Segment proposals, representative images, and original state mappings |
| `review.json` | Structured steps, intervals, open questions, statistics, and audit information |
| `frames.jsonl` | Per-frame indexes and change metrics |
| `omission-audit.json` | Results of coverage, continuity, sampling, and review checks |
| `report.md` | Readable operation instructions, screenshots, and unresolved questions |
| `evidence/` | Original images, crops, and overview contact sheets exported as needed |

Input videos, review databases, and evidence may contain the user's own content. Keep them in their respective working directories.

## Understanding coverage statistics

The project records the following separately:

1. **Full-frame computational coverage:** which source frames the program has processed.
2. **Coarse review coverage:** which time intervals have an interpretation and representative evidence.
3. **Detailed review performed / completed:** which operations have had their key original images inspected, and which still have unresolved questions.
4. **Recorded visual views:** the number of distinct source frames registered after an image tool actually displayed them.

Original images, crops, enlarged views, and contact-sheet panels from the same source frame are deduplicated by source frame. Overview and original-resolution evidence are recorded at separate levels of detail.

Viewing records still need to be checked against actual tool calls. Passing an audit means the records meet the checking rules.

## Validation

On 2026-09-26, **all 98 script tests passed separately in both Windows environments, Python 3.10 and 3.12**. The suite preserves strict and layered workflows, host adaptation, and frame-count reporting fixes, and adds crop-region review, trace linkage, extraction of 600 sparse frames, end-of-budget completion, irregular timestamp alignment, legacy/current FFmpeg filter-file interfaces, and release-copy comparison. Once the dependencies are ready, run:

```text
python -X utf8 -m unittest discover -s scripts/tests -v
```

In one trial using a 32-frame synthetic tutorial, the layered workflow displayed 18 distinct source frames, compared with 32 in strict mode. Both recorded all 9 predefined visible-state checkpoints, with 0 errors in the final parameter value.

On 2026-09-25, skill loading was verified in both hosts on Windows, along with actual visual review using `deepseek-flash` in DeepSeek Harness. On another 32-frame synthetic recording, it completed full-frame indexing, image viewing, operation records, validation, and export. Its 55 successful image calls covered 32 original images, 22 crops, and one overview sheet; actual tool records were reconciled with evidence hashes. It correctly identified the cancelled value `0.73`, final value `0.04`, filename `measurements.csv`, and imported row count `13`. Record validation passed; missing click actions and file-identity evidence remain unresolved, and the full review gate did not pass. This is a historical visual trial; the 2026-09-26 optimization checks use synthetic tests. macOS has not been validated; see the corresponding commit's [CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml) for remote Windows/Linux results.

See [Validation notes](references/validation.md) and the [host adaptation summary](validation/host-adaptation.json) for detailed results and limitations.

Maintenance and acceptance criteria are documented in [Layered acceptance](references/layered-acceptance.md), [Processing methods](references/method.md), and [Development source and release checks](references/maintenance.md). Use `python scripts/check_release.py --target <release-directory>` for a read-only comparison; the new CI configuration must be assessed against actual results for the corresponding commit.
