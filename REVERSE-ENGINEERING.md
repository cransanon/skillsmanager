# Skills Manager, reverse engineered

Repo: `cransanon/skillsmanager`, a fork of `xingkongliang/skills-manager` at v1.40.0.
Every claim below is checked against the code unless marked unchecked.

## 1. The core purpose in one sentence

One library of skill folders on disk, with a database that remembers where each one came from and which agent folders it has been placed into, so a skill is installed once and shown to many agents without losing track of it.

That is the whole product. Everything else is plumbing around three facts the app refuses to forget:

1. Where a skill came from (git URL, local folder, marketplace ref).
2. Which agents currently have it (and by symlink or by copy).
3. Which named groups (presets) it belongs to.

Checked: `skills/manage-skills/SKILL.md` "Mental model" section states these three states and tells agents to keep them separate. The DB schema is built around them (section 4).

## 2. The problem it exists to solve

Every coding agent reads skills from its own folder: `~/.claude/skills`, `~/.codex/skills`, `~/.cursor/skills`, and so on. Checked: `src-tauri/src/core/tool_adapters.rs:147` onward lists 56 adapters, each with its own `relative_skills_dir`.

Without a manager, the same skill gets cloned into several of those folders by hand. Nothing records the source, so nothing can check for updates. Nothing records which copies exist, so removing or updating one is manual per agent. The `README.md` "Let your agents manage skills" section names this directly: installing into an agent folder "behind its back" loses "source metadata, preset membership, update tracking and cross-agent deployment state."

## 3. The five concepts

| Concept | What it is | Where it lives |
|---|---|---|
| Library (central repo) | One directory of skill folders the app owns | `~/.skills-manager/skills/`, checked `central_repo.rs:250-259` |
| Skill | A directory containing `SKILL.md` (or legacy `skill.md`) | marker rule checked `skill_metadata.rs:76-85`, policy in `docs/skill-format-detection-spec.md` |
| Agent (called "tool" in code) | A program with a known skills folder | `tool_adapters.rs:18-47` struct, `:147` defaults |
| Deployment (called "target" in code) | One skill placed in one agent folder, as symlink or copy | `skill_targets` table, `migrations.rs:95-106` |
| Preset (called "scenario" in code) | A named group of skills, deployed or undeployed as a unit | `scenarios`, `scenario_skills`, `scenario_skill_tools` tables, `migrations.rs:120-146` |

Workspaces are views over the same data from the agent's side rather than the library's side. Checked: `src/App.tsx` routes. Global Workspace = one agent's global folder. Project Workspace = an agent's folder inside a project directory (`projects` table, `migrations.rs:153-164`). Linked Workspace = any directory treated as a skills root (`workspace_type` column, same table).

## 4. The data model

SQLite file at `~/.skills-manager/skills-manager.db`. Checked: `central_repo.rs:358-360`. Schema version 8. Checked: `migrations.rs:5`.

Tables, from `migrations.rs:69-170` and later migrations:

- `skills` — one row per library skill. Carries `source_type`, `source_ref`, `source_subpath`, `source_branch`, `source_revision`, `remote_revision`, `central_path`, `content_hash`, `update_status`.
- `skill_targets` — one row per (skill, agent) deployment. Carries `target_path`, `mode` (`symlink` or `copy`), `source_hash`. Unique on (skill_id, tool).
- `scenarios`, `scenario_skills`, `scenario_skill_tools` — presets, their members, and per-member per-agent on/off flags.
- `active_scenario` — the single "legacy exclusive" active preset.
- `projects` — project and linked workspaces.
- `skill_tags` — tags.
- `discovered_skills` — skills found in agent folders that aren't in the library yet.
- `audit_log` — append-only action history (v5).
- `pending_conflicts` — sync conflicts awaiting a decision (v7).
- `settings`, `skillssh_cache` — key/value settings, marketplace cache.

The DB is not the only record. A sidecar directory `~/.skills-manager/skills/.skills-manager/` holds JSON per skill and per preset, written from the DB and readable back into it. Checked: `sync_metadata.rs:14-67` (`SkillMetaFile`, `ScenarioMetaFile`, `ScenarioSkillMetaFile`), `metadata_dir()` at `:63`. This is what lets the library travel through git: the DB stays local, the sidecar goes in the backup, and a fresh machine rebuilds the DB from the sidecar. Checked: `app_state.rs:76-81` calls `reindex_from_metadata` at startup when the sidecar exists.

## 5. How the main flows work

### Install

1. A ref is classified: local path, git URL, or `owner/repo[@skill]` marketplace ref. Checked: rule list in `skills/manage-skills/SKILL.md` "Ref resolution"; parser at `skills-manager-cli.rs:1641`.
2. Git sources are cloned to a cache, narrowed to the one skill directory when possible. Checked: `git_fetcher.rs:589` `clone_repo_ref_scoped`; `CHANGELOG.md` 1.38.0.
3. The skill directory is copied into the library and a `skills` row is written with source metadata and a content hash. Checked: `installer.rs:82-150`.
4. Nothing is deployed. Install is library-only by default. Checked: `SKILL.md` "Default is library-only".

### Deploy

1. For each (skill, agent) pair, the target path is `<agent skills_dir>/<library dir name>`. Checked: `scenario_service.rs:85-91`.
2. Mode is symlink unless the `sync_mode` setting says copy. Checked: `sync_engine.rs:275-281`.
3. Before writing, the target is classified (absent, our link, foreign link, real dir, real file) and the write is refused unless the policy proves the target is ours. Checked: `sync_engine.rs:97-160` (`TargetState`, `ReplacePolicy`). A refusal is reported as `TARGET_CONFLICT` with the paths, never silently overwritten.
4. A `skill_targets` row records the deployment.

