# video-operation-review

[简体中文](README.md) | English

**A layered review skill for software screen recordings: reconstruct operations and preserve video frames.**

Designed for step-by-step software tutorials covering modeling, programming, data processing, and similar tasks. It helps AI assistants with vision capabilities identify menu paths, selected objects, final parameter values, confirmation or cancellation, file handoffs, and visible results, producing operation records that can be checked and refined.

For example, if a video shows someone entering `0.20`, cancelling, then entering `0.02` and applying it, the review should distinguish the temporary input from the final value. Questions remain open when a button is unclear or an execution result is not shown.

> The scripts handle video indexing, evidence management, and record checks. The AI assistant interprets the operations by actually viewing the images.

## Features

- **Complete frame indexing.** Process the video sequentially and record original source frame numbers, original PTS timestamps, exact image identities, and change cues. Supports variable frame rates and nonzero start times.
- **Layered viewing.** Prepare segments and representative images for the entire video, then inspect original images, crops, and before-and-after states for key operations. Waiting, mouse movement, and flicker can be grouped when there is supporting evidence, with detail organized by operation unit.
- **Operation reconstruction.** Record menus, objects, parameters, confirmation or cancellation, inputs and outputs, and visible results. Distinguish temporary inputs, final values, and unknown information.
- **Gap checks and local expansion.** Check for overlaps, state discontinuities, and missing information. Sample merged or lower-priority intervals, and expand the relevant window when an anomaly is found.
- **Subtitles and existing transcripts.** Accept SRT, VTT, embedded text subtitles, and transcript JSON with an explicit time base. Preserve the original text, optional translations, sources, offsets, and overlap warnings.
- **Persistent review progress.** Store indexes, evidence, viewing records, steps, and open questions in SQLite. Resume after a pause and reuse existing results.

## Requirements

- Python 3.10 or later.
- NumPy and Pillow; see [requirements.txt](requirements.txt).
- Accessible FFmpeg and ffprobe executables. FFmpeg must support `-fps_mode passthrough`.
- The host assistant used for semantic review must be able to read files, run local commands, and actually view images.

Both the model and the current host need actual image input; a text-only model without image input cannot complete a review.

Validated on Windows with Python 3.10.11 and Python 3.12.10, using FFmpeg 8.1.2.
Current coverage is a single video stream with common 8-bit encodings; high bit depth, dynamic resolution, and other platform combinations are unverified.

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
| Codex | Explicitly use `$video-operation-review` | A working image-viewing tool in the current environment, such as `view_image` |
| DeepSeek Harness | Request `video-operation-review`, loaded through the existing skill tool | `read_image`, an attachment service, and a current model that supports image input |

