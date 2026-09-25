# New-model optimization and backward compatibility

This skill requires a model that supports image input and a host that can actually display evidence to it. **Text-only models are incompatible: state this explicitly and stop the review, without a text-only fallback.** Compatibility depends on actual capabilities.

## Current optimization references

The following capabilities were checked on 2026-09-25 to guide evidence presentation.

| Host | New-model reference | Implications for this skill |
|---|---|---|
| Codex | GPT-6 Astra and the same-generation GPT-6 Sol / Luna | Guide review with clear goals, evidence constraints, and the current operation context; load detailed commands as needed, avoiding mandatory lengthy descriptions for every image or mechanical agent splitting |
| DeepSeek Harness | DeepSeek-V4.1-Flash, official API name `deepseek-flash` | Use native vision to check operations; also check the image capability declared by Harness and the actual image dimensions sent to the model |

For OpenAI model information and skill guidance, see the [model catalog](https://developers.openai.com/api/docs/models) and [GPT-6 skill and prompting guidance](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra). For DeepSeek versions and image input, see the [changelog](https://api-docs.deepseek.com/updates/) and [vision interface](https://api-docs.deepseek.com/guides/vision/).

## Check capabilities before starting

Identify the current model/route, available image tool, and local command tool. Record verifiable values and leave unknowns unknown. Stop if the model is known to be text-only. Once the model declares image support, actually open one evidence image from the current task and confirm that its contents are visible. An attachment ID, text placeholder, or file path alone does not satisfy this check.

DeepSeek model aliases and the host capability catalog are separate layers. An official older name may route to a newer model while an older Harness catalog still declares it text-only; a custom new ID may also lack an image-capability declaration. Use the current route's capabilities and actual image results. Do not infer compatibility just because the name contains `vision`, `v4`, or “latest.”

## Prioritize image clarity over fitting more frames into one request

First use full-screen images from the same operation interval to locate the object, then compare the necessary before, editing, confirmation, and result states. Sheets support coarse review; verify final values, units, checkbox states, and temporary-versus-final differences using individual images or local crops. Include only the evidence needed to answer the current question.

Even when the model supports high-resolution images, the host may resize them first. The inspected DSH `dsh-llm-deepseek` 0.1.5-rc.3 adapter defaults to a 640,000-pixel budget per image, configurable through `imagePixelBudget`. This is an adapter default, not a permanent limit of the DeepSeek model. It may also replace older images with placeholders. Public API image accounting may be newer than the local adapter. Record facts from returned dimensions, placeholders, and server-reported usage. See the [adapter documentation](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/llm/llm-deepseek).

When a number is too small in a 1920×1080 screen recording, crop its parameter box from existing evidence, retaining the field label, unit, and necessary context, then view the crop through the host image tool. For example:

```text
python scripts/review_video.py crop --work ./work/tutorial --asset f000000024 --box 400,200,1000,600
```

The frame number and coordinates above are examples; locate the actual region in an exported original image first. Cropping does not change source-frame identity. Use Codex's `original` viewing option when available and useful. If the host does not expose that option, do not pass invented parameters; use readable local evidence instead.

## Older visual models

Older visual models that meet the capability requirements can use the entire core workflow. GPT-6-specific parameters, asynchronous tools, structured-output APIs, and subagents are not required. Preserve the user's chosen model and reasoning effort by default.

- With a smaller context, review one operation unit with its complete before-and-after relationship per batch, splitting viewing across turns when necessary. Save steps, questions, and frame references after each batch; do not impose a fixed frame-sampling limit for the whole video.
- Keep each response focused on the current operation's object, change, confirmation/cancellation, evidence, and unknowns. Use null for unverifiable values and inspect the relevant evidence further. Model age does not change the evidence standard.
- After context compaction, task resumption, or removal of historical images, read `status`, `intervals`, and `candidates --pending` first. Reopen the images needed for the current unresolved step. Reopening does not increase distinct source-frame counts; existing results remain available.
- Execute sequentially when asynchronous or parallel tools are unavailable. When no independent reviewer is available, retain self_review and the unmet review requirement.

Script tests verify CLI and v1/v2/v3 database compatibility. Semantic model performance still requires trials with the actual model.
