# Source Cmd blueprints

The Source Cmd catalog of **blueprints**: ready-made agents you can create
on your own keep. A blueprint is an agent's job (its name, persona, what it
does and how, what it runs on, and what it would ask you for and why) as one
small YAML file. Nothing in it is about you: what you tell an agent, what it
learns and where it runs stay on your keep.

Keeps fetch this catalog from **https://keepcmd.com/blueprints/**, check its
signature against the keys compiled into Keep Cmd, and let you browse it on
your own keep, so nobody learns which blueprints you looked at.

## The catalog

| Blueprint | Job | What it is |
|---|---|---|
| `sourcecmd/dolly-o` | Macro Long Short Advisor | An AI persona inspired by Ray Dalio's public thinking |
| `sourcecmd/crug-man` | Economic Sophist | An AI persona inspired by Paul Krugman's public writing; the panel's heel |
| `sourcecmd/ludwig` | Economist | An AI persona inspired by Ludwig von Mises |
| `sourcecmd/petey-j` | Macro Trader | An AI persona inspired by Paul Tudor Jones's public talks on trading |
| `sourcecmd/warn-buffet` | Value Investor | An AI persona inspired by Warren Buffett's public thinking and Ben Graham |
| `sourcecmd/rare-earths-guy` | Equity Research Analyst | An invented character: the panel's research workhorse |
| `sourcecmd/schott-calder` | Scorekeeper | An invented character: the panel's referee, who logs every call |

Together they're an investing panel for one Loop conversation: each speaks
when @-mentioned or when the panel is addressed, answers the others by name,
and anyone may ask Schott Calder to log a prediction. None of them is
financial advice.

## Layout

```
blueprints/<namespace>/<slug>/blueprint.yaml   one file per blueprint; the path is its id
SCHEMA.md                                       the format, per kind and format version
scripts/build-index.py                          lint and build the signed index
scripts/release.sh                              build a release into dist/
scripts/sign-index.sh                           sign the index (where the key lives)
```

The format is in [SCHEMA.md](SCHEMA.md): `kind: agent`, `format: 1`, strict,
job layer only.

## Curation

**In-house only, for now.** Source Cmd writes and reviews every blueprint.
There are no community submissions and no contribution process yet; pull
requests from outside aren't accepted. Every id carries an author namespace
(`sourcecmd/…`), so other authors can be added later without renaming
anything. There are no ratings, stars or install counts: they'd need
something counting who installs what.

The rules every entry follows, which the lint enforces where a machine
can (`python3 scripts/build-index.py --check` before merging a change;
every release runs it, and keepcmd's own parser checks the build again
before it's published):

- **Job only.** The format has no field for anything about an owner, a
  keep, a household or a machine, and refuses unknown fields.
- **Public figures as personas, never private people.** A blueprint may
  channel a public figure's publicly known views (tag `persona`), or be an
  invented character (tag `character`) that channels no one. It never names
  or describes a private person, household or machine.
- **Persona guardrails.** Every `persona` blueprint has a "Who you are, and
  aren't" section in its instructions saying that it's an AI persona
  channelling the person's public views and never claims to be them; that
  it never invents quotes presented as real; that it never implies the
  person's endorsement, and its calls are the persona's, never the
  person's; and to be playful and respectful, especially of living people.
  Its summary says "inspired by". A `character` has a "Who you are"
  section saying it's an AI character. The lint refuses one without it.
- **No personal data.** The lint refuses email addresses, phone numbers, IP
  addresses, home-folder paths and anything that looks like a secret.
- **Made from a real agent.** Each entry is exported from an agent we set
  up and use, so the format never holds anything a live agent can't
  produce.

## Releases and signing

A release is built with `scripts/release.sh <catalog_version>` (a date,
`2026.10.08`, or `2026.10.08.1` for a second release that day). It
validates every file and writes `dist/index.json` (each blueprint's id,
kind, format, version, summary and the sha256 of its file),
`dist/catalog.tar.gz` (the `blueprints/` tree) and an unpacked copy.

The index is signed with the **catalog key**, the same Ed25519 key set as
the plugin catalog: its public halves are compiled into every keepcmd
binary, so every keep trusts them and only them. One signature over the
index's exact bytes covers every file's hash and every version number.
Keeps verify it before storing anything, check every file against its
hash, store each version unchangeably, and refuse an index whose
`catalog_version` is older than the one they already have.

The signed files are published under `blueprints/` on keepcmd.com.
