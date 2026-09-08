#!/bin/sh
# Bootstrap CDSL from a local checkout or from a script received on standard input.
# Keep the entire operation in a subshell; children must not consume this script.
(
    cdsl_repo=https://github.com/takamasa-aiso/cdsl.git
    cdsl_ref=main
    cdsl_dry_run=0
    cdsl_python=''
    cdsl_real_codex=''
    cdsl_root=''
    cdsl_stage=''
    cdsl_lock_owned=0

    _cdsl_fail() {
        printf 'CDSL: %s\n' "$*" >&2
        exit 1
    }

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --help|-h)
                printf '%s\n' \
                    'Usage: curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh' \
                    'Options: --dry-run, --ref NAME, --python PATH, --real-codex PATH' \
                    'For options, pipe to: sh -s -- --dry-run' \
                    'Installs CDSL and missing dependencies. Bash and Git are installed if needed.' \
                    'Remote installs use ~/.local/share/cdsl/source; --ref defaults to main.' \
                    'For installation and activation together in your current Bash shell:' \
                    '  (set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) && . "$HOME/.config/cdsl/shell.sh"'
                exit 0
                ;;
            --dry-run) cdsl_dry_run=1; shift ;;
            --ref|--python|--real-codex)
                [ "$#" -ge 2 ] && [ -n "$2" ] || _cdsl_fail "$1 requires a value."
                case "$2" in -*) _cdsl_fail "$1 requires a value." ;; esac
                case "$1" in
                    --ref) cdsl_ref=$2 ;;
                    --python) cdsl_python=$2 ;;
                    --real-codex) cdsl_real_codex=$2 ;;
                esac
                shift 2
                ;;
            --) shift; [ "$#" -eq 0 ] || _cdsl_fail 'Unexpected positional arguments.' ;;
            *) _cdsl_fail "Unknown option: $1" ;;
        esac
    done

    [ "$(uname -s)" = Linux ] || _cdsl_fail 'Linux or WSL is required.'
    case "${HOME-}" in /*) ;; *) _cdsl_fail 'An absolute HOME directory is required.' ;; esac
    cdsl_uid=$(id -u) || _cdsl_fail 'Could not determine the current user.'
    if [ "$cdsl_uid" -eq 0 ] && [ -n "${SUDO_USER-}" ]; then
        _cdsl_fail 'Run this as your normal user. Only package installation uses sudo.'
    fi
    if [ "${CDSL_WRAPPED-}" = 1 ] && [ "$cdsl_dry_run" -eq 0 ]; then
        _cdsl_fail 'Run this at your regular terminal prompt, outside an active CDSL session.'
    fi

    # A piped shell has no script pathname. Local execution can reuse its checkout.
    cdsl_entry=${BASH_SOURCE:-$0}
    case "$cdsl_entry" in
        */*) cdsl_entry_dir=${cdsl_entry%/*} ;;
        install.sh) cdsl_entry_dir=. ;;
        *) cdsl_entry_dir='' ;;
    esac
    if [ -n "$cdsl_entry_dir" ] && [ -f "$cdsl_entry" ] && \
       [ -f "$cdsl_entry_dir/scripts/setup.sh" ] && [ -f "$cdsl_entry_dir/cdsl/auto_setup.py" ]; then
        cdsl_root=$(CDPATH= cd -- "$cdsl_entry_dir" && pwd -P) || _cdsl_fail 'Could not locate the CDSL checkout.'
    fi

    _cdsl_privileged() {
        if [ "$cdsl_uid" -eq 0 ]; then
            command "$@"
        else
            command -v sudo >/dev/null 2>&1 || _cdsl_fail 'sudo is missing. Ask your administrator to install Bash and Git, then retry.'
            command sudo "$@"
        fi
    }

    # The downloaded Bash setup script handles the remaining runtime dependencies.
    set --
    command -v bash >/dev/null 2>&1 || set -- "$@" bash
    command -v git >/dev/null 2>&1 || set -- "$@" git
    if [ "$#" -gt 0 ]; then
        printf 'CDSL: Required bootstrap packages: %s\n' "$*"
        if [ "$cdsl_dry_run" -eq 0 ]; then
            if command -v apt-get >/dev/null 2>&1; then
                _cdsl_privileged apt-get update || _cdsl_fail 'Package index update failed.'
                _cdsl_privileged apt-get install -y -- "$@" || _cdsl_fail 'Package installation failed.'
            elif command -v dnf >/dev/null 2>&1; then
                _cdsl_privileged dnf install -y -- "$@" || _cdsl_fail 'Package installation failed.'
            else
                _cdsl_fail 'Automatic package installation requires apt-get or dnf. Install Bash and Git manually.'
            fi
        fi
    fi

    set --
    [ "$cdsl_dry_run" -eq 0 ] || set -- "$@" --dry-run
    [ -z "$cdsl_python" ] || set -- "$@" --python "$cdsl_python"
    [ -z "$cdsl_real_codex" ] || set -- "$@" --real-codex "$cdsl_real_codex"
    if [ "$cdsl_dry_run" -eq 1 ]; then
        if [ -n "$cdsl_root" ] && command -v bash >/dev/null 2>&1; then
            command bash "$cdsl_root/scripts/setup.sh" "$@" || exit 1
        else
            printf 'Would fetch %s (ref: %s) into %s\n' "$cdsl_repo" "$cdsl_ref" "$HOME/.local/share/cdsl/source"
            printf '%s\n' 'Then: check and install runtime dependencies, install official Codex if missing, and configure CDSL.'
        fi
        printf '%s\n' 'CDSL: Preview complete. No packages, checkouts, or settings were changed.'
        exit 0
    fi
    command -v bash >/dev/null 2>&1 && command -v git >/dev/null 2>&1 || \
        _cdsl_fail 'Bash or Git is still missing after package installation.'

    if [ -z "$cdsl_root" ]; then
        cdsl_data=$HOME/.local/share/cdsl
        cdsl_destination=$cdsl_data/source
        [ ! -L "$cdsl_destination" ] || _cdsl_fail 'The managed source directory must not be a symbolic link.'
        if [ -e "$cdsl_destination" ] && [ ! -d "$cdsl_destination" ]; then
            _cdsl_fail 'The managed source path is not a directory.'
        fi
        (umask 077; mkdir -p -- "$cdsl_data") || _cdsl_fail 'Could not create the CDSL data directory.'
        cdsl_lock=$cdsl_data/.install-lock
        mkdir -- "$cdsl_lock" 2>/dev/null || \
            _cdsl_fail "Another installer may be running. If none is running, remove the empty lock directory: $cdsl_lock"
        cdsl_lock_owned=1
        _cdsl_cleanup() {
            if [ -n "$cdsl_stage" ]; then
                rm -rf -- "$cdsl_stage"
            fi
            if [ "$cdsl_lock_owned" -eq 1 ]; then
                rmdir -- "$cdsl_lock" 2>/dev/null || :
            fi
        }
        trap '_cdsl_cleanup' 0
        trap 'exit 130' 2
        trap 'exit 143' 1 15
        # Do not inherit repository redirection from a caller's Git environment.
        unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
        GIT_TERMINAL_PROMPT=0
        GIT_OPTIONAL_LOCKS=0
        export GIT_TERMINAL_PROMPT GIT_OPTIONAL_LOCKS
        _cdsl_git() {
            command git -c core.hooksPath=/dev/null -c core.fsmonitor=false "$@"
        }
        _cdsl_git check-ref-format --branch "$cdsl_ref" >/dev/null || _cdsl_fail 'Invalid repository ref.'
        if [ -d "$cdsl_destination" ]; then
            [ -d "$cdsl_destination/.git" ] && [ ! -L "$cdsl_destination/.git" ] || \
                _cdsl_fail 'The existing source directory is not a regular Git checkout.'
            cdsl_root=$(CDPATH= cd -- "$cdsl_destination" && pwd -P) || exit 1
            cdsl_top=$(_cdsl_git -C "$cdsl_root" rev-parse --show-toplevel) || exit 1
            [ "$cdsl_top" = "$cdsl_root" ] || _cdsl_fail 'The existing checkout points outside the source directory.'
            cdsl_origin=$(_cdsl_git -C "$cdsl_root" remote get-url origin) || exit 1
            case "$cdsl_origin" in
                https://github.com/takamasa-aiso/cdsl|https://github.com/takamasa-aiso/cdsl.git|git@github.com:takamasa-aiso/cdsl.git|ssh://git@github.com/takamasa-aiso/cdsl.git) ;;
                *) _cdsl_fail 'The existing source directory belongs to a different repository.' ;;
            esac
            cdsl_changes=$(_cdsl_git -C "$cdsl_root" status --porcelain --untracked-files=no) || exit 1
            [ -z "$cdsl_changes" ] || _cdsl_fail 'The existing source checkout has local changes. Keep or commit them before retrying.'
            # Running CDSL may create untracked Python bytecode; keep other files protected.
            cdsl_changes=$(_cdsl_git -C "$cdsl_root" status --porcelain --untracked-files=all -- . \
                ':(glob,exclude)**/__pycache__/**' ':(glob,exclude)**/*.py[co]') || exit 1
            [ -z "$cdsl_changes" ] || _cdsl_fail 'The existing source checkout has local changes. Keep or commit them before retrying.'
            _cdsl_git -C "$cdsl_root" fetch origin "$cdsl_ref" || _cdsl_fail 'Could not fetch CDSL.'
            _cdsl_git -C "$cdsl_root" merge-base --is-ancestor HEAD FETCH_HEAD || \
                _cdsl_fail 'The requested ref is not a fast-forward update. The checkout was not reset.'
            _cdsl_git -C "$cdsl_root" merge --ff-only --no-overwrite-ignore FETCH_HEAD || _cdsl_fail 'Could not update CDSL.'
        else
            cdsl_stage=$(mktemp -d "$cdsl_data/.source.XXXXXXXX") || _cdsl_fail 'Could not create a temporary checkout.'
            _cdsl_git clone --branch "$cdsl_ref" --single-branch "$cdsl_repo" "$cdsl_stage/source" || _cdsl_fail 'Could not clone CDSL.'
            [ -f "$cdsl_stage/source/scripts/setup.sh" ] && [ -f "$cdsl_stage/source/cdsl/auto_setup.py" ] || \
                _cdsl_fail 'The selected ref does not contain the CDSL setup files.'
            mv -Tn -- "$cdsl_stage/source" "$cdsl_destination" || _cdsl_fail 'Could not publish the source checkout.'
            [ ! -e "$cdsl_stage/source" ] || _cdsl_fail 'The source destination appeared during installation; it was preserved.'
            cdsl_root=$(CDPATH= cd -- "$cdsl_destination" && pwd -P) || exit 1
        fi
    fi
    [ -f "$cdsl_root/scripts/setup.sh" ] || _cdsl_fail 'The selected checkout has no setup script.'
    if ! command bash "$cdsl_root/scripts/setup.sh" "$@"; then
        _cdsl_fail 'Setup did not complete. Downloaded source and installed dependencies are retained; resolve the error and rerun the installer.'
    fi
) </dev/null
