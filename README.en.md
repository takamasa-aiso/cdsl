# CDSL (CoDex StatusLine)

[日本語](README.md) | English

CDSL is an unofficial tool that adds a CCSL-style status display when you run `codex`. It shows the model and effort, context usage, usage limits, and permissions in five rows at the bottom of your terminal.

![CDSL status display with gpt-6-astra(high) and a pink Fast marker](assets/statusline-preview.png)

The preview uses synthetic values.

- [How it works](#how-it-works)
- [Installation](#installation): requirements, automatic installation, and manual installation
- [Updates](#updates)
- [Maintenance](#maintenance): diagnostics, display reload, uninstallation, and recovery
- [Display and controls](#display-and-controls): rows, permissions, scrolling, copying, and pasting
- [Configuration and storage](#configuration-and-storage): startup files, official Codex paths, and custom rendering
- [Project information](#project-information): security, license, releases, and repository contents

## How it works

![CDSL startup, local session data, and the two terminal panes](assets/how-it-works.svg)

CDSL starts official Codex in tmux's upper pane and displays status in the lower pane without modifying the official executable. It reads conversation logs, Git information, and shortcut settings, passes JSON to the renderer, and normally refreshes once per second.

`statusLine.command` is CDSL's own setting. The tested Codex 0.153.4 has no setting for embedding an external command's output in its native status line. Calls such as `codex exec`, `codex update`, and help pass through to official Codex.

## Installation

### Requirements

| Item | Requirement |
|---|---|
| OS and shell | Linux / WSL, Bash |
| Dependencies | Python 3.11 or later, tmux 3.2 or later, Git |
| Codex CLI | Standalone or npm installation; tested with 0.153.4 and 0.156.1 |

tmux has been tested with 3.2a and 3.4. macOS, native Windows, and remote Codex connections are outside the supported scope.

### Installing with install.sh

Run this where `curl` is available. It downloads CDSL into `~/.local/share/cdsl/source`, installs missing packages through apt/dnf, and installs Linux Codex if it is missing.

**Install only, then start Codex in a new Bash shell**

```bash
curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh
```

**Install and activate the current Bash shell**

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) && . "$HOME/.config/cdsl/shell.sh"
```

### Manual installation

First install the required packages and [official Codex](https://learn.chatgpt.com/docs/codex/cli). The Python commands stop before changing settings if dependencies are missing; they do not install packages.

<details>
<summary>Package commands by operating system</summary>

Ubuntu 24.04 / Debian 12:

```bash
sudo apt update
sudo apt install python3 tmux git bash
```

RHEL 9.4 or later and compatible distributions such as AlmaLinux and Rocky Linux:

```bash
sudo dnf install git bash tmux python3.12
```

Keep the OS's Python 3.9 unchanged and use `python3.12` for the initial installation commands. RHEL 10 provides Python 3.12 as its default:

```bash
sudo dnf install git bash tmux python3
```

Check the requirements with `python3 --version` (`python3.12 --version` on RHEL 9) and `tmux -V`. Full functionality has not been verified on a RHEL installation; on compatible distributions, also confirm package availability.

References: [Ubuntu](https://packages.ubuntu.com/noble/python3) / [Debian](https://packages.debian.org/bookworm/python3) / [RHEL 9](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/installing_and_using_dynamic_programming_languages/assembly_installing-and-using-python_installing-and-using-dynamic-programming-languages) / [RHEL 10](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/installing_and_using_dynamic_programming_languages/installing-and-using-python)

</details>

```bash
git clone https://github.com/takamasa-aiso/cdsl.git
cd cdsl
python3 scripts/cdsl.py install --codex --dry-run
python3 scripts/cdsl.py install --codex
```

### Starting Codex

**Installation also configures rendering; no separate setup is needed.** Existing settings are preserved. Keep the downloaded or cloned directory, because CDSL runs directly from it.

If the current Bash shell has not been activated, open a new Bash shell or run this. Both installation methods use the same path for the same user; no `cd` is needed.

```bash
source "$HOME/.config/cdsl/shell.sh"
```

Run `codex` to start or `codex resume` to resume a conversation. If needed, [sign in](https://learn.chatgpt.com/docs/auth) with `codex login`.

## Updates

Uninstallation is not required. Exit Codex and run these commands at the installing user's regular Bash prompt. Renderer settings are preserved.

### Installed with curl

Rerunning the installer updates the existing source and installs missing dependencies.

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

### Manual clone or local install.sh

Replace `CDSL_DIR` with your actual clone location. If missing packages are reported, install them using [Manual installation](#manual-installation).

```bash
CDSL_DIR="$HOME/cdsl"

git -C "$CDSL_DIR" pull --ff-only &&
  python3 "$CDSL_DIR/scripts/cdsl.py" install --codex &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

Startup and tmux changes require a new Codex session. Reloading only the lower display does not apply them.

## Maintenance

### Common preparation for maintenance

In the installing user's Bash shell, select the source directory. The following operations do not require `cd`.

| Installation method | Setting |
|---|---|
| `install.sh` through curl | `CDSL_DIR="$HOME/.local/share/cdsl/source"` |
| Manual clone or local `install.sh` | `CDSL_DIR="$HOME/cdsl"` (replace with your actual clone path) |

Set the variable again in a new Bash shell. Root and regular users have different `HOME` directories. Even if `python3` is 3.9, management scripts switch to the installation's Python or another available Python 3.11 or later.

### Diagnostics

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
```

Checks dependencies, source files, the official Codex path, startup artifacts, and renderer settings, reporting `OK` or `NG` and suggested action. It changes no settings and does not test sign-in or actual usage retrieval, rendering, or image pasting.

### Reloading the display

Run this inside the active Codex session to reload only the lower display:

```bash
python3 "$CDSL_DIR/scripts/refresh-statusline.py"
```

### Uninstallation

Exit Codex and run these commands in your regular Bash shell:

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex && hash -r
```

`--dry-run` only previews changes. Uninstallation removes the dedicated entry, `shell.sh`, startup metadata, and managed Bash blocks. Before changing files, it backs them up under `~/.local/share/cdsl/backups/` and prints their backup paths. **Source files, renderer settings, backups, official Codex, and OS packages are retained.**

Run `hash -r` in that same Bash shell to clear the old command location; it does not change PATH. Python cannot clear its parent shell's cache. If Codex will not start, check `type -a codex` and use the absolute Linux Codex path printed by the uninstaller. You do not need to source CDSL again after uninstalling it.

### Recovering from damaged metadata or modified artifacts

Normal uninstallation removes recognizable generated files even when metadata is missing or damaged. It reports no changes only when no artifacts remain; unrecognized contents stop it with exit code 1. In that case, inspect with `doctor`, then explicitly use `--purge`:

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge && hash -r
```

`--purge` still targets only startup integration. It removes modified generated files and managed blocks after backing up each entire file, preserving content outside the blocks. Symlinks, non-regular targets, and blocks with unclear boundaries stop the operation without writes. Rerun `install.sh` after recovery; resolve any separate errors in renderer settings or dependencies too.

## Display and controls

### Five rows and usage

| Row | Meaning |
|---|---|
| Header | Model and effort, working directory, Git branch and change count |
| Context | Current conversation's context percentage, token count, capacity, and cache ratio |
| Session | Account usage of the five-hour limit and this conversation's cumulative tokens |
| Weekly | Account usage of the weekly limit and time until reset |
| Permissions | The current conversation's permission scope and approval policy |

Example: `[gpt-6-astra(high)]`. Effort comes from the current conversation log and appears in pink, including its parentheses. It is omitted when unknown and never inferred from global settings. When Codex records Fast in an applied-settings event, a pink Fast marker appears next to the model. Narrow terminals abbreviate effort to `lo`, `med`, `hi`, or `xh` when the model name would otherwise be clipped. Times use JST.

### Understanding limits and graphs

**Session and Weekly percentages describe the account; graphs show consumption in the displayed conversation.** Other conversations are not aggregated. Data comes from Codex's local logs.

| Display | Meaning |
|---|---|
| `[N/A]` | The returned limits do not include that window |
| `[---]` | The percentage is unavailable or its period has expired |
| `Permissions: unknown` | Permission information is unavailable or not recognized |
| Waiting message | The active conversation cannot be identified unambiguously |

When valid five-hour limit data is recorded again, Session returns to displaying its percentage. Reinstallation is unnecessary.

<details>
<summary>Why graph bars can move without new usage</summary>

Bar heights show relative consumption in each time interval. The graph covers the limit's period when a reset time is available; otherwise, Session uses the preceding five hours. Intervals and scale change over time, so bars can move without new consumption. They do not directly represent remaining allowance or elapsed time.

</details>

### Permissions and shortcuts

The row shows `scope | approval policy`. Assign a key to `next_permission_mode` in `/keymap` to show a hint such as `(F7 for cycle)`. An unassigned action shows `(/keymap to set cycle key)`; an undetermined binding shows a check hint.

In the tested [Codex 0.153.4](https://github.com/openai/codex/releases/tag/rust-v0.153.4), the action starts unassigned. Close menus and press the key in the input area to cycle through the available Read Only, Ask for approval, and Approve for me modes. **Select Full Access through `/permissions`.**

Changes apply to the current conversation. CDSL follows log updates on its normal one-second cycle, without another prompt. Use `/keymap` to change the binding too.

`Approve for me` is the closest practical counterpart to Claude Code's `auto` mode in replacing manual approval prompts with automatic review. Their mechanisms differ, and either can reject an operation. [Codex](https://learn.chatgpt.com/docs/sandboxing/auto-review) / [Claude Code](https://code.claude.com/docs/en/permission-modes#eliminate-permission-prompts-with-auto-mode)

<details>
<summary>Permission scopes and approval policies</summary>

Scopes include `Read Only`, `Workspace` (writes in allowed locations), and `Full Access` (no Codex sandbox restriction). OS and organizational restrictions still apply. Custom settings appear as `Custom permissions` or a profile name.

| Approval policy | Meaning |
|---|---|
| `Ask for approval` | Requests user approval when needed |
| `Approve for me` | Sends operations requiring approval to automatic review |
| `Never` | Does not request approval; denies operations requiring it |
| `On request` | Requests approval when needed, but the log does not identify the reviewer |
| `Untrusted` | Requires approval for commands outside the known safe set |
| `Granular` | Allows or denies approval requests by category |
| `On failure` | Requests approval to retry outside restrictions after a sandbox failure; deprecated |
| `unknown` | Unavailable or not recognized |

`Never` does not define access scope. `Read Only | Never` is read-only; `Full Access | Never` has no Codex sandbox restriction and makes no approval requests. Inspect individual allowed paths with `/permissions` or `/status`.

</details>

### Scrolling, copying, and pasting

- Scroll the upper pane's history with the wheel or trackpad. Return to the bottom or press `q` or `Esc` to resume input. The lower pane stays fixed.
- On WSL, dragging across text in the upper pane copies it to the Windows clipboard. `Ctrl+v` pastes clipboard text or images into Codex. Right-click paste works when the terminal forwards that mouse event to tmux.
- For native text selection, hold `Shift` while dragging in terminals that support it. Outside WSL, use your terminal's copy and paste controls; copying from tmux requires terminal-side OSC 52 support.
- Paste images with `Ctrl+v`. Depending on the environment, `Alt+v` or Codex's standard alternate `Ctrl+Alt+v` may also work. Otherwise, attach the image file's path.

Image-paste bindings cannot be edited in `/keymap`. Check received keys through `/keymap` → `Debug` → `Inspect keypresses` (Enter to start, `Ctrl+c` to exit). [Key definitions](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap.rs#L2164) / [Key inspector](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap_setup/picker.rs#L312)

The WSL clipboard bridge uses Windows PowerShell to copy selected text to Windows. On `Ctrl+v`, it converts clipboard images to PNG attachments or pastes text if there is no image. Failed retrieval falls back to Codex's standard handling.

### Legacy terminals

Narrow terminals shorten labels and hints. Terminals such as `TERM=xterm` without `COLORTERM` use ASCII graphs and basic colors, and spell out Fast as `fast`. Select compatibility output with `CDSL_RENDER_MODE=ascii codex`, or standard output with `CDSL_RENDER_MODE=unicode codex`.

## Configuration and storage

### Startup files and Codex updates

| Location | Purpose |
|---|---|
| `~/.local/share/cdsl/bin/codex` | Dedicated startup entry |
| `~/.config/cdsl/shell.sh` | Adds the entry to the front of PATH |
| `~/.bashrc` and Bash login configuration | Managed blocks loading the integration |
| `~/.config/cdsl/config.toml` | Rendering command and refresh interval |
| `~/.local/share/cdsl/startup.json` | Startup metadata |
| `~/.local/share/cdsl/backups/` | Copies of changed files saved with permissions `0600` |

Official Codex updates do not remove CDSL's entry. Changes to Codex's location or log format may require reconfiguration or CDSL changes. If you move the CDSL source directory, reinstall from the new location and update the renderer's `command` path too.

### Finding the official Codex executable

| Installation | Example entry |
|---|---|
| Standalone | `~/.local/bin/codex`, linked to `~/.codex/packages/standalone/current/bin/codex` |
| npm | `<prefix>/bin/codex`, for example `/usr/local/bin/codex` |
| nvm | `~/.nvm/versions/node/<version>/bin/codex` |

CDSL prefers the standalone `current` entry, then searches PATH. Check candidates, npm's location, and the symlink target with:

```bash
type -a codex
type -aP codex
npm prefix -g
readlink -f "$HOME/.local/bin/codex"
```

To select an entry explicitly, first [set `CDSL_DIR`](#common-preparation-for-maintenance), then specify the official Codex entry. Replace the example with your actual path; avoid CDSL's dedicated entry or a version-specific internal path.

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" install --codex --real-codex "$HOME/.local/bin/codex"
```

### Custom rendering

Normally no configuration is needed. To customize it, edit `~/.config/cdsl/config.toml` using the Python and source paths for your environment:

```toml
[statusLine]
command = ["/usr/bin/python3", "/absolute/path/to/cdsl/scripts/statusline.py"]
timeout_seconds = 2.0
refresh_interval = 1.0
```

`command` is an argument array: `~`, variables, pipes, and other shell expansion are unavailable. To use another configuration file, create it yourself and set `CDSL_CONFIG` to its path.

Custom renderers receive version 1 JSON on standard input and return UTF-8 ANSI text. See [scripts/statusline.py](scripts/statusline.py) for the protocol. Standard output and standard error are limited to 64 KiB each; Codex remains usable after renderer failures or timeouts.

## Project information

- **Security:** Report issues [privately](https://github.com/takamasa-aiso/cdsl/security/advisories/new); see [SECURITY.md](SECURITY.md).
- **License:** [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) retain the MIT terms, CCSL attribution, and original copyright notices. Attribution does not imply endorsement by OpenAI or the CCSL author.
- **Releases:** [GitHub Releases](https://github.com/takamasa-aiso/cdsl/releases) describe changes, tested Codex versions, and known limitations in Japanese and English. Each release tags its published commit; this README describes current behavior.
- **Repository contents:** [cdsl/](cdsl/) contains the implementation, [scripts/](scripts/) the entry scripts, and [assets/](assets/) the preview and diagrams.
