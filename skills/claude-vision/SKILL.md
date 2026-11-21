---
name: claude-vision
description: Give a text-only agent eyes through Claude Code. Use when a task needs to actually look at an image — a page screenshot, a rendered mockup, a before/after pair — such as visual QA of layout, alignment, spacing, contrast, typography, or clipping, including follow-up questions about the same image.
---

# claude-vision

`claude -p` runs Claude Code non-interactively. It loads images with its `Read`
tool, so an agent with no vision of its own can have a screenshot looked at and
get an answer back.

## Recipe

One evaluation = one fresh directory holding nothing but the images. Copy each
image into it, because file tools only reach inside the working directory.

    d=$(mktemp -d) && cp shot.png "$d/" && cd "$d"
    claude -p --disable-slash-commands --tools=Read --model haiku \
      "Use the Read tool on ./shot.png, then review layout, alignment, spacing, contrast and clipping. Give a verdict, then a numbered list of concrete problems."

Keeping the directory empty is not cosmetic: it stops the model from answering
out of project source instead of the pixels.

## Model

`--model` accepts one of three tiers, or a custom model id the user names:

| value | when |
|---|---|
| `haiku` (default) | cheapest and fastest; spotting the obvious problem on a screen |
| `sonnet` | balanced, more careful reading of the layout |
| `opus` | strongest; a design critique, a before/after comparison, a verdict that has to be right |
| `<custom-id>` | a model the user specifies |

The recipe above pins `haiku` because most reviews only need the obvious. Climb
the tiers when the judgement matters, and take the user's model when they name
one.

A model that cannot accept images may still answer — describing the page from
project source, or from the filename — sounding confident having seen nothing.
To prove it really looked, ask something only the pixels can answer (the label
of a specific button, the text beside an icon, a colour) and check the answer
against the image.

## Follow-ups

Continue in the same directory with `-c`. When the page has changed, copy the
new screenshot in first, then ask about it — that is how a fix gets verified:

    cp shot2.png . && claude -c --disable-slash-commands --tools=Read \
      "This is ./shot2.png after the fix. Is problem #2 gone?"

A fresh evaluation gets a new directory; a follow-up reuses one, whether it asks
about the same image or about a new screenshot of the same work, so the earlier
verdict is still there to compare against.

## Expect it to vary

A small model answers a screenshot in seconds; a larger one, or a high effort
level, turns the same call into a full agent turn that takes minutes. Set the
command timeout for the slow case, and keep the explicit "use Read on
./shot.png" instruction: a model in a hurry may skip the image and answer from
the filename.

## Loop

    screenshot -> claude -p review -> read the numbered findings
               -> change the page -> screenshot -> claude -c "is #2 fixed?"
