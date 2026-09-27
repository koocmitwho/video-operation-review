# Model and image adaptation

Use an image-capable model with the host's image tools. Keep the user's chosen model and reasoning effort, and organize review around image clarity, context capacity, and available tools. See the [Chinese reference](models.md).

## Optimization references

The adaptation references checked on 2026-09-25 guide evidence presentation:

| Host | Reference | Evidence organization |
|---|---|---|
| Codex | GPT-6 Astra / Sol / Luna | Group evidence around the operation goal and before/after states; load commands as needed |
| DeepSeek Harness | DeepSeek-V4.1-Flash, API name `deepseek-flash` | Check both the route's image capabilities and the actual image dimensions sent to the model |

References: [OpenAI model catalog](https://developers.openai.com/api/docs/models), [GPT-6 skill guidance](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), [DeepSeek changelog](https://api-docs.deepseek.com/updates/), and [vision interface](https://api-docs.deepseek.com/guides/vision/).

## Check before starting

Record the current model/route, image tool, and local command tool. Open one evidence image from the current task and check readability. Check DeepSeek model aliases, route capabilities, and actual image results separately. Compatibility follows the available image-input and tool capabilities.

## Image presentation

Locate the object in a full image, then compare the before, editing, confirmation, and result states. Sheets support coarse review; final values, units, and checkbox states use individual originals or local crops. Include the evidence needed for the current question.

The inspected DSH `dsh-llm-deepseek` 0.1.5-rc.3 adapter has a default 640,000-pixel budget per image, configurable with `imagePixelBudget`. Record current results from actual dimensions, historical image state, and server usage. See the [adapter documentation](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/llm/llm-deepseek).

For a small number in a 1920×1080 frame, crop its parameter box while retaining the label, unit, and context. Locate the frame and region in the exported original first.

Run from any working directory; change `$skillRoot` for a different skill installation:

```powershell
$skillRoot = Join-Path $env:USERPROFILE '.agents\skills\video-operation-review'
$pythonExe = 'python'
$reviewCli = Join-Path $skillRoot 'scripts\review_video.py'
$ReviewWork = 'D:\video-reviews\tutorial'
& $pythonExe -X utf8 $reviewCli crop --work $ReviewWork --asset f000000024 --box 400,200,1000,600
```

Crops preserve source-frame identity. Use an `original` detail option when the host provides it, and choose readable local evidence regions.

## Context and resumption

- With smaller context, review one operation unit with its complete before/after relationship per batch, then save steps, questions, and frame references.
- Record the current object, change, confirmation/cancellation, evidence, and open questions. Store values awaiting identification as null and inspect relevant evidence.
- After compaction or resumption, read `status`, `intervals`, and `candidates --pending`, then reopen the evidence needed for the current step. Viewing counts deduplicate source frames.
- Use sequential execution or authorized collaboration as supported by the host. Register self-review and independent review with their respective states.

Script regressions check CLI and v1/v2/v3 database compatibility. Actual model trials are recorded in [validation.md](validation.md).
