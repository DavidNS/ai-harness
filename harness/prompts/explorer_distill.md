# Explorer Distill Phase Prompt v1

Rewrite the supplied artifact candidate into a concise canonical `# Improvement` document.

Preserve:
- The core user-visible problem.
- Concrete repository evidence and inspected paths.
- The intended behavior and minimum verification intent.
- Important implementation constraints, risks, and falsifying conditions.
- Observable acceptance criteria.

Remove:
- Internal labels such as selected direction, value hypothesis, behavioral delta, counterevidence, falsifying conditions, and rejected alternatives.
- Internal IDs such as C1, C2, D1, D2, unless they are part of a real public API or command name.
- Checkboxes, mixed numbered procedures, transcript language, and explorer-process narration.

Acceptance criteria must be explicit, observable, and verifiable. Prefer concise
natural-language Markdown bullets that name the outcome and the proof signal.
Use structured JSON only when it makes a genuinely complex criterion clearer.
Do not require or default to Given/When/Then wording.

Return only the required compact improvement Markdown. Do not wrap it in a code fence. Do not claim controller execution, persistence, publication, phase completion, or permission escalation.
