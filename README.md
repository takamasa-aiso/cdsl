# CDSL (CoDex StatusLine)

日本語 | [English](README.en.md)

通常の`codex`起動に、CCSLを基にしたステータス表示を追加します。モデルとeffort、コンテキスト、利用枠、権限を端末の下部5行にまとめる、非公式のCodex CLI向けツールです。

![CDSLの表示例：gpt-6-astra(high)、括弧を含むeffortはピンク色](assets/statusline-preview.png)

数値は説明用のサンプルです。

- [呼び出しの仕組み](#呼び出しの仕組み)
- [インストール](#インストール)：対応環境・自動導入・手動導入
- [アップデート](#アップデート)
- [管理操作](#管理操作)：診断・表示の再読み込み・アンインストール・復旧
- [表示と操作](#表示と操作)：各行の意味・Permissions・スクロール・画像貼り付け
- [設定と保存先](#設定と保存先)：起動連携・公式Codexのパス・描画のカスタマイズ
- [プロジェクト情報](#プロジェクト情報)：セキュリティ・ライセンス・Release・配布ファイル

## 呼び出しの仕組み

![CDSLの起動、ローカルデータの受け渡し、端末の上下領域](assets/how-it-works.ja.png)

`codex`を実行すると、CDSLの外部ランチャーが公式Codexとステータス表示用の処理を起動します。tmuxが端末を上下に分け、上段にCodex、下段に5行のCDSLを配置します。公式Codexの実行ファイルは変更しません。

CDSLは現在の会話のローカルログ、Git情報、保存されたキー設定を読み、JSONとして描画プログラムへ渡します。返ってきた色付き文字列を下段に表示します。`statusLine.command`はCDSL独自の設定です。検証対象のCodex 0.153.4には、外部コマンドの出力を本体のステータス欄へ埋め込む設定がないため、CDSLが呼び出し役を担います。

<details>
<summary>会話の識別・更新・非対話コマンドの扱い</summary>

通常は1秒ごとに更新します。起動したプロセスが書き込み中の親会話ログを追跡し、子エージェントや読み取り用に開かれた履歴を除外します。会話切替中や候補が複数あるときは、別の会話を推測して表示しません。

`/permissions`や権限切替ショートカットの変更後に記録される`thread_settings_applied`を読み、次のプロンプトを待たずにPermissionsへ反映します。別スレッドが所有する設定イベントは取り込みません。

`codex exec`、`codex update`、ヘルプ、非TTY実行などは公式Codexへ引数をそのまま渡します。対話セッションではCodex標準のstatuslineを起動引数で非表示にしますが、ユーザーが後から渡した同じ設定の引数が優先されます。

</details>

## インストール

### 対応環境

| 項目 | 要件 |
|---|---|
| OS・シェル | Linux / WSL、Bash |
| Python | 3.11以上 |
| tmux | 3.2以上（3.2a・3.4で検証） |
| その他 | Git、導入・ログイン済みのCodex CLI（0.153.4で検証） |

Codexのstandalone版とnpm版に対応します。macOS、Windowsネイティブ版、リモートCodex接続は対象外です。

以下の`install.sh`は不足パッケージとLinux版Codexを導入できます。手動で導入する場合は、先に必要なパッケージを用意してください。

### install.shで導入する

`curl`が使える環境で実行します。本体を`~/.local/share/cdsl/source`へ取得し、apt/dnfで不足パッケージを導入します。Linux版Codexがなければ併せて導入します。

**インストールのみ（完了後は新しいBashで起動）**

```bash
curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh
```

**インストールして現在のBashへも反映**

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) && . "$HOME/.config/cdsl/shell.sh"
```

### 手動で導入する

先に対応環境をそろえ、公式Codexを[公式の導入手順](https://learn.chatgpt.com/docs/codex/cli)でインストールします。以下のPythonコマンドは依存関係を確認し、不足があれば一覧を表示して変更前に停止します。パッケージは自動導入しません。

<details>
<summary>OS別のパッケージ導入例</summary>

**Ubuntu 24.04 / Debian 12**

```bash
sudo apt update
sudo apt install python3 tmux git bash
python3 --version
tmux -V
```

`python3`が3.11以上、`tmux`が3.2以上であることを確認します。標準パッケージは[Ubuntu 24.04がPython 3.12](https://packages.ubuntu.com/noble/python3)、[Debian 12がPython 3.11](https://packages.debian.org/bookworm/python3)です。

**RHEL系（AlmaLinux、Rocky Linuxなど）**

以下はRHELの公式パッケージに基づく例です。RHEL実機での全機能検証は行っていません。互換ディストリビューションでは、同じパッケージが提供されていることを確認してください。

[RHEL 9](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/installing_and_using_dynamic_programming_languages/assembly_installing-and-using-python_installing-and-using-dynamic-programming-languages)の標準`python3`は3.9です。9.4以降では追加のPython 3.12を使えます。

```bash
sudo dnf install git bash tmux python3.12
python3.12 --version
tmux -V
```

この環境の初回導入コマンドは`python3`を`python3.12`へ読み替えてください。自動起動時も導入に使ったPythonを利用し、OS標準の`python3`を置き換える必要はありません。

[RHEL 10](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/installing_and_using_dynamic_programming_languages/installing-and-using-python)は標準のPython 3.12を使えます。

```bash
sudo dnf install git bash tmux python3
python3 --version
tmux -V
```

対象リリースとサポート期間は[RHEL Application Streamsのライフサイクル](https://access.redhat.com/support/policy/updates/rhel-app-streams-life-cycle)を参照してください。

</details>

```bash
git clone https://github.com/takamasa-aiso/cdsl.git
cd cdsl

# Preview the installation changes
python3 scripts/cdsl.py install --codex --dry-run

# Enable automatic startup
python3 scripts/cdsl.py install --codex
```

### 起動する

どちらの導入方法でも起動連携と描画コマンドの設定が完了します。**通常は個別の描画設定が不要です。** 設定ファイルがなければ作成し、既存の描画設定は保持します。本体は取得したフォルダーから動作するため、導入後も削除しないでください。

現在のBashへまだ反映していない場合は、新しいBashを開くか、次の設定を読み込みます。同じユーザーなら導入方法にかかわらず共通のパスで、`cd`は不要です。

```bash
source "$HOME/.config/cdsl/shell.sh"
```

通常どおり起動できます。`codex resume`で会話を再開する場合もCDSLが表示されます。

```bash
codex
```

未ログインの場合は`codex login`を実行し、[公式の認証手順](https://learn.chatgpt.com/docs/auth)に従ってください。

## アップデート

アンインストールは不要です。Codexを終了し、導入したユーザーの通常のBashで実行します。既存の描画設定は保持されます。

### curl経由で導入した場合

インストーラーを再実行すると、既存の`~/.local/share/cdsl/source`を更新し、不足パッケージも確認・導入します。

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

### 手動clone・ローカルのinstall.shで導入した場合

`CDSL_DIR`を実際のclone先へ置き換えてください。以下は`~/cdsl`の例です。`cd`は不要です。不足パッケージが報告された場合は、[手動導入](#手動で導入する)の手順で用意してから再実行します。

```bash
CDSL_DIR="$HOME/cdsl"

git -C "$CDSL_DIR" pull --ff-only &&
  python3 "$CDSL_DIR/scripts/cdsl.py" install --codex &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

起動処理やtmux設定の変更（スクロール対応など）は、新しく起動したCodexに反映されます。`refresh-statusline.py`による下部表示の再読み込みだけでは反映されません。

## 管理操作

### 管理操作の共通準備

導入したユーザーのBashで、本体の場所を指定します。これ以降の診断・再読み込み・アンインストールは導入方法にかかわらず共通で、`cd`は不要です。

| 導入方法 | 実行する設定 |
|---|---|
| curl経由の`install.sh` | `CDSL_DIR="$HOME/.local/share/cdsl/source"` |
| 手動clone・ローカルの`install.sh` | `CDSL_DIR="$HOME/cdsl"`（実際のclone先に置き換える） |

新しいBashでは変数を設定し直してください。rootと一般ユーザーは`HOME`が異なるため、導入したユーザーのまま操作します。診断は本体のファイルも確認するので、実際に導入したフォルダーを指定します。

AlmaLinux 9などで`python3`が3.9のままでも、管理スクリプトは導入時のPythonまたは利用可能なPython 3.11以上へ自動で切り替えます。

### 診断

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
```

`doctor`は設定を変更せず、次の項目を`OK`・`NG`と詳細で表示します。導入前にも使えます。

| 診断項目 | 確認内容 |
|---|---|
| 実行環境 | Linux / WSL、Python 3.11以上、Bash・Git、tmux 3.2以上 |
| CDSLの実行ファイル | 必要なPythonファイルの存在、読み取り可否、構文 |
| 公式Codexと起動設定 | 実行パス、管理情報とシェル設定の整合性 |
| 起動連携の残存物 | 専用入口・`shell.sh`・管理情報・各Bash設定のブロック。問題があれば復旧コマンドも表示 |
| 描画設定とコマンド | 設定形式・値、コマンド先頭の実行ファイルと実行権限 |

WSLではPowerShellの有無も任意項目として表示します。Codexのログイン状態、描画コマンドの実行結果、会話・利用量の取得、画像貼り付けの動作は診断しません。`OK`は事前確認を通過した意味で、全機能の動作確認を保証しません。

### 表示の再読み込み

実行中のCodexセッション内で、下部のCDSL表示だけを再読み込みできます。

```bash
python3 "$CDSL_DIR/scripts/refresh-statusline.py"
```

### アンインストール

Codexを終了し、導入したユーザーの通常のBashで実行します。

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex && hash -r
```

`--dry-run`は変更予定の確認だけです。管理ブロック・専用入口・`shell.sh`・管理情報を除去し、変更・削除の前に`~/.local/share/cdsl/backups/`へ退避して保存先を表示します。管理情報が欠落・破損していても、CDSLの生成内容と一致する残存物は除去します。残存物がなければ変更不要と表示し、識別できない内容があれば終了コード1で停止します。

本体フォルダー、描画設定、バックアップ、公式Codex、導入済みOSパッケージは保持します。アンインストール後に`source`でCDSLを読み込み直す必要はありません。

`hash -r`は、現在のBashに保存されたコマンド位置を消します。Pythonの子プロセスから親Bashのキャッシュは消せないため、上記のように同じBashで実行します。新しいターミナルを開く方法でも反映できます。

```bash
type -a codex
type -aP codex
```

`hash -r`はPATH自体を変更しません。`codex`が見つからない場合や、WSLでWindows版が選ばれる場合は、アンインストール結果に表示されたLinux版の絶対パスを使います。パスが表示されなければ[公式Codexのパスを確認する](#公式codexのパスを確認する)を参照するか、公式Codexを再インストールしてください。

### 管理情報の破損・変更された残存物からの復旧

通常のアンインストールが識別できない残存物で停止した場合は、`doctor`で確認し、明示的に`--purge`を指定します。

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge && hash -r
```

`--purge`は既定では無効です。対象は固定パスの専用入口・`shell.sh`・管理情報と、`.bashrc`・`.bash_profile`・`.bash_login`・`.profile`内のCDSL管理ブロックです。変更された内容もファイル全体をバックアップしてから除去し、独立した複数ブロックも扱います。ブロック外の内容は保持します。

シンボリックリンクや通常ファイル以外の対象、マーカーの入れ子・欠落などで範囲を確定できないブロックには書き込まず停止します。保持するファイルは通常のアンインストールと同じです。復旧後は`install.sh`を再実行できますが、パッケージ不足や既存の描画設定エラーは別途解消する必要があります。

## 表示と操作

### 表示の意味

| 行 | 表示内容 |
|---|---|
| ヘッダー | モデルとeffort、作業ディレクトリ、取得できる場合はGitブランチと変更数 |
| Context | 現在の会話のコンテキスト使用率、使用トークン数、上限、キャッシュ率 |
| Session | アカウントの5時間枠の使用率、対象会話の累計トークン数 |
| Weekly | アカウントの週次枠の使用率とリセットまでの時間 |
| Permissions | 現在の会話に適用された権限の範囲と承認方針 |

モデルは`[gpt-6-astra(high)]`のように表示し、括弧を含むeffortをSessionグラフの高い棒と同じピンク色にします。effortは現在の会話ログ・設定変更イベントから取得し、不明ならモデル名だけを表示します。グローバル設定から推測せず、変更がログへ記録されると通常1秒周期で追従します。

全行の左端は半角スペース2つ、使用率の閉じ括弧と後続値の間は半角スペース1つです。使用率は最低2桁幅で、`[ 8%]`・`[10%]`・`[100%]`のように表示します。時刻・時間帯は日本標準時（JST、UTC+09:00）です。

### 利用枠とグラフの読み方

**Session / Weeklyの使用率はアカウントの値、グラフは対象会話内のトークン消費履歴です。** 他の会話を合算したグラフではありません。利用量はAPIへ直接問い合わせず、Codexのローカルログから取得します。

| 表示 | 意味 |
|---|---|
| パーセンテージ | 取得できた使用率 |
| `[N/A]` | 返却された利用枠に対象の期間が含まれない |
| `[---]` | 使用率が未取得、または記録された利用期間が期限切れ |
| `Permissions: unknown` | 権限情報が未取得、または未対応 |
| 待機表示 | 対象会話を一意に特定できない |

利用枠は`window_minutes`で判定します。5時間枠がなければSessionを`[N/A]`とし、取得できた会話のトークン数を表示します。週次枠がAPIの`primary`に入っている場合もWeeklyへ表示します。

5時間枠の使用率と有効なリセット時刻が`window_minutes = 300`で現在の会話ログへ記録されると、Sessionは自動でパーセンテージ表示に戻ります。再インストールは不要ですが、ログ更新前には検知できません。

<details>
<summary>消費がなくても棒グラフが動く理由</summary>

縦棒は各時間帯の消費量を、表示範囲の最小値と最大値に合わせて相対表示します。リセット時刻が取得できた場合はその利用期間を描き、Sessionが`N/A`などで時刻がなければ現在から過去5時間を描きます。

時間経過で集計区間の境界が移動し、区間から最大値が外れると縮尺も変わるため、新しい消費がなくても棒の位置や高さが変わります。残量や経過時間そのものを表す棒ではありません。

</details>

### Permissionsの表示と切替

`Permissions: 権限の範囲 | 承認方針`の順に表示します。通常表示のラベルはClaude Codeの標準ダークテーマのwarning色（`#FFC107`）です。値の横に半角スペース1つを挟み、設定された先頭のショートカットを表示します。

| ショートカットの状態 | ヒント |
|---|---|
| 設定済み（F7の例） | `(F7 for cycle)` |
| 未割当 | `(/keymap to set cycle key)` |
| 設定を判定できない | `(/keymap to check cycle key)` |

Codexの`/keymap`で`next_permission_mode`にキーを割り当て、メニューを閉じて入力欄で押すと切り替えられます。検証対象の[Codex 0.153.4](https://github.com/openai/codex/releases/tag/rust-v0.153.4)では初期状態で未割当です。実行中の画面では、利用可能なRead Only・Ask for approval・Approve for meを巡回します。**Full Accessは巡回対象外なので、`/permissions`で選択します。** これは実行中の切替の説明で、`--yolo`などの起動オプションとは別です。

変更は現在の会話だけに適用され、CDSLは通常1秒周期で反映します。`/permissions`からの変更も同様で、次のプロンプト送信は不要です。候補と確認処理はCodex本体に従います。実行中のキー変更は`/keymap`で行い、設定ファイルの直接編集が即座に反映されるとは限らない点に注意してください。

`Never`は実行時の承認を求めず、承認が必要な操作を拒否する方針です。権限の範囲とは別なので、`Read Only | Never`は読み取り専用、`Full Access | Never`はCodexのサンドボックス制限なし・承認要求なしを意味します。

自動審査で人への確認を減らす使い方では、`Approve for me`がClaude Codeの`auto`モードに最も近い選択肢です。どちらも審査で操作を拒否できますが、Codexはサンドボックスを維持して承認が必要な操作を審査役へ送り、Claude Codeは独自の分類モデルとルールで判定します。実用上の対応づけであり、同じ仕組みではありません。[Codex Auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review)、[Claude Code auto mode](https://code.claude.com/docs/en/permission-modes#eliminate-permission-prompts-with-auto-mode)を参照してください。

<details>
<summary>権限の範囲・承認方針の一覧</summary>

| 権限の範囲 | 意味 |
|---|---|
| `Read Only` | 読み取り専用の組み込みプロファイル |
| `Workspace` | 作業ディレクトリなど、許可された範囲への書き込みが可能 |
| `Full Access` | Codexのサンドボックス制限なし。OSや組織側の制約は別途適用される |
| `Custom permissions` | 組み込みの表示名に当てはまらない権限設定 |
| プロファイル名 | 名前付きの独自プロファイルを使用中。その名前を表示 |
| `unknown` | 有効な権限情報が未取得 |

| 承認方針 | 意味 |
|---|---|
| `Ask for approval` | Codexが必要と判断した承認をユーザーへ求める |
| `Approve for me` | 承認が必要な操作を自動レビューへ送る。拒否される場合もある |
| `Never` | 実行時の承認を求めない。承認が必要な操作は拒否する |
| `On request` | 必要時に承認を求めるが、承認先がログから不明 |
| `Untrusted` | 既知の安全なコマンド以外は承認が必要 |
| `Granular` | 承認の種類ごとに要求の許可・自動拒否を設定 |
| `On failure` | サンドボックス内での失敗後、制限外での再実行の承認を求める旧設定。Codexでは非推奨 |
| `unknown` | 承認方針が未取得、または未対応 |

表示は会話ログの実効設定を短く表したものです。個別の許可パスやルールはCodexの`/permissions`・`/status`で確認してください。

</details>

<details>
<summary>キー設定の取得元と狭い端末での表示</summary>

`$CODEX_HOME/config.toml`（通常は`~/.codex/config.toml`）を読みます。`--profile <name>`で起動した場合は、同じディレクトリの`<name>.config.toml`も読みます。プロジェクト・システム・コマンドラインに同じアクションの定義がある場合や、保存設定を確実に読み取れない場合は、キー名の代わりに確認用ヒントを出します。

狭い端末ではラベル・グラフを短縮します。`Permissions:`は`P:`、`Custom permissions`は`Custom`、`Ask for approval`は`Ask`、`Approve for me`は`Auto review`になります。ヒントも`(F7)`・`(set /keymap)`・`(check /keymap)`へ短縮し、必要なら権限の値を省略してヒントを残します。極端に狭い場合はヒントも省略します。

</details>

### スクロールと文字選択

上段のCodex画面はマウスホイールやトラックパッドで履歴をスクロールできます。最下部まで戻すか`q`・`Esc`を押すと通常入力へ戻ります。下段のCDSLは固定表示です。端末本来の文字選択を使う場合は、端末の設定に応じて`Shift`を押しながらドラッグしてください。

### 画像の貼り付け

画像をコピーし、入力欄で`Ctrl+v`を押します。環境によっては`Alt+v`で貼り付けられる場合もあります。クリップボードが使えなければ、ローカルファイルへ保存した画像のパスを入力欄に貼り付け、画像として添付されたことを確認して送信します。

Codex 0.153.4には標準の代替キー`Ctrl+Alt+v`もあります。画像貼り付けキーは固定で、`/keymap`の編集対象ではありません。[Codexのキー定義](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap.rs#L2164)

キーが届かない場合は、`/keymap`の`Debug`タブで`Inspect keypresses`を選び、Enterを押して確認できます。`Ctrl+c`で終了します。端末側の割当も確認してください。[Codexのキー検査画面](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap_setup/picker.rs#L312)

WSLでは`Ctrl+v`にCDSLのWindowsクリップボード補助が入り、利用できるWindows PowerShellでPNGへ変換して添付します。取得できなければCodex標準処理へ戻ります。

### 端末の互換表示

`TERM=xterm`かつ`COLORTERM`未指定などの端末では、幅が一定のASCIIグラフと基本色を使います（Permissionsは黄色）。`CDSL_RENDER_MODE=ascii codex`で互換表示、`CDSL_RENDER_MODE=unicode codex`で通常表示を明示できます。

## 設定と保存先

### 保存先と起動連携

| 場所 | 役割 |
|---|---|
| `~/.local/share/cdsl/bin/codex` | CDSL専用の起動入口 |
| `~/.config/cdsl/shell.sh` | 専用入口をPATHの先頭へ置く設定 |
| `~/.bashrc` | Bashの対話起動で読み込む管理ブロック |
| Bashのログイン設定 | `.bash_profile`、`.bash_login`、`.profile`の優先順位で使われるファイルへ管理ブロックを追加 |
| `~/.config/cdsl/config.toml` | 描画コマンドと更新間隔 |
| `~/.local/share/cdsl/startup.json` | アンインストール・再設定用の管理情報 |
| `~/.local/share/cdsl/backups/` | 変更前のファイルを0600で保存 |

公式Codexの入口を上書きしないため、公式インストーラーがその入口を作り直してもCDSLの入口は残ります。standalone版は`current`、npm版は選択した実行パスを保持し、同じ場所の更新に追従します。Codexのログ形式やCLI仕様が変わる場合はCDSL側の対応が必要です。

シェル設定の既存部分は保持し、CDSLの管理ブロックだけを追加・更新します。外部で変更されたブロックやシンボリックリンクのシェル設定は、上書きせずエラーにします。

### 公式Codexのパスを確認する

| 導入方法 | 起動入口の例 |
|---|---|
| standalone版 | `~/.local/bin/codex`から`~/.codex/packages/standalone/current/bin/codex`へリンク |
| npmグローバル導入 | `<prefix>/bin/codex`（例：`/usr/local/bin/codex`） |
| nvmで管理するNodeへのnpm導入 | `~/.nvm/versions/node/<version>/bin/codex` |

CDSLはstandalone版の`current`を優先し、見つからなければPATHから探します。次のコマンドは、関数・エイリアスを含む候補と、PATH上の実行ファイルをそれぞれ表示します。

```bash
type -a codex
type -aP codex
```

npmの`<prefix>`と、standalone版のリンク先は次で確認できます。`readlink`のパスは実際の候補へ置き換えてください。

```bash
npm prefix -g
readlink -f "$HOME/.local/bin/codex"
```

`--real-codex`へはCDSL専用入口を指定せず、公式Codexの起動入口を指定します。版ごとの内部パスより、更新後も同じ場所にある入口を選びます。Nodeのバージョン変更などでCodexの場所が変わったときも再登録してください。

[管理操作の共通準備](#管理操作の共通準備)で`CDSL_DIR`を設定したうえで実行します。

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" install --codex --real-codex "$HOME/.local/bin/codex"
```

CDSL本体のフォルダーを移した場合は、新しい場所からインストールを再実行し、描画設定の`command`も新しい絶対パスへ変更します。既存の描画設定は自動では上書きしません。

### 描画コマンドの設定（カスタマイズする場合のみ）

通常の導入で設定は完了します。以下は描画プログラムや更新間隔を変更する場合だけの参考例です。Pythonと本体のパスは環境に合わせて置き換えます。

```toml
[statusLine]
command = ["/usr/bin/python3", "/absolute/path/to/cdsl/scripts/statusline.py"]
timeout_seconds = 2.0
refresh_interval = 1.0
```

設定は`~/.config/cdsl/config.toml`です。別のファイルを使う場合は、用意したパスを`CDSL_CONFIG`へ指定します。指定先は自動作成されません。`command`はシェルを介さない引数配列なので、`~`・変数・パイプなどは展開されません。

<details>
<summary>独自の描画プログラム向けJSONプロトコル</summary>

バージョン1のJSONを標準入力へ渡し、UTF-8のANSI文字列を標準出力から受け取ります。

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

`session`には正規化した使用量・Git・権限情報が入ります。`session.now`は描画時刻で、既定の描画プログラムはログや時計を独自に読みません。`terminal.rows`はプロトコル上の画面情報で、既定の描画は常に5行です。

標準出力・標準エラーの上限はそれぞれ64KiBです。タイムアウトや実行失敗は表示領域へ通知し、Codexの操作を継続できます。

</details>

## プロジェクト情報

### セキュリティとライセンス

セキュリティ上の問題は[GitHubの非公開報告](https://github.com/takamasa-aiso/cdsl/security/advisories/new)から連絡してください。詳細は[SECURITY.md](SECURITY.md)を参照してください。

著作権表示とMITライセンス条件は[LICENSE](LICENSE)、CCSL由来の部分・出典・元の著作権表示とライセンス条件は[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に記載しています。CDSLはOpenAIやCCSL作者による公式提供・推奨を示すものではありません。

### Releaseの記載ルール

[GitHub Releases](https://github.com/takamasa-aiso/cdsl/releases)には、バージョンごとに次の項目を日本語・英語の順で記載します。

| 項目 | 内容 |
|---|---|
| 変更内容 / Changes | 前のReleaseからの追加・修正・利用者への影響。初回は主な機能 |
| 対応するCodexのバージョン / Codex compatibility | 実際に動作確認した版。未検証の版を対応済みとしない |
| 既知の制限 / Known limitations | 環境、データ取得・表示・性能、未解決の問題と回避策。なければその旨 |

各Releaseは公開するコミットにタグを付け、その版の状態を記載します。変更履歴はReleaseにまとめ、このREADMEには現在の仕様と利用方法を記載します。

### 配布ファイルと参考資料

<details>
<summary>リポジトリ内のファイル一覧</summary>

| 場所 | 用途 |
|---|---|
| `cdsl/` | 起動連携、セッション取得、描画、画像貼り付けの本体 |
| `install.sh` | 本体の取得と導入の入口 |
| `scripts/setup.sh` | Bashによる依存導入とCDSL設定 |
| `scripts/cdsl.py` | 導入・診断・アンインストールと起動処理の入口 |
| `scripts/statusline.py` | JSONを色付き文字列へ変換 |
| `scripts/paste-image.py` | WSLクリップボード補助 |
| `scripts/refresh-statusline.py` | 実行中の下部表示の再読み込み |
| `assets/statusline-preview.png` | 現行CDSLで描画した表示例 |
| `assets/how-it-works.ja.png` | 日本語の仕組み図 |
| `assets/how-it-works.svg` | 英語の仕組み図 |
| `README.md`・`README.en.md` | 日英の利用方法 |
| `SECURITY.md` | セキュリティ上の問題の非公開報告方法 |
| `THIRD_PARTY_NOTICES.md` | CCSL由来の部分と元の著作権・ライセンス条件 |
| `LICENSE` | 利用条件と著作権表示 |

</details>

- [Codex設定リファレンス](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Codexの承認とセキュリティ](https://learn.chatgpt.com/docs/agent-approvals-security)
- [Codex 0.153.4の権限ショートカット](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/chatwidget/permission_shortcuts.rs)
- [Codexの公式インストーラー](https://github.com/openai/codex/blob/rust-v0.153.4/scripts/install/install.sh)
