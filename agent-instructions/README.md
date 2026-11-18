# Instructions for agents

Rules that an LLM agent (Claude Code, Codex and the like) follows when it works with oloop files. They are written for the agent, not for the implementer of a client or server. For agents as participants of the server (keys, member endpoints) see `../AGENTS.md`.

Each file covers one topic:

| File | Topic |
| --- | --- |
| `task-markdown.md` | How to write the Markdown of task files so that the oloop renderer shows it right |

## Using them

Import the files into the global `~/.claude/CLAUDE.md` from the local checkout, so that there is one copy and a `git pull` updates every agent:

```markdown
@~/dev/oloop/oloop-spec/agent-instructions/task-markdown.md
```

Do not paste the text into other files.

## Keeping them

Some rules depend on what the renderer of the desktop app can show today (for example that HTML is shown as text). When the renderer changes, change `task-markdown.md` in the same step.
