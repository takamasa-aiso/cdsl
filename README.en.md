# CDSL (CoDex StatusLine)

[日本語](README.md) | English

CDSL adds a CCSL-inspired status display when you run `codex`. It keeps the model and effort, context usage, session and weekly limits, and permissions in five rows at the bottom of your terminal. CDSL is an independent, unofficial companion for Codex CLI.

![CDSL status display with gpt-6-astra(high), with effort and its parentheses in pink](assets/statusline-preview.png)

The preview uses synthetic values.

- [How it works](#how-it-works)
- [Installation](#installation): requirements, automatic installation, and manual installation
- [Updates](#updates)
- [Maintenance](#maintenance): diagnostics, display reload, uninstallation, and recovery
- [Display and controls](#display-and-controls): rows, permissions, scrolling, and image pasting
- [Configuration and storage](#configuration-and-storage): startup files, official Codex paths, and custom rendering
- [Project information](#project-information): security, license, releases, and repository contents

## How it works

![CDSL startup, local session data, and the two terminal panes](assets/how-it-works.svg)

When you run `codex`, CDSL's external launcher starts official Codex and a separate status process. tmux divides the terminal into an upper pane for Codex and a lower pane for the five-row display. The official Codex executable stays intact.

The status process reads the active conversation's local log, Git information, and saved shortcut settings. It passes that data as JSON to the configured renderer, then displays the returned colored text in the lower pane. Codex's conversation interface and the CDSL display run as separate processes.

`statusLine.command` belongs to CDSL's configuration. The tested Codex 0.153.4 has no setting that embeds an external command's output in its own footer, so CDSL provides the integration.

<details>
<summary>Session matching, refresh timing, and noninteractive commands</summary>

CDSL follows the root conversation being written by the process it launched, excluding subagents and history files opened only for reading. It waits when the conversation is switching or multiple candidates exist.

CDSL normally refreshes once per second. It reads `thread_settings_applied` events recorded after settings changes, so updated permissions appear without another prompt. Events owned by another thread are ignored.

Commands such as `codex exec`, `codex update`, help, and non-TTY invocations pass their arguments directly to official Codex. For interactive sessions, CDSL disables the native status line through a startup argument. An explicit setting supplied later in the user's arguments takes precedence.

</details>

## Installation

### Requirements

- Linux or WSL, with Bash and Git
- Python 3.11 or later
- tmux 3.2 or later, tested with 3.2a and 3.4
- Codex CLI, tested with 0.153.4; sign-in is required before use

Both standalone and npm installations of Codex are supported. macOS, native Windows, and remote Codex connections are outside the supported scope.

For a manual Codex installation, use the [official Codex CLI instructions](https://learn.chatgpt.com/docs/codex/cli). Complete sign-in before using CDSL; if you are not already signed in, run `codex login` and follow the [official authentication steps](https://learn.chatgpt.com/docs/auth).

### Installing with install.sh

With `curl` available, use either method below. The script downloads CDSL into `~/.local/share/cdsl/source` and installs missing packages through apt/dnf. Linux Codex is installed only if it is missing.

**1. Install, then run `codex` in a new Bash terminal**

```bash
curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh
```

**2. Install and activate the current Bash shell**

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) && . "$HOME/.config/cdsl/shell.sh"
```

For later updates, use [Updates](#updates); diagnostics and uninstallation are in [Maintenance](#maintenance).

### Manual installation

First install the required packages and [official Codex](https://learn.chatgpt.com/docs/codex/cli). The Python installer checks required dependencies together before making changes. If any are missing, it lists them and stops without writing files. This command does not install packages automatically: install the required packages using the examples in this section, then retry installation.

<details>
<summary>Package commands for Ubuntu, Debian, and RHEL-based systems</summary>

If the required packages are missing on Ubuntu 24.04 or Debian 12, run:

```bash
sudo apt update
sudo apt install python3 tmux git bash
python3 --version
tmux -V
```

Check that `python3 --version` reports 3.11 or later and `tmux -V` reports 3.2 or later. The standard packages provide [Python 3.12 on Ubuntu 24.04](https://packages.ubuntu.com/noble/python3) and [Python 3.11 on Debian 12](https://packages.debian.org/bookworm/python3).

On RHEL-based systems (such as AlmaLinux and Rocky Linux), choose Python according to the release and enabled repositories. The following examples use official RHEL packages; full functionality has not been verified on a RHEL installation. On a compatible distribution, first confirm that the same packages are available.

The default `python3` in [RHEL 9](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/installing_and_using_dynamic_programming_languages/assembly_installing-and-using-python_installing-and-using-dynamic-programming-languages) is 3.9, which does not meet CDSL's requirements. On RHEL 9.4 and later, use the additional Python 3.12 package:

```bash
sudo dnf install git bash tmux python3.12
python3.12 --version
tmux -V
```

For the initial installation on this RHEL 9 setup, replace `python3` with `python3.12` in the installation commands. Automatic startup uses the interpreter selected during installation; replacing the OS's `python3` is unnecessary.

[RHEL 10](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/installing_and_using_dynamic_programming_languages/installing-and-using-python) provides Python 3.12 as its default:

```bash
sudo dnf install git bash tmux python3
python3 --version
tmux -V
```

Check the [RHEL Application Streams life cycle](https://access.redhat.com/support/policy/updates/rhel-app-streams-life-cycle) for supported releases and Python support periods.

</details>

```bash
git clone https://github.com/takamasa-aiso/cdsl.git
cd cdsl

# Preview the installation changes
python3 scripts/cdsl.py install --codex --dry-run

# Enable automatic startup
python3 scripts/cdsl.py install --codex
```

### Starting Codex

Both installation methods set up startup integration and the rendering command. **No separate rendering configuration is needed for normal use.** Missing settings are created and existing renderer settings are preserved. Keep the downloaded or cloned directory: CDSL runs directly from it.

Open a new Bash terminal, or activate the installing user's current Bash shell if it has not been activated yet. Both installation methods use the same file, and no `cd` is required:

```bash
source "$HOME/.config/cdsl/shell.sh"
```

Start Codex as usual. Resuming a conversation with `codex resume` also shows CDSL.

```bash
codex
```

## Updates

Uninstallation is not required before updating. Exit Codex and run the commands below at the installing user's regular Bash prompt.

### Installed with curl

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

This updates the existing `~/.local/share/cdsl/source`, checks and installs missing dependencies, and activates the current shell before starting Codex. Existing renderer settings are preserved.

### Manual clone or local install.sh

Set `CDSL_DIR` to the actual location of your CDSL checkout. The example below assumes `~/cdsl`; replace it if you installed elsewhere. No `cd` is needed.

```bash
CDSL_DIR="$HOME/cdsl"
git -C "$CDSL_DIR" pull --ff-only &&
  python3 "$CDSL_DIR/scripts/cdsl.py" install --codex &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

The Python installer reports missing dependencies and stops without installing packages. Install the missing packages using [Manual installation](#manual-installation), then rerun the update commands.

Startup and tmux changes, including scrolling behavior, take effect in a newly launched Codex session. `refresh-statusline.py` reloads only the lower display and does not apply these startup changes.

## Maintenance

Use the same user that installed CDSL, and set the source directory once before running these commands.

### Common preparation for maintenance

In the installing user's Bash shell, run one setting from this table. The manual example assumes a clone at `~/cdsl`; replace it with the actual absolute path if yours is elsewhere. When using a local `install.sh`, select the CDSL directory containing that script.

| Installation method | Setting to run |
|---|---|
| `install.sh` through curl | `CDSL_DIR="$HOME/.local/share/cdsl/source"` |
| Manual clone or local `install.sh` | `CDSL_DIR="$HOME/cdsl"` (example) |

The commands in this section use this variable to address scripts by absolute path, so they work from any directory. Set the variable again in a new Bash shell. Use the same user that installed CDSL: root and a regular user have different `HOME` directories.

Even if `python3` remains at 3.9, as on AlmaLinux 9, the management scripts automatically switch to the installation's Python or another available Python 3.11 or later. You do not need to replace the OS's `python3`.

Both installation methods use the same user's startup integration and management state. Diagnostics also check the selected source files, so select the directory actually used for installation.

### Diagnostics

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
```

`doctor` runs the same prerequisite checks as the installer and reports `OK` or `NG` for each item, with details of any problems. It does not change settings or repair them automatically, and it can also run before installation.

| Diagnostic item | What it checks |
|---|---|
| Runtime environment | Linux / WSL, Python 3.11 or later, Bash and Git availability, and tmux 3.2 or later |
| CDSL runtime files | Required Python files exist, can be read, and have valid syntax |
| Official Codex and startup settings | The official Codex executable path and consistency of CDSL's installation state and shell configuration |
| Startup artifacts | The dedicated entry, `shell.sh`, metadata, and managed blocks in each Bash startup file; reports missing, damaged, or modified artifacts and the recovery command |
| Renderer configuration and command | Configuration format and values, and the existence and execute permissions of the first executable in the command |

On WSL, it also reports PowerShell availability for the image clipboard helper as an optional item. PowerShell is not required for the status display.

It does not test Codex sign-in, the renderer's actual output, conversation or usage retrieval, or image pasting. `OK` means the prerequisite check passed; it does not confirm that installation is complete or every feature works.

### Reloading the display

To reload only the lower display while keeping the current Codex session running, execute this from that session:

```bash
python3 "$CDSL_DIR/scripts/refresh-statusline.py"
```

For startup or tmux changes, follow [Updates](#updates) and launch a new Codex session.

### Uninstallation

Exit Codex and run these commands at the installing user's regular Bash prompt.

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex && hash -r
```

`--dry-run` only previews the changes. Uninstallation removes CDSL's managed shell blocks, dedicated entry, `shell.sh`, and startup metadata. If metadata is missing or damaged, artifacts matching CDSL's generated content can still be removed. Before changing or removing an existing file, CDSL backs it up under `~/.local/share/cdsl/backups/` and prints its actual backup path. It reports that no changes are needed only when no startup artifacts remain; unrecognized content stops the operation with exit code 1.

The CDSL source directory, rendering settings, backups, official Codex, and installed OS packages are retained. You do not need to source CDSL again after uninstalling it.

Run `hash -r` in the calling Bash shell to clear CDSL's cached command location; Python cannot clear its parent shell's cache. Opening a new terminal also applies the change. Then check command resolution:

```bash
type -a codex
type -aP codex
```

When the uninstall command can locate official Codex, it prints an absolute path for direct startup. Use that Linux executable if `codex` cannot be found or resolves to another entry, such as a Windows installation on WSL. `hash -r` does not change PATH itself. If no path is printed, use [Finding the official Codex executable](#finding-the-official-codex-executable) or reinstall official Codex.

### Recovering from damaged metadata or modified artifacts

If normal uninstallation cannot identify remaining artifacts because metadata is missing or damaged or contents have changed, inspect them with `doctor`, then explicitly use `--purge`.

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge && hash -r
```

`--purge` is never enabled by default. It targets the dedicated entry, `shell.sh`, and startup metadata at their fixed paths for the installing user, plus CDSL's managed blocks in `.bashrc`, `.bash_profile`, `.bash_login`, and `.profile`. Modified contents are removed only after backing up each entire file. Multiple separate blocks can be removed; content outside them is preserved. The operation stops without writing to symlinks, non-regular targets, or blocks whose boundaries cannot be determined because of nested or missing markers.

After recovery, follow [Installing with install.sh](#installing-with-installsh) again. Rendering settings, source files, and backups are retained during recovery too. Unrelated problems, such as missing packages or errors in existing renderer settings, remain subject to the normal installation checks.

## Display and controls

### Five rows and usage

| Row | Meaning |
|---|---|
| Header | Model and effort when available, working directory, and Git branch and change count when available |
| Context | Context usage in the current conversation: percentage, tokens used, capacity, and cache ratio |
| Session | Account usage of the five-hour limit, plus cumulative tokens in the displayed conversation |
| Weekly | Account usage of the weekly limit and time until reset |
| Permissions | Permission scope and approval policy applied to the current conversation |

Each row starts with two spaces, and one space separates the closing bracket from the next value. Percentage numbers use a minimum width of two characters: `[ 8%]`, `[10%]`, and `[100%]`.

The model appears as `[gpt-6-astra(high)]`. Effort, including its parentheses, uses the same pink as the tallest bars in the Session graph. Effort comes from the current conversation log and applied-settings events; only the model name is shown when effort is unavailable. CDSL does not infer it from global settings. Once a model or effort change is recorded in the log, the display follows it on the default one-second refresh cycle.

Clock times and time ranges use Japan Standard Time (JST, UTC+09:00).

### Understanding limits and graphs

**Session and Weekly percentages describe the account's limits; their graphs show token consumption within the displayed conversation.** Other conversations are not aggregated. CDSL reads usage from Codex's local logs instead of querying the usage API directly.

| Display | Meaning |
|---|---|
| A percentage | Received usage information |
| `[N/A]` | The returned limits do not include the relevant window |
| `[---]` | The percentage has not been received or its recorded period has expired |
| `Permissions: unknown` | Permission information is unavailable or not recognized |
| Waiting message | CDSL cannot identify the active conversation unambiguously |

CDSL identifies limits by `window_minutes`. If the returned limits do not include a five-hour window, Session shows `[N/A]` alongside the available conversation token count. A weekly limit returned in the API's `primary` slot is still displayed under Weekly.

If Codex records the five-hour limit's usage percentage and a valid reset time with `window_minutes = 300` in the current conversation log, Session automatically changes from `[N/A]` to a percentage. No reinstallation or manual configuration is needed. CDSL reads the log on its default one-second refresh cycle and cannot detect the returning limit before the log updates.

<details>
<summary>Why graph bars can move without new usage</summary>

Bar heights show relative consumption in each time interval, scaled between the lowest and highest values in the displayed period. When a reset time is available, the graph covers that limit's period. Without a reset time, such as when Session shows `N/A`, the Session graph uses the preceding five hours. As time passes, interval boundaries move and the scale can change when the largest value leaves the window. Bars can therefore move or change height without new token usage. They do not represent remaining allowance or elapsed time directly.

</details>

### Permissions and shortcuts

The row reads `Permissions: scope | approval policy`. In the standard display, the `Permissions:` label uses `#FFC107`, the warning color in Claude Code's default dark theme. The first configured shortcut appears beside the values, separated by one space:

| Shortcut state | Hint |
|---|---|
| Assigned, for example to `F7` | `(F7 for cycle)` |
| Unassigned | `(/keymap to set cycle key)` |
| Cannot be determined | `(/keymap to check cycle key)` |

In Codex's `/keymap`, assign a key to `next_permission_mode`. Close the menu, then press that key in the Codex input area to cycle permissions. This action is unassigned by default in Codex 0.153.4. Changes appear on CDSL's normal refresh cycle, one second by default, without another prompt. Changes through `/permissions` work the same way; see [How it works](#how-it-works) for session matching.

In the tested [Codex CLI 0.153.4](https://github.com/openai/codex/releases/tag/rust-v0.153.4), `next_permission_mode` cycles through the available Read Only, Ask for approval, and Approve for me modes. Full Access is outside that cycle; select it through `/permissions`. This describes in-session controls; startup flags such as `--yolo` are separate.

Use `/keymap` to change the shortcut in a running Codex session. Editing the configuration file directly does not guarantee that Codex's current interface reloads the binding immediately.

Codex determines the available modes and any confirmation steps. Shortcut changes apply to the current conversation.

`Never` means Codex does not request execution approval. It can run operations within the allowed scope; operations that require approval are denied without an approval prompt. Scope is a separate setting: `Read Only | Never` means read-only access, while `Full Access | Never` means no Codex sandbox restriction and no execution approval requests.

For reducing manual permission prompts through automatic review, `Approve for me` is the closest practical counterpart to Claude Code's `auto` mode. Both can reject actions during review. Codex retains its sandbox and sends eligible approval requests to a reviewer; Claude Code uses its own classifier and rules. This is a comparison of workflows, whose review mechanisms and rules remain distinct. See [Codex Auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review) and [Claude Code auto mode](https://code.claude.com/docs/en/permission-modes#eliminate-permission-prompts-with-auto-mode).

<details>
<summary>Permission scope and approval policy reference</summary>

| Permission scope | Meaning |
|---|---|
| `Read Only` | The built-in read-only profile |
| `Workspace` | Writes are allowed in the workspace and other permitted locations |
| `Full Access` | No Codex sandbox restriction; OS and organizational restrictions still apply |
| `Custom permissions` | A permission configuration that does not match a built-in display label |
| A profile name | The name of the active custom profile |
| `unknown` | Effective permission information is not yet available |

| Approval policy | Meaning |
|---|---|
| `Ask for approval` | Codex asks the user when it determines approval is needed |
| `Approve for me` | Operations requiring approval go through automatic review, which can reject them |
| `Never` | Execution approval is never requested; operations requiring it are denied |
| `On request` | Approval is requested as needed, but the log does not identify the reviewer |
| `Untrusted` | Commands outside the known safe set require approval |
| `Granular` | Approval categories are configured individually to allow a request or reject it automatically |
| `On failure` | Approval to retry outside the sandbox is requested after a sandboxed failure; deprecated in Codex |
| `unknown` | The approval policy is unavailable or not recognized |

</details>

<details>
<summary>Shortcut settings and abbreviated labels</summary>

CDSL reads the saved user keymap from `$CODEX_HOME/config.toml`, normally `~/.codex/config.toml`. When Codex is started with `--profile <name>`, it also reads `<name>.config.toml` in the same directory. If the action is defined in project, system, or command-line settings, or the saved configuration cannot be read reliably, CDSL shows the check hint instead of a key name.

These labels summarize the conversation's effective settings. Use Codex's `/permissions` or `/status` to inspect individual paths and rules. On narrow terminals, labels and graphs are shortened; CDSL can shorten `Permissions:` to `P:`, `Custom permissions` to `Custom`, `Ask for approval` to `Ask`, and `Approve for me` to `Auto review`. Hints shorten to `(F7)`, `(set /keymap)`, or `(check /keymap)`. Permission values can be clipped to keep the hint visible; at extremely narrow widths, the hint is also omitted.

</details>

### Scrolling and text selection

The upper Codex pane supports scrolling through history with the mouse wheel or trackpad. Scroll back to the bottom, or press `q` or `Esc`, to leave history and return to input. The lower CDSL pane stays fixed. To use your terminal's own text selection, hold `Shift` while dragging if your terminal supports it.

### Pasting images

Copy an image and press `Ctrl+v` in the Codex input area. In some environments, `Alt+v` can paste when `Ctrl+v` does not work.

Codex 0.153.4 also provides `Ctrl+Alt+v` as a standard alternate binding. Its standard image-paste keys are fixed, outside the editable actions in `/keymap`. See the [Codex key definitions](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap.rs#L2164).

To see which key reaches Codex, open `/keymap`, select `Inspect keypresses` on the `Debug` tab, and press Enter. Press `Ctrl+c` to leave the inspector. If the key does not arrive, check the terminal's bindings. See the [Codex key inspector](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap_setup/picker.rs#L312).

If clipboard access is unavailable, save the image to a local file and paste its path into the input area to attach it. Confirm that the image is attached before submitting your prompt.

On WSL, CDSL adds a `Ctrl+v` helper that uses available Windows PowerShell to convert clipboard images to PNG attachments, falling back to Codex's standard handling if retrieval fails.

### Legacy terminals

Legacy terminals, such as `TERM=xterm` with no `COLORTERM`, use compatibility output with fixed-width ASCII graphs and basic colors (yellow for Permissions). Select it explicitly with `CDSL_RENDER_MODE=ascii codex`, or select the standard display with `CDSL_RENDER_MODE=unicode codex`.

## Configuration and storage

### Startup files and Codex updates

| Location | Purpose |
|---|---|
| `~/.local/share/cdsl/bin/codex` | CDSL's dedicated startup entry |
| `~/.config/cdsl/shell.sh` | Adds that entry to the front of `PATH` |
| `~/.bashrc` | Loads the integration for interactive Bash shells |
| Bash login configuration | Adds a managed block to the file Bash uses, following `.bash_profile`, `.bash_login`, `.profile` precedence |
| `~/.config/cdsl/config.toml` | Rendering command and refresh interval |
| `~/.local/share/cdsl/startup.json` | Installation state used for updates and uninstallation |
| `~/.local/share/cdsl/backups/` | Copies of changed files saved with permissions `0600` |

CDSL's entry remains in place when the official Codex installer replaces its own entry. Standalone installations retain the `current` path; npm installations retain the selected executable path. Updates at the same installation location are picked up automatically.

If Codex moves to a different location, for example after switching Node versions, rerun the installer with `--real-codex` pointing to the new path. Changes to Codex's log format or CLI behavior may require a CDSL update.

The installer preserves existing shell configuration and changes only its managed blocks. It saves backups with file permissions `0600`. If a managed block has been edited externally or a shell configuration file is a symbolic link, installation stops with an error instead of overwriting it.

### Finding the official Codex executable

Codex's location depends on how it was installed and configured. These are common examples:

| Installation | Example official Codex entry |
|---|---|
| Standalone | `~/.local/bin/codex` links to `~/.codex/packages/standalone/current/bin/codex` |
| Global npm installation | `<prefix>/bin/codex`, for example `/usr/local/bin/codex` |
| npm with an nvm-managed Node version | `~/.nvm/versions/node/<version>/bin/codex` |

In Bash on Linux, check the actual candidates with the following commands. `type -a` includes functions and aliases; `type -aP` lists executable files on `PATH`.

```bash
type -a codex
type -aP codex
```

For npm installations, find `<prefix>` with:

```bash
npm prefix -g
```

To inspect a candidate's symlink target, substitute its actual path:

```bash
readlink -f "$HOME/.local/bin/codex"
```

After CDSL is installed, its dedicated `~/.local/share/cdsl/bin/codex` entry may appear first. Do not pass that entry to `--real-codex`; select an official Codex executable from the candidates. Use an entry that remains at the same location across updates, rather than a version-specific internal path shown by `readlink`.

CDSL prefers the standalone installation's `current` entry, then searches `PATH`. After [setting `CDSL_DIR`](#common-preparation-for-maintenance), you can select the official executable explicitly when needed:

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" install --codex --real-codex "$HOME/.local/bin/codex"
```

This example uses a common standalone path. If your installation is elsewhere, substitute the official entry you identified.

If you move the CDSL source directory, rerun the installer from the new location and update `command` in the [rendering configuration](#custom-rendering) to the new absolute path. The installer preserves existing rendering settings.

### Custom rendering

**No separate configuration is needed after following the installation steps.** When the file is missing, `install --codex` creates `~/.config/cdsl/config.toml` with the absolute paths of the Python interpreter used for installation and the bundled renderer. Existing settings are preserved.

The following example is a reference for customizing the renderer or refresh interval. You do not need to copy or run it during normal installation:

```toml
[statusLine]
command = ["/usr/bin/python3", "/absolute/path/to/cdsl/scripts/statusline.py"]
timeout_seconds = 2.0
refresh_interval = 1.0
```

The Python and clone paths in the example vary by environment. To use a different configuration file, create it yourself and set `CDSL_CONFIG` to its path; that file is not created automatically. `command` is an argument array executed without a shell, so `~`, variables, pipes, and other shell syntax are not expanded.

<details>
<summary>JSON protocol for custom renderers</summary>

CDSL uses a version 1 JSON protocol. The integration sends a request on standard input, and the renderer returns UTF-8 text with ANSI formatting on standard output:

```json
{
  "version": 1,
  "session": {
    "now": "2026-01-01T12:00:00+09:00",
    "model": "example-model",
    "cwd": "/workspace/project",
    "context_tokens": 91800,
    "context_window": 200000,
    "weekly_used_percent": 64
  },
  "terminal": {"columns": 100, "rows": 24, "color": true}
}
```

`session` contains normalized usage, Git, and permission information. `session.now` supplies the rendering time; the default renderer does not read session logs or the clock independently. `terminal.rows` carries screen information for the protocol. The default renderer always produces five rows.

Standard output and standard error are each limited to 64 KiB. Timeouts and command failures are reported in the display area while Codex remains usable.

</details>

## Project information

### Reporting security issues

Please report security issues through [GitHub private vulnerability reporting](https://github.com/takamasa-aiso/cdsl/security/advisories/new). See [SECURITY.md](SECURITY.md) for the information to include and how to handle sensitive details.

### Credits and license

- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Codex approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)
- [Codex 0.153.4 permission shortcuts](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/chatwidget/permission_shortcuts.rs)
- [Official Codex installer](https://github.com/openai/codex/blob/rust-v0.153.4/scripts/install/install.sh)

CDSL's copyright notices and MIT license terms are in [LICENSE](LICENSE). The CCSL-derived portions, their source, original copyright notice, and license terms are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Attribution does not imply endorsement by OpenAI or the CCSL author.

### Release notes policy

Each CDSL version published through [GitHub Releases](https://github.com/takamasa-aiso/cdsl/releases) includes the following three sections, with Japanese first and English alongside it:

| Section | Required content |
|---|---|
| 変更内容 / Changes | Additions, fixes, and user-facing changes since the previous release; main features for the first release |
| 対応するCodexのバージョン / Codex compatibility | The Codex CLI versions actually tested; untested versions are not described as supported |
| 既知の制限 / Known limitations | Platform, data, display, and performance constraints, plus unresolved issues and workarounds; explicitly state when none apply |

Each release tags the commit being published, and its notes describe that version. Release history belongs in Releases; this README describes current behavior and usage.

<details>
<summary>Repository contents</summary>

| Location | Purpose |
|---|---|
| `cdsl/` | Startup integration, session collection, rendering, and clipboard handling |
| `install.sh` | Entry point for downloading and installing CDSL |
| `scripts/setup.sh` | Dependency installation and CDSL setup in Bash |
| `scripts/cdsl.py` | Entry point for installation, diagnostics, uninstallation, and startup |
| `scripts/statusline.py` | Converts JSON into colored display text |
| `scripts/paste-image.py` | Entry point for the WSL clipboard helper |
| `scripts/refresh-statusline.py` | Reloads only the display in a running session |
| `assets/statusline-preview.png` | Example rendered by the current CDSL renderer |
| `assets/how-it-works.ja.png` | Japanese diagram of startup, local data flow, and terminal panes |
| `assets/how-it-works.svg` | English diagram of the same architecture |
| `README.md`, `README.en.md` | Japanese and English usage documentation |
| `SECURITY.md` | How to report security issues privately |
| `THIRD_PARTY_NOTICES.md` | CCSL-derived portions, source attribution, original copyright notice, and license terms |
| `LICENSE` | License terms and copyright notices |

</details>
