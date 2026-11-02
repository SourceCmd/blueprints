# The blueprint format

A blueprint is one YAML file holding an agent's **job**: what any copy of
the agent would be, and nothing about anyone who runs it. Every file starts
with its **kind** and that kind's **format** version. Keeps read the kinds
and formats they know and refuse everything else by name.

| Kind | Formats keeps read | What it is |
|---|---|---|
| `agent` | `1` | One agent's job layer |

Other kinds (a bundle of agents, a household recipe, a routine) may come
later, each with its own format numbering.

## Strict by design

- **An unknown field is refused**, at every level. A field added later
  (perhaps carrying something sensitive) never passes through an older keep
  silently: additions bump `format`.
- **A file without `kind` is refused.** Hearth's old proposal format
  (`blueprint_schema: 1`, `items:`) is retired, and such a file is refused
  as "made for Hearth's old blueprint format".
- **A file is at most 64 KB**, one YAML document.
- **A blueprint never grants.** Its `asks` are what the agent will ask for,
  written down ahead of time, each with why. The owner decides, on their
  keep, at review. A declared risk (`risk:`) is an unknown field: the keep
  decides risk, not the file.

## `kind: agent`, `format: 1`

```yaml
kind: agent
format: 1
id: sourcecmd/researcher          # <author namespace>/<slug>, lowercase; sourcecmd/ is Source Cmd's
version: 1.0.0                    # semver, the blueprint's own
display_name: Researcher          # at most 60 characters
summary: Digs into a question across the web and reports back with sources.   # at most 300
tags: [research, writing]         # lowercase words and dashes; at most 12
author: Source Cmd
apps: [loop, hearth]              # which apps list it: loop, hearth, or both
min_keep_version: 0.9.0           # optional

agent:                            # the job layer, field for field
  name: Researcher                # suggested; the owner can change it at review
  persona: |                      # optional; the agent's voice and character (at most 4 KB)
    Curious, precise, a little dry.
  job: Researcher                 # the job title (at most 120)
  instructions: |                 # how it does the job, as Markdown (at most 32 KB)
    You research questions for the person who asks...

personal_hints:                   # questions for "What <name> should know about you"; never answers
  - What you already know about the subject, so it doesn't start from zero.

runs_on:
  harnesses: [claude-code, codex] # preference order; the keep falls back to what it has
  model: capable                  # economical | capable; omit for the keep's default
  prefer_models:                  # optional, exact, per harness, best first
    claude-code: [claude-sonnet-5-5]

skills:                           # skills from the plugin catalog, by slug and version
  - skill: sourcecmd/citing_sources
    version: 0.2.0

asks:                             # what it would ask for, each with why
  tools:
    - tool: WebSearch
      why: Finds sources.
    - tool: Bash
      pattern: npm test           # optional: narrows the tool to one command
      why: Runs the tests before it says it's done.
  network:                        # exactly one of: open: web | host: <name> | category: <name>
    - open: web
      why: Follows sources wherever they are.
  own_folder:                     # read, or read and change, files in its own folder
    access: read-write            # read | read-write
    why: Keeps its notes and drafts.
  folders:                        # a folder the owner picks at review: a label, never a path
    - access: read
      label: Your reading notes
      why: Reads what you've already gathered.

needs:                            # plugins it uses, by catalog name; never installed by the blueprint
  plugins:
    - plugin: sourcecmd/home-assistant
      actions: [turn_on]
      why: Turns the lights on when asked.
      optional: true              # works without it
```

Required: `kind`, `format`, `id`, `version`, `display_name`, `summary`,
`author`, `apps`, `agent.name`, `agent.job`, `agent.instructions`, and a
`why` on every ask. Everything else is optional.

YAML reads `key: value` inside a list item as a mapping, so quote a hint or
a `why` that contains `: ` (`- "How patient you are: when you'd want the
money back."`).

### What the asks mean on a keep

- **Tools** become allow rules for that tool (narrowed by `pattern`) if the
  owner ticks them at review.
- **`network: open: web`** is any public website: one bare `Network` rule.
  It never reaches the owner's home network, loopback or cloud metadata
  addresses; the keep refuses those whatever the rules say.
- **`own_folder`** is the file tools inside the agent's own folder, bounded
  by its sandbox wall.
- **`folders`** open a folder picker at review; the file names a label only.
- **Plugins** are a separate install with their own review.
- **`grant`** on a plugin (format 2, D-420; keeps that read only format 1
  skip the blueprint): the level the job asks for on a connection of the
  plugin, `reads` (the default: its read verbs run freely, anything that
  changes asks the owner each time) or `everything` (every verb runs
  without asking; its `why` must say what it changes). The review line
  is never pre-ticked; the owner picks a connection and may lower the
  level, never raise it.
- **`manage`** (added to format 1 on 2026-10-09; older keeps skip a
  blueprint that has it): rights over the owner's other agents, by action:
  `agent.create`, `agent.update` (name, persona, job and model),
  `agent.add_to_chat` (add the owner's agents to a Loop conversation the
  agent is in), `agent.sleep`, `agent.wake`, `agent.retire`. Each `{action,
  why}`; each action once. Never pre-ticked; ticked, it becomes the keep's
  rule for that action on every agent of the owner's space (and lets the
  matching `keepcmd` command through, so the keep's own check decides).
  Without a tick, each such step asks the owner.

  ```yaml
  asks:
    manage:
      - action: agent.create
        why: Makes the agents people ask it for.
  ```

The catalog's agents are reasonably permissive for now: the review
pre-ticks reads-only tools, the open web and the agent's own folder. A
folder the owner must pick, plugins and anything the keep considers
sensitive (a shell, a write outside its folder) stay unticked.

### What a blueprint never contains

There is no field for any of these, so they can't be written:

- **Where and how it runs:** a space, host, folder path, who may talk to it,
  rules, connections, plugin configuration, secrets, schedules, any keep id.
- **Anything personal:** the owner's notes, the agent's memory, its files,
  transcripts, history, attachments.
- **Code:** no scripts, binaries or hooks. Skills and plugins are named by
  catalog slug.
