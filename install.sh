#!/usr/bin/env bash
# Source this file so activation applies to the calling Bash shell.

if [ -z "${BASH_VERSION:-}" ]; then
    printf '%s\n' 'CDSL: Open Bash and run: source ./install.sh' >&2
    return 1 2>/dev/null || exit 1
fi
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    printf 'CDSL: Run this in your current Bash shell: source %q\n' "${BASH_SOURCE[0]}" >&2
    exit 1
fi
if declare -F _cdsl_install_main >/dev/null; then
    printf '%s\n' 'CDSL: The shell function _cdsl_install_main already exists.' >&2
    return 1
fi

_cdsl_install_main() {
    local cdsl_dry_run=0 cdsl_python_option='' cdsl_real_codex=''
    local cdsl_source=${BASH_SOURCE[0]} cdsl_root cdsl_kind
    local -a cdsl_args=()
    while (( $# )); do
        case $1 in
            --help|-h)
                printf '%s\n' \
                    'Usage: source ./install.sh [--dry-run] [--python PATH] [--real-codex PATH]' \
                    'Installs missing dependencies with apt-get/dnf, configures CDSL, and activates this Bash shell.' \
                    'If official Codex is missing, installs the tested standalone release 0.153.4.' \
                    'Sudo may prompt for your password. Complete Codex sign-in on first launch if needed.' \
                    '--dry-run previews changes without installing packages or changing settings.'
                return 0
                ;;
            --dry-run) cdsl_dry_run=1; cdsl_args+=(--dry-run); shift ;;
            --python|--real-codex)
                if (( $# < 2 )) || [[ -z $2 || $2 == --* ]]; then
                    printf 'CDSL: %s requires a value.\n' "$1" >&2
                    return 1
                fi
                if [[ $1 == --python ]]; then
                    cdsl_python_option=$2
                else
                    cdsl_real_codex=$2
                    cdsl_args+=(--real-codex "$2")
                fi
                shift 2
                ;;
            --) shift; if (( $# )); then printf '%s\n' 'CDSL: Unexpected positional arguments.' >&2; return 1; fi ;;
            *) printf 'CDSL: Unknown option: %s\n' "$1" >&2; return 1 ;;
        esac
    done
    if [[ ${OSTYPE-} != linux* || ${HOME-} != /* ]]; then
        printf '%s\n' 'CDSL: Linux/WSL and an absolute HOME directory are required.' >&2
        return 1
    fi
    if (( EUID == 0 )) && [[ -n ${SUDO_USER-} ]]; then
        printf '%s\n' 'CDSL: Source this script as your normal user, without sudo. Only package commands use sudo.' >&2
        return 1
    fi
    cdsl_kind=$(builtin type -t codex || :)
    if [[ $cdsl_kind == alias || $cdsl_kind == function ]]; then
        printf '%s\n' 'CDSL: A codex alias or function overrides PATH. Rename or remove it before running this installer.' >&2
        return 1
    fi
    if [[ ${CDSL_WRAPPED-} == 1 && $cdsl_dry_run == 0 ]]; then
        printf '%s\n' 'CDSL: Run this at your regular Bash prompt, outside an active CDSL session.' >&2
        return 1
    fi
    [[ $cdsl_source == */* ]] || cdsl_source=./$cdsl_source
    cdsl_root=$(cd -- "${cdsl_source%/*}" && pwd -P) || return 1
    if [[ ! -f $cdsl_root/scripts/cdsl.py || ! -f $cdsl_root/cdsl/auto_setup.py ]]; then
        printf '%s\n' 'CDSL: Keep install.sh in the complete cloned or extracted CDSL directory.' >&2
        return 1
    fi

    # Keep helper functions, temporary PATH changes, and traps out of the caller.
    if (
        cdsl_python='' cdsl_manager='' cdsl_apt_updated=0 cdsl_download=''
        cdsl_codex_bin=${CODEX_INSTALL_DIR:-$HOME/.local/bin}
        cdsl_packages=() cdsl_privilege=()

        _cdsl_python() {
            local cdsl_candidate cdsl_executable
            for cdsl_candidate in "${cdsl_python_option:-python3}" python3.14 python3.13 python3.12 python3.11; do
                cdsl_executable=$(type -P -- "$cdsl_candidate") || cdsl_executable=''
                if [[ -n $cdsl_executable ]] && "$cdsl_executable" -B -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
                    printf '%s\n' "$cdsl_executable"
                    return 0
                fi
                [[ -z $cdsl_python_option ]] || break
            done
            return 1
        }

        _cdsl_tmux_ok() {
            local cdsl_version
            cdsl_version=$(command tmux -V 2>/dev/null) || return 1
            [[ $cdsl_version =~ ^tmux\ (next-)?([0-9]+)\.([0-9]+) ]] || return 1
            (( BASH_REMATCH[2] > 3 || (BASH_REMATCH[2] == 3 && BASH_REMATCH[3] >= 2) ))
        }

        _cdsl_packages() {
            (( $# )) || return 0
            if command -v apt-get >/dev/null; then
                cdsl_manager=apt-get
            elif command -v dnf >/dev/null; then
                cdsl_manager=dnf
            else
                printf '%s\n' 'CDSL: Automatic package installation requires apt-get or dnf. Install the listed dependencies manually.' >&2
                printf 'Missing packages: %s\n' "$*" >&2
                return 1
            fi
            printf 'CDSL: Required packages: %s\n' "$*"
            if (( cdsl_dry_run )); then
                printf 'Would run: %s install -y' "$cdsl_manager"
                printf ' %q' "$@"
                printf '\n'
                return 0
            fi
            if (( EUID != 0 )); then
                if ! command -v sudo >/dev/null; then
                    printf '%s\n' 'CDSL: sudo is missing. Ask your administrator to install the listed packages, then retry as your normal user.' >&2
                    return 1
                fi
                cdsl_privilege=(sudo)
            fi
            if [[ $cdsl_manager == apt-get && $cdsl_apt_updated == 0 ]]; then
                command "${cdsl_privilege[@]}" apt-get update || return 1
                cdsl_apt_updated=1
            fi
            command "${cdsl_privilege[@]}" "$cdsl_manager" install -y -- "$@" || return 1
        }

        # Exit 1 means a clean installation needs official Codex; 2 means an error.
        _cdsl_probe() {
            "$cdsl_python" -B - "$cdsl_root" "$cdsl_real_codex" "$cdsl_dry_run" <<'PY'
import sys
import os
import subprocess
from pathlib import Path
sys.path.insert(0, sys.argv[1])
explicit = sys.argv[2] or None
try:
    from cdsl.auto_setup import inspect_installation
    from cdsl.startup import resolve_real_codex
    inspection = inspect_installation(real_codex=explicit)
except Exception as error:
    print('CDSL: Cannot validate this installation: ' + str(error), file=sys.stderr)
    sys.exit(2)
failures = [item for item in inspection['checks'] if not item['ok']]
if not failures:
    # Even --version can initialize Codex's local cache. Keep previews read-only.
    if sys.argv[3] == '1':
        sys.exit(0)
    try:
        subprocess.run([inspection['startup']['real_codex'], '--version'],
                       check=True, stdout=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.SubprocessError):
        print('CDSL: Official Codex cannot run --version. Check its runtime dependencies or use --real-codex.', file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
if len(failures) == 1 and failures[0]['name'] == 'Official Codex and startup configuration':
    state = Path.home() / '.local/share/cdsl/startup.json'
    if explicit is None and not state.exists() and not state.is_symlink():
        try:
            resolve_real_codex()
        except ValueError:
            codex_home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
            current = codex_home / 'packages/standalone/current'
            if current.exists() or current.is_symlink():
                print('CDSL: An existing standalone Codex installation is incomplete. Repair it or use --real-codex.', file=sys.stderr)
                sys.exit(2)
            sys.exit(1)
for item in failures:
    print('CDSL: ' + item['name'] + ': ' + item.get('detail', 'Check the requirements.'), file=sys.stderr)
sys.exit(2)
PY
        }

        cdsl_python=$(_cdsl_python) || cdsl_python=''
        if [[ -n $cdsl_python_option && -z $cdsl_python ]]; then
            printf '%s\n' 'CDSL: --python must select an installed Python 3.11 or later.' >&2
            return 1
        fi
        if [[ -z $cdsl_python ]]; then
            cdsl_python_package=python3
            if ! command -v apt-get >/dev/null && command -v dnf >/dev/null && [[ -r /etc/os-release ]]; then
                cdsl_platform=$(
                    . /etc/os-release
                    cdsl_version=${VERSION_ID-}
                    printf '%s:%s' "${ID-} ${ID_LIKE-}" "${cdsl_version%%.*}"
                ) || return 1
                if [[ $cdsl_platform == *:9 && $cdsl_platform == *rhel* ]]; then
                    cdsl_python_package=python3.12
                fi
            fi
            cdsl_packages+=("$cdsl_python_package")
        fi
        command -v git >/dev/null || cdsl_packages+=(git)
        _cdsl_tmux_ok || cdsl_packages+=(tmux)
        command -v bwrap >/dev/null || cdsl_packages+=(bubblewrap)
        if ! _cdsl_packages "${cdsl_packages[@]}"; then
            printf '%s\n' 'CDSL: Package installation failed. CDSL settings have not been changed.' >&2
            return 1
        fi
        if (( cdsl_dry_run && ${#cdsl_packages[@]} )); then
            printf '%s\n' 'Then: recheck dependencies, validate CDSL settings, install Codex 0.153.4 if missing, configure CDSL, and activate this Bash shell.'
            return 0
        fi
        hash -r
        cdsl_python=$(_cdsl_python) || cdsl_python=''
        if [[ -z $cdsl_python ]] || ! _cdsl_tmux_ok || ! command -v git >/dev/null || ! command -v bwrap >/dev/null; then
            printf '%s\n' 'CDSL: Dependencies are still unavailable or too old on PATH. Python 3.11+, tmux 3.2+, Git, and bubblewrap are required. CDSL settings have not been changed.' >&2
            return 1
        fi
        cdsl_probe_status=0
        _cdsl_probe || cdsl_probe_status=$?
        if (( cdsl_probe_status > 1 )); then
            return 1
        fi
        if (( cdsl_probe_status == 1 )); then
            if [[ $cdsl_codex_bin != /* || -e $cdsl_codex_bin/codex || -L $cdsl_codex_bin/codex ]]; then
                printf '%s\n' 'CDSL: CODEX_INSTALL_DIR must be absolute and its codex entry must be absent. Check the existing entry or use --real-codex.' >&2
                return 1
            fi
            cdsl_packages=()
            command -v curl >/dev/null || cdsl_packages+=(curl)
            command -v tar >/dev/null || cdsl_packages+=(tar)
            command -v gzip >/dev/null || cdsl_packages+=(gzip)
            command -v awk >/dev/null || cdsl_packages+=(gawk)
            command -v sed >/dev/null || cdsl_packages+=(sed)
            command -v grep >/dev/null || cdsl_packages+=(grep)
            command -v find >/dev/null || cdsl_packages+=(findutils)
            for cdsl_tool in mktemp sha256sum uname cat chmod mkdir mv ln rm cp readlink cut tr head basename dirname date sleep fold; do
                if ! command -v "$cdsl_tool" >/dev/null; then
                    cdsl_packages+=(coreutils)
                    break
                fi
            done
            if [[ ! -s /etc/ssl/certs/ca-certificates.crt && ! -s /etc/pki/tls/certs/ca-bundle.crt ]]; then
                cdsl_packages+=(ca-certificates)
            fi
            _cdsl_packages "${cdsl_packages[@]}" || return 1
            if (( cdsl_dry_run )); then
                printf '%s\n' 'Would download https://chatgpt.com/codex/install.sh and install Codex 0.153.4 as the current user.' 'Then: validate and install CDSL and activate this Bash shell.'
                return 0
            fi
            cdsl_download=$(mktemp "${TMPDIR:-/tmp}/cdsl-codex-install.XXXXXXXX") || return 1
            trap 'rm -f -- "$cdsl_download"' EXIT
            trap 'exit 130' INT
            trap 'exit 143' TERM HUP
            printf '%s\n' 'CDSL: Installing official Codex 0.153.4 for the current user.'
            command curl -fsSL --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 120 \
                https://chatgpt.com/codex/install.sh -o "$cdsl_download" || return 1
            # Avoid adding an extra shell-startup block in the official installer.
            PATH="$cdsl_codex_bin:$PATH" CODEX_INSTALL_DIR="$cdsl_codex_bin" CODEX_NON_INTERACTIVE=1 \
                sh "$cdsl_download" --release 0.153.4 || return 1
            _cdsl_probe || return 1
        fi
        if (( cdsl_dry_run )); then
            "$cdsl_python" "$cdsl_root/scripts/cdsl.py" install --codex "${cdsl_args[@]}" || return 1
        else
            # Activation below replaces the CLI's new-terminal success hint.
            "$cdsl_python" "$cdsl_root/scripts/cdsl.py" install --codex "${cdsl_args[@]}" >/dev/null || return 1
        fi
    ); then
        if (( cdsl_dry_run )); then
            printf '%s\n' 'CDSL: Preview complete. No packages or settings were changed; this shell was not activated.'
            return 0
        fi
        # The generated hook also clears Bash's cached codex command path.
        . "$HOME/.config/cdsl/shell.sh" || return 1
        if [[ $(type -P codex) != "$HOME/.local/share/cdsl/bin/codex" ]]; then
            printf '%s\n' 'CDSL: Installed, but codex does not resolve to the CDSL entry. Check your PATH.' >&2
            return 1
        fi
        printf '%s\n' 'CDSL is ready in this Bash terminal. Run: codex' 'Complete Codex sign-in on first launch if prompted.'
        return 0
    else
        printf '%s\n' 'CDSL: Installation did not complete; this shell was not activated. Any packages or official Codex already installed are retained. Resolve the error and source install.sh again.' >&2
        return 1
    fi
}

if _cdsl_install_main "$@"; then
    unset -f _cdsl_install_main
    return 0
else
    unset -f _cdsl_install_main
    return 1
fi