DeepSeek Harness must have local skill discovery and loading enabled. This repository is used as a filesystem skill. See [host adaptation](references/hosts.md) for directory and tool differences and troubleshooting; directory rules follow the [Codex documentation](https://learn.chatgpt.com/docs/build-skills) and [DeepSeek Harness documentation](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/skill/skill-filesystem).

### Check the environment first

The agent running the skill handles this check. Run from the repository root; for an installed skill, use absolute paths as shown in [hosts.md](references/hosts.md):

```text
python scripts/review_video.py doctor
```

The diagnostic checks the current Python, NumPy, Pillow, FFmpeg, and ffprobe, returning JSON. Exit code 0 means local processing dependencies passed; 1 means something is missing or unsuitable. Diagnosis and `--help` run with the standard library.

If the desktop host did not inherit your terminal's PATH, provide executable paths with `--ffmpeg` / `--ffprobe`, or set `VOR_FFMPEG` / `VOR_FFPROBE` in the same process environment. Explicit command arguments take precedence. When using a virtual environment, use the same Python interpreter to install dependencies, diagnose the environment, and run the scripts.

After checking processing dependencies, open an exported evidence image to check the host image tool and model image-input path.

### New and older model compatibility

This update uses the GPT-6 family in Codex and DeepSeek-V4.1-Flash (`deepseek-flash`) in DeepSeek Harness as the basis for new-model optimizations: organize evidence around related operations, reduce repetitive descriptions, and inspect local crops when image resizing affects readability. The model references are the [OpenAI model catalog](https://developers.openai.com/api/docs/models) and [DeepSeek changelog](https://api-docs.deepseek.com/updates/).

Older models that retain image input and the necessary tool capabilities are also supported: reduce the operation scope of each batch when context is smaller, save progress between batches, and resume from those records. Use sequential execution when asynchronous or subagent tools are unavailable.

See [model adaptation](references/models.en.md) for model strategies, image clarity, and capability checks. Compatibility rules and actual validation results are recorded separately.

### Let your agent run the review

After installation, explicitly invoke the skill with an AI assistant that can access the video:

> Use `$video-operation-review` to review this software tutorial. Give me steps I can follow, final parameters for each object, key screenshots, and anything that still needs confirmation.

The skill entry point is [SKILL.md](SKILL.md). If it is not installed in a discovery directory, ask the assistant to read that file directly. The agent checks the environment, chooses a review directory, runs the scripts, actually views images, and records and exports the results. Users do not need to learn the commands or fill in JSON. Existing material, scope, and model choices are reused; provide a time or usage budget if you need one.

The agent first looks for an existing review directory. New work uses your chosen location, or `video-reviews/<video-name>/` under the current task's writable directory, and reports its actual path. Updates explain what has been checked and what comes next. When pausing, the agent provides the result location and a continuation note for another chat. Resuming retains existing records, although replaying the cached prefix can still take time.

The final explanation starts with reproducible steps, final parameters grouped by object and phase, key screenshots, and questions tied to their time positions; coverage statistics and records follow. See the [complete delivery example](examples/tutorial/report.md) and [progress, resumption, and delivery guidance](references/delivery.md) (both in Chinese).

### Prepare evidence from the command line

These commands are references for the agent and for debugging. Run them from the repository root with the current video, or use the script's absolute path from another directory. Use a dedicated review directory for that video with `--work`.

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

This skill does not perform speech recognition, OCR inference, or automatic translation: transcripts are produced by an external ASR adapter and imported as JSON, so audio without existing captions is not transcribed automatically. See [Language, audio, and subtitles](references/language.md) for interfaces and dependencies.

The agent states whether narration was used and identifies its source. When an audio track exists without a transcript, the report explicitly says that narration has not been transcribed.

### Validate and export

```text
python scripts/review_video.py validate --work ./work/tutorial
python scripts/review_video.py audit --work ./work/tutorial --summary
python scripts/review_video.py export --work ./work/tutorial
```

`valid` reports source, evidence-hash, and record integrity; `review_complete` reports candidate viewing and the current review gate. Default validate exits 0/1 according to valid; `--require-coverage` adds review completion to the exit condition. `--rehash-source` recomputes the source hash, and rehashed records this behavior. Export supports staged delivery with current status.

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
Each `--work` is written serially by one recorder; multiple reviewers produce their own records and import them by ID.

## Understanding coverage statistics

The project records the following separately:

1. **Full-frame computational coverage:** which source frames the program has processed.
2. **Coarse review coverage:** which time intervals have an interpretation and representative evidence.
3. **Detailed review performed / completed:** which operations have had their key original images inspected, and which still have unresolved questions.
4. **Recorded visual views:** the number of distinct source frames registered after an image tool actually displayed them.

Original images, crops, enlarged views, and contact-sheet panels from the same source frame are deduplicated by source frame. Overview and original-resolution evidence are recorded at separate levels of detail.

An audit checks record consistency and interval coverage; viewing records are self-reported and are not independent verification.

## Validation

On 2026-09-29, the agent execution instructions and report delivery were updated. Windows with Python 3.12.10 and 3.10.11 each ran 145 checks with no failures; each canonical-directory run skipped one Git-index check, which was covered by 15 documentation checks in the release checkout. The final issue-impact display fix also passed 12 report tests in both environments. Three agents reviewed 8-, 26-, and 38-second excerpts from one real recording: 1,368 computed frames, 138 actual image calls, and 128 displayed frames deduplicated by excerpt source identity. All three records passed integrity checks; six source or handoff questions remain, and the complete-review gates did not pass. See the [acceptance summary](validation/agent-delivery-20260929.json) and the [self-contained synthetic example](examples/tutorial/report.md).

After the 2026-09-27 fixes, **all 132 tests passed (34 added)** on Windows with Python 3.12.10 and 3.10.11, taking 93.525 and 135.805 seconds in separate serial runs. Logs: [Python 3.12](validation/tests-fixes-20260927.log), [Python 3.10](validation/tests-fixes-python310-20260927.log). `doctor` and the manual synthetic-GUI flow passed. See the [fix summary](validation/fixes-20260927.json).

For a 1080p, 120-frame fixture, median scan time across three pairs changed from 7.170 to 7.205 seconds, and Python peak working set from 82.92 to 83.28 MiB. Per-frame metric hashes matched. [Measurements](validation/performance-1080p-20260927.json).

On 2026-09-27, the clean 98-test baseline passed in a single Windows / Python 3.12.10 environment in 87.304 seconds. The [complete log](validation/tests-98.log) preserves the output.

On 2026-09-26, **all 98 script tests passed separately in both Windows environments, Python 3.10 and 3.12**. The suite preserves strict and layered workflows, host adaptation, and frame-count reporting fixes, and adds crop-region review, trace linkage, extraction of 600 sparse frames, end-of-budget completion, irregular timestamp alignment, legacy/current FFmpeg filter-file interfaces, and release-copy comparison. Once the dependencies are ready, run:

```text
python -X utf8 -m unittest discover -s scripts/tests -v
```

In one trial using a 32-frame synthetic tutorial, the layered workflow displayed 18 distinct source frames, compared with 32 in strict mode. Both recorded [all 9 predefined key states](validation/layered-trial-truth.json) (historical trial summary), with 0 errors in the final parameter value.

On 2026-09-25, skill loading was verified in both hosts on Windows, along with actual visual review using `deepseek-flash` in DeepSeek Harness. On another 32-frame synthetic recording, it completed full-frame indexing, image viewing, operation records, validation, and export. Its 55 successful image calls covered 32 original images, 22 crops, and one overview sheet; the author reconciled tool records with evidence hashes, and the receipts are not published with the repository. It correctly identified the cancelled value `0.73`, final value `0.04`, filename `measurements.csv`, and imported row count `13`. Record validation passed; missing click actions and file-identity evidence remain unresolved, and the full review gate did not pass. This is a historical visual trial; the 2026-09-26 optimization checks use synthetic tests. See the corresponding commit's [CI](https://github.com/koocmitwho/video-operation-review/actions/workflows/tests.yml) for remote Windows/Linux results.

Agent trials cover synthetic fixtures, a real short recording, and three excerpts from one real recording. In-application user reproduction and full-workflow throughput and memory for long recordings have not been measured; the performance figures above cover only 1080p / 120 frames.

See [Validation notes](references/validation.md) and the [host adaptation summary](validation/host-adaptation.json) for detailed results and measurement conditions.

Maintenance and acceptance criteria are documented in [Layered acceptance](references/layered-acceptance.md), [Processing methods](references/method.md), and [Development source and release checks](references/maintenance.md). Use `python scripts/check_release.py --target <release-directory>` for a read-only comparison; actual CI results are in the Actions runs for the corresponding commit.

License: [MIT](LICENSE).
