# Python style

- Prefer descriptive names and readable, explicit code.
- Leave a blank line after complete statements ending in `)` and after `return` when code follows; separate logical steps with blank lines.
- Keep arguments, collection items, and headers with their bodies together; avoid trailing blank lines.
- Run `uvx ruff check .` and `uvx ruff format --check .`.
- Check the spacing rule manually; Ruff does not enforce it.

# Documentation before committing

- Before every code commit, review the documentation affected by the change. Update it in the same commit so it describes the system that the committed code implements.
- Review changes to architecture, service responsibilities, authentication, data ownership, persistence, public interfaces, configuration, and deployment or operating procedures in particular. Documentation updates are part of completing these changes.
- Update the existing authoritative guide and remove obsolete statements. Keep detailed explanations and procedures in one authoritative place. Short summaries elsewhere should link to it.
- Make each guide understandable without the task conversation. State its purpose and link any prerequisites explicitly. Explain the current system without references to previous discussions or abandoned approaches unless a decision record needs that rationale.
- Document stable responsibilities, contracts, and behavior. Reference code or configuration for frequently changing details; keep necessary setup commands accurate and distinguish examples from requirements.
- Keep task history, temporary implementation status, and test reports out of permanent guides. Keep proposals clearly separate from implemented behavior.
- For foundational guides, verify diagram arrows, job states, identities and payloads against the implementation. Clearly label proposals. Check Mermaid syntax and render changed diagrams to catch unreadable layouts.
- Check that the documentation matches the final change and that edited links and commands remain valid before committing.
- If a code change does not affect documented behavior, understanding, setup, or operation, do not manufacture a documentation edit. State briefly in the commit description why no documentation update was needed.