### Adopt

Skills already sitting in an agent folder but not in the library get imported as `source_type=local`, optionally pinned to a git source. Checked: CLI `Adopt` at `skills-manager-cli.rs:212-225`; `SKILL.md` "Adopt skills installed elsewhere".

### Update

`check` compares `remote_revision` against `source_revision`. `update` re-clones and replaces the library directory, then re-syncs copy-mode targets. If the new version would delete files the old one has, the update is held back and the paths are reported. Checked: `removals.rs:47` `removed_paths`; `UpdateReport.held_back_removals` at `skills-manager-cli.rs:531-538`. A background updater polls every 15 minutes. Checked: `skill_auto_updater.rs:28`.

### Backup and multi-device sync

The library directory is itself a git repo. Checked: `git_backup.rs` operates on `skills_dir`. Auto-backup commits and pushes 2 minutes after the last change. Checked: `auto_backup.rs:35`. Merges across devices are done per skill, not per line, by a custom "object merge" engine with a protocol trailer on every commit. Checked: `merge/mod.rs:1-6`, `merge/protocol.rs:1-10`. Real conflicts land in `pending_conflicts` and wait for keep mine / use remote / keep both.

### Agents driving the app

At startup the app copies its own CLI to `~/.skills-manager/bin/skills-manager-cli` and writes a `.version` stamp only after the copy is verified. Checked: `cli_bridge.rs:1-30`, `lib.rs` setup calls `ensure_bridge`. The `manage-skills` skill (in this repo at `skills/manage-skills/SKILL.md`) teaches an agent to find that binary and use `--json` output. The Dashboard card installs that skill and deploys it to chosen agents. Checked: `src/components/AgentControlSetupCard.tsx:13-16`.

## 6. Architecture

| Layer | Location | Size | Role |
|---|---|---|---|
| Rust core | `src-tauri/src/core/` (35 modules) | ~25k lines | All logic: store, sync, git, merge, scanners, adapters |
| Tauri commands | `src-tauri/src/commands/` (10 files) | ~12k lines | IPC surface the UI calls; 150 commands listed in `src/lib/tauri.ts` |
| CLI | `src-tauri/src/bin/skills-manager-cli.rs` | 3.4k lines | Same core, five groups: `repo`, `agents`, `skills`, `presets`, `git` |
| App shell | `src-tauri/src/lib.rs` | 1.1k lines | Startup, tray icon, file watcher, background jobs |
| Frontend | `src/` React 19 + TypeScript + Tailwind | ~19k lines | Six views: Dashboard, Library, Workspace, Install, Backup, Settings, plus ProjectDetail |

Line counts checked with `wc -l`. Startup order checked in `lib.rs:804` onward: open store and migrate, publish CLI bridge, tray icon, file watcher, skill auto-updater, merge recovery, auto-backup.

The desktop app and the CLI share the DB and a repo lock, so either can change state and the other sees it. Checked: `repo_lock.rs`; `README.md` "Concurrent use with the desktop app".

## 7. On-disk layout

```
~/.skills-manager/
  skills/                      the library; also a git repo when backup is on
    <skill-name>/SKILL.md
    .skills-manager/           JSON sidecar: schema.json, skills/, scenarios/, protocol.json
  skills-manager.db            SQLite, local only, rebuilt from the sidecar
  bin/skills-manager-cli       copy of the CLI for agents, plus .version stamp
  logs/
  external/<name>-<hash>/      state for --skills-root checkouts
```

Checked: `central_repo.rs:250-360`, `sync_metadata.rs:63`, `cli_bridge.rs:45-52`, `README.md` "--skills-root".

The library path can be relocated in Settings. The `bin/` bridge stays under the real home directory regardless, so agents can find it without being told. Checked: `central_repo.rs:88-98` `home_base_dir`, `cli_bridge.rs:42-47`.

## 8. What this fork is

- 50 commits, all upstream. No commits by `cransanon`. Working tree clean. Checked: `git log --format=%an | sort | uniq -c`, `git status`.
- Identical to upstream v1.40.0 as far as git history shows.
- Updater endpoint and the manage-skills source URL still point at `xingkongliang/skills-manager`. Checked: `src-tauri/tauri.conf.json` plugins.updater.endpoints; `AgentControlSetupCard.tsx:15-16`.

## 9. What it does not do

- It does not read or interpret skill contents beyond `name` and `description` in `SKILL.md` frontmatter. Checked: `skill_metadata.rs:30-71`.
- It does not run agents or inject anything into a conversation. It only places directories where agents look.
- It does not edit skills. The library copy is replaced wholesale on update.
- It does not deploy anything automatically on install. Every deployment is an explicit action, by click, preset, or CLI.
- It has no notion of per-skill content versions. One snapshot history for the whole library via git tags. Checked: `git_backup.rs:57-71` `GitBackupVersion`.

## 10. Vocabulary map (code name to UI name)

| Code | UI / CLI |
|---|---|
| scenario | preset |
| tool | agent |
| target | deployment |
| central repo / center | library |
| sync | deploy (additive) or legacy exclusive sync |
| lobster | second agent category (OpenClaw, Hermes), checked `tool_adapters.rs:9-16` |

Unchecked, one line: your skill set is around 90 persona and tool skills aimed at Claude Code. In this system each would be one library row, Claude Code would be one agent, and groups like "Sacred Seed priests" or "desk tools" would be presets.
