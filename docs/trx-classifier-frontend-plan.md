# TRX-classifier frontend plan

> Historical plan for the disposable Acetate Web 0.1 test client. Its direct `/classify` integration does not match the current authenticated job API. Use the [API contract](trx-classifier-contract.md#http-api) for new integration. The interface notes below remain a design reference.

Build a disposable visual test client based on the second design concept. Keep it separate from the agent in `apps/acetate-web-0.1/`.

## Stack and structure

- Plain HTML, CSS, and JavaScript; no framework or build step.
- [Pico CSS](https://picocss.com/) for ready-made styling of buttons, file inputs, tables, and other native HTML elements.
- [fetch-event-source](https://github.com/Azure/fetch-event-source) for multipart POST requests with SSE responses; use its existing parser.
- Acetate's approved logo and a ready-made Phosphor PDF icon.
- Use the existing frontend and its locally installed UI libraries on port 3101.

```text
apps/
├── agent-trx-classifier/
│   └── src/evaluations/dataset/
│       ├── dataset.json
│       └── fixtures/
│           └── fixture-01.pdf
└── acetate-web-0.1/
    ├── index.html
    ├── styles.css
    ├── app.js
    ├── assets/
    └── README.md
```

## Fixtures

- Copy `fixture-01.pdf` from `/Users/gabrieloliveira/Gabrr/learning/Evaluation Lab/LangChain/src/evaluations/normalizer/fixtures/fixture-01.pdf` into the agent's dataset fixtures folder.
- Copy `dataset.json` from `/Users/gabrieloliveira/Gabrr/learning/Evaluation Lab/LangChain/src/evaluations/normalizer/dataset.json` into the agent's dataset folder. Preserve the source files and their contents.
- Upload the local PDF through the frontend. Use the dataset's expected results for LangSmith evaluation, mapping reference labels to the agreed classifier labels during evaluation.

## Interface

- Two columns: conversation on the left, selected step output on the right. Stack them on narrow screens.
- Apply Acetate's white surfaces, black text, restrained teal accents, and existing typography fallbacks through a small CSS override file.
- Composer: PDF picker and Send button. No general-purpose chat functionality.
- Show the submitted PDF as a user message with a clearly visible PDF icon and filename. Clicking it opens the original document using the browser's native viewer.
- Show incoming workflow steps as one connected vertical chain with running, completed, or failed states.
- Clicking a step selects its output in the side viewer. Display the step name and output type.
- Use a simple scrollable `<pre><code>` viewer: indent JSON; display text and Markdown as source. No custom document renderer, field cards, or editor.
- Preserve the user's selected step while further events arrive.
- On completion, show all transactions in a table beneath the chain: description, amount, category, and confidence. Sort by confidence ascending without changing the original API result.

## API boundary

- Send one PDF as multipart field `file` to configurable `POST /classify`; consume `text/event-stream`.
- Use the shared event contract: `step_started`, `step_completed`, `result`, and `error`.
- Step events need a stable step ID and readable name. Completed steps include their actual output and output type (`json`, `text`, or `markdown`).
- The final result includes transactions with `report_bucket` and `classification_confidence`.
- Keep API communication and event normalization separate from DOM updates within `app.js`.
- Allow one active run; disable Send while processing. Show validation, HTTP, stream, and workflow errors visibly.
- Disable automatic POST retries and visibility-triggered reconnection to avoid starting duplicate runs. A premature stream closure is an error; retain outputs already received.
- Use the existing same-origin `/api/classify` proxy to the agent on port 8000. Render outputs as text, never executable HTML.

## Acceptance checks

- Submit `fixture-01.pdf`; see its attachment message and steps appear as events arrive.
- Inspect the actual Markdown, extraction JSON, and classification JSON by clicking their steps.
- After completion, see every returned transaction, with the least confident first.
- Check failure handling, long output scrolling, and the narrow-screen layout.

Implementation uses Acetate Web 0.1; fixtures are copied into the agent. The core API and LangSmith evaluation are implemented.
