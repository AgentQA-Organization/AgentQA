# Installation

The full installation reference. For the quick path, the [README](../README.md#installation)
has the two commands most people need; this page covers every harness, every
flag, and the manual route.

Prerequisites (Node.js, Python, and the platform toolchain) are in
[`toolchain.md`](toolchain.md).

## Claude Code (preferred)

Register this repo as a plugin marketplace, then install — `agentqa-init`,
`agentqa-write-test`, and `agentqa-studio` are auto-discovered from
[`skills/`](../skills/) via the [`.claude-plugin/`](../.claude-plugin/) manifest:

```bash
claude plugin marketplace add https://github.com/TunNguyen-25/AgentQA
claude plugin install agentqa@agentqa
```

Default scope is `user` (this machine only); add `--scope project` to commit the
choice to `.claude/settings.json` and share it with your team.

```bash
claude plugin update agentqa@agentqa      # update
claude plugin uninstall agentqa@agentqa   # remove
```

## Codex / Cursor (plugin manifest)

The repo ships per-harness plugin manifests that point at the same
[`skills/`](../skills/) folder — [`.codex-plugin/plugin.json`](../.codex-plugin/plugin.json)
and [`.cursor-plugin/plugin.json`](../.cursor-plugin/plugin.json) (the same
convention as [`.claude-plugin/`](../.claude-plugin/), mirroring
[obra/superpowers](https://github.com/obra/superpowers)). Install the repo through
the harness's own plugin flow, or use `install.sh` below — for Codex it raw-copies
the skills into `.agents/skills/`, the Agent-Skills path Codex reads.

## `install.sh` (any harness)

A raw-copy installer that places the skill folders directly into your harness's
skills directory. Use this for harnesses without a marketplace flow.

**One-liner** (run from inside your app repo — installs into `.claude/skills/`):

```bash
curl -fsSL https://raw.githubusercontent.com/TunNguyen-25/AgentQA/main/install.sh | bash
```

To pass flags through the pipe, use `bash -s --`, e.g.
`curl -fsSL <url> | bash -s -- --global`.

**Manual** (inspect first):

```bash
git clone https://github.com/TunNguyen-25/AgentQA.git
cd AgentQA && ./install.sh
```

The installer detects your harness and copies the skill folders into that
harness's skills directory. Flags:

| Flag | Effect |
|---|---|
| _(default)_ | install into the current app repo (`<repo>/.claude/skills/`) |
| `--global` | install user-wide (`~/.claude/skills/`) |
| `--ref <tag\|branch>` | version to fetch when cloning (default `main`) |
| `--harness <id>` | override harness detection (or set `AGENTQA_HARNESS`) |
| `--setup` | also run the toolchain setup after installing (default: no) |

## Harness support

Claude Code installs via the native marketplace or `install.sh`. Codex and Cursor
have per-harness plugin manifests (`.codex-plugin/`, `.cursor-plugin/`) pointing at
the shared `skills/`, and Codex is also a native `install.sh --harness codex`
target (raw-copy into `.agents/skills/`). For any other harness, `install.sh`
prints where to place the `agentqa-init/`, `agentqa-write-test/`, and
`agentqa-studio/` folders.

Because every skill is plain [Agent Skills](https://agentskills.io) `SKILL.md`, the
same `skills/` works across harnesses — only the install path differs. Per-harness
plugin marketplaces are still maturing, so `install.sh` stays the guaranteed path.

## First run

```text
1.  /agentqa-init setup   # install & validate the toolchain (once per machine)
2.  /agentqa-init init    # configure THIS app repo (once per project)
3.  /agentqa-write-test "log in with a valid account lands on the home tab"
4.  /agentqa-write-test "run the login suite"   # green loop on demand
```

Step 1 installs the [toolchain](toolchain.md); step 2 writes
[`.agentqa/config.yml`](configuration.md).

## Versioning

Releases are git-tagged with SemVer (`v1.3.2`). The plugin version lives in
[`.claude-plugin/plugin.json`](../.claude-plugin/plugin.json), and each skill
carries its own in its `SKILL.md` frontmatter (`metadata.agentqa-init-version`,
`metadata.agentqa-write-test-version`, `metadata.agentqa-studio-version`). Pin the
installer to a release with `--ref v<x.y.z>`.

## See also

- [`toolchain.md`](toolchain.md) — prerequisites and what `setup` installs
- [`configuration.md`](configuration.md) — what `/agentqa-init init` writes
