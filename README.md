# CDSL (CoDex StatusLine)

日本語 | [English](README.en.md)

通常の`codex`起動に、CCSL風のステータス表示を追加する非公式ツールです。モデルとeffort、コンテキスト、利用枠、権限を端末の下部5行に表示します。

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

CDSLが公式Codexを起動し、tmuxの上段に会話画面、下段にステータスを配置します。公式Codexの実行ファイルは変更しません。会話ログ・Git情報・キー設定を読み、JSONを描画プログラムへ渡して通常1秒ごとに表示を更新します。

`statusLine.command`はCDSL独自の設定です。検証対象のCodex 0.153.4には、外部コマンドの出力を本体のステータス欄へ埋め込む設定がありません。`codex exec`、`codex update`、ヘルプなどは公式Codexへそのまま引き継ぎます。

## インストール

### 対応環境

| 項目 | 要件 |
|---|---|
| OS・シェル | Linux / WSL、Bash |
| 依存パッケージ | Python 3.11以上、tmux 3.2以上、Git |
| Codex CLI | standalone版またはnpm版（0.153.4で検証） |

tmuxは3.2a・3.4で検証しています。macOS、Windowsネイティブ版、リモートCodex接続は対象外です。

### install.shで導入する

`curl`が使える環境で実行します。本体を`~/.local/share/cdsl/source`へ取得し、apt/dnfで不足パッケージと、未導入の場合はLinux版Codexを導入します。

**インストールのみ（完了後は新しいBashで起動）**

```bash
curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh
```

**インストールして現在のBashへも反映**

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) && . "$HOME/.config/cdsl/shell.sh"
```

### 手動で導入する

必要なパッケージと[公式Codex](https://learn.chatgpt.com/docs/codex/cli)を先に導入してください。以下のPythonコマンドは、不足があれば変更前に停止します。パッケージは自動導入しません。

<details>
<summary>OS別のパッケージ導入例</summary>

Ubuntu 24.04 / Debian 12：

```bash
sudo apt update
sudo apt install python3 tmux git bash
```

RHEL 9.4以降のRHEL系（AlmaLinux、Rocky Linuxなど）：

```bash
sudo dnf install git bash tmux python3.12
```

標準のPython 3.9は置き換えず、初回の導入コマンドでは`python3.12`を使います。RHEL 10は標準のPython 3.12を利用できます。

```bash
sudo dnf install git bash tmux python3
```

`python3 --version`（RHEL 9では`python3.12 --version`）と`tmux -V`で要件を確認してください。RHEL実機での全機能検証は行っていません。互換ディストリビューションではパッケージの提供有無も確認してください。

参考：[Ubuntu](https://packages.ubuntu.com/noble/python3) / [Debian](https://packages.debian.org/bookworm/python3) / [RHEL 9](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/installing_and_using_dynamic_programming_languages/assembly_installing-and-using-python_installing-and-using-dynamic-programming-languages) / [RHEL 10](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/installing_and_using_dynamic_programming_languages/installing-and-using-python)

</details>

```bash
git clone https://github.com/takamasa-aiso/cdsl.git
cd cdsl
python3 scripts/cdsl.py install --codex --dry-run
python3 scripts/cdsl.py install --codex
```

### 起動する

**導入時に描画設定も完了するため、個別設定は不要です。** 既存設定は保持します。本体は取得したフォルダーから動作するので、導入後も削除しないでください。

現在のBashへ未反映なら、新しいBashを開くか次を実行します。同じユーザーならパスは導入方法によらず共通で、`cd`は不要です。

```bash
source "$HOME/.config/cdsl/shell.sh"
```

`codex`で起動、`codex resume`で会話を再開できます。未ログインの場合は`codex login`で[認証](https://learn.chatgpt.com/docs/auth)してください。

## アップデート

アンインストールは不要です。Codexを終了し、導入したユーザーの通常のBashで実行します。描画設定は保持されます。

### curl経由で導入した場合

インストーラーを再実行すると、本体を更新し、不足パッケージを導入します。

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/takamasa-aiso/cdsl/main/install.sh | sh) &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

### 手動clone・ローカルのinstall.shで導入した場合

`CDSL_DIR`を実際のclone先へ置き換えます。不足パッケージが報告された場合は、[手動導入](#手動で導入する)の手順で用意してください。

```bash
CDSL_DIR="$HOME/cdsl"

git -C "$CDSL_DIR" pull --ff-only &&
  python3 "$CDSL_DIR/scripts/cdsl.py" install --codex &&
  . "$HOME/.config/cdsl/shell.sh" &&
  codex
```

起動処理・tmux設定の変更にはCodexの再起動が必要です。下部表示の再読み込みだけでは反映されません。

## 管理操作

### 管理操作の共通準備

導入したユーザーのBashで、本体の場所を指定します。以降の操作に`cd`は不要です。

| 導入方法 | 実行する設定 |
|---|---|
| curl経由の`install.sh` | `CDSL_DIR="$HOME/.local/share/cdsl/source"` |
| 手動clone・ローカルの`install.sh` | `CDSL_DIR="$HOME/cdsl"`（実際のclone先に置き換える） |

新しいBashでは変数を設定し直してください。rootと一般ユーザーは`HOME`が異なります。`python3`が3.9でも、管理スクリプトは導入時のPythonまたは利用可能な3.11以上へ切り替わります。

### 診断

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
```

依存関係、本体ファイル、公式Codexのパス、起動設定の残存物、描画設定を確認し、`OK`・`NG`と対処を表示します。設定は変更しません。ログインや利用量取得・描画・画像貼り付けの実動作を検証するものではありません。

### 表示の再読み込み

実行中のCodexセッション内で、下部表示だけを再読み込みします。

```bash
python3 "$CDSL_DIR/scripts/refresh-statusline.py"
```

### アンインストール

Codexを終了し、通常のBashで実行します。

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex && hash -r
```

`--dry-run`は変更予定の確認だけです。専用入口・`shell.sh`・管理情報・Bashの管理ブロックを除去します。変更前のファイルは`~/.local/share/cdsl/backups/`へ退避し、保存先を表示します。**本体、描画設定、バックアップ、公式Codex、OSパッケージは残します。**

`hash -r`は同じBashで実行し、古いコマンド位置を消します。PATH自体は変わりません。起動できなければ`type -a codex`で確認し、アンインストール結果に表示されたLinux版Codexの絶対パスを使ってください。解除後にCDSLを`source`し直す必要はありません。

### 管理情報の破損・変更された残存物からの復旧

管理情報がなくても、識別できる生成物は通常のアンインストールで除去します。残存物がなければ変更不要、識別できなければ終了コード1で停止します。後者では`doctor`で確認し、明示的に`--purge`を指定します。

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" doctor
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge --dry-run
python3 "$CDSL_DIR/scripts/cdsl.py" uninstall --codex --purge && hash -r
```

`--purge`も対象は起動連携だけです。変更された生成物や管理ブロックをファイル全体のバックアップ後に除去し、ブロック外は保持します。シンボリックリンク・通常ファイル以外の対象・範囲不明のブロックには書き込まず停止します。復旧後は`install.sh`を再実行できます。描画設定などに別のエラーがあれば、そちらも解消してください。

## 表示と操作

### 表示の意味

| 行 | 表示内容 |
|---|---|
| ヘッダー | モデルとeffort、作業ディレクトリ、Gitブランチと変更数 |
| Context | 現在の会話のコンテキスト使用率・トークン数・上限・キャッシュ率 |
| Session | アカウントの5時間枠の使用率、対象会話の累計トークン数 |
| Weekly | アカウントの週次枠の使用率、リセットまでの時間 |
| Permissions | 現在の会話に適用された権限の範囲と承認方針 |

例：`[gpt-6-astra(high)]`。effortは現在の会話ログから取得し、括弧ごとピンク色で表示します。不明なら省略し、グローバル設定からは推測しません。時刻はJSTです。

### 利用枠とグラフの読み方

**Session / Weeklyの使用率はアカウントの値、グラフは対象会話の消費履歴です。** 他の会話は合算しません。データはCodexのローカルログから取得します。

| 表示 | 意味 |
|---|---|
| `[N/A]` | 返却された利用枠に対象期間がない |
| `[---]` | 使用率が未取得、または利用期間が期限切れ |
| `Permissions: unknown` | 権限情報が未取得、または未対応 |
| 待機表示 | 対象会話を一意に特定できない |

5時間枠がログへ再び記録されれば、Sessionは使用率表示に戻ります。再インストールは不要です。

<details>
<summary>消費がなくても棒グラフが動く理由</summary>

棒の高さは各時間帯の消費量の相対値です。リセット時刻があればその利用期間、Sessionの時刻が不明なら直近5時間を描きます。時間経過で集計区間や縮尺が変わるため、消費がなくても動きます。残量や経過時間そのものを示す棒ではありません。

</details>

### Permissionsの表示と切替

`権限の範囲 | 承認方針`を表示します。`/keymap`の`next_permission_mode`へキーを割り当てると、`(F7 for cycle)`のようなヒントが付きます。未割当なら`(/keymap to set cycle key)`、判定できなければ確認用のヒントを表示します。

検証対象の[Codex 0.153.4](https://github.com/openai/codex/releases/tag/rust-v0.153.4)では初期状態で未割当です。メニューを閉じて入力欄でキーを押すと、利用可能なRead Only・Ask for approval・Approve for meを巡回します。**Full Accessは`/permissions`で選択してください。**

切替は現在の会話に適用され、CDSLはログ更新後、通常1秒周期で追従します。次のプロンプト送信は不要です。キーの変更も`/keymap`から行ってください。

`Approve for me`は、人への確認を自動審査へ置き換える点でClaude Codeの`auto`モードに最も近い選択肢です。仕組みは異なり、どちらも操作を拒否する場合があります。[Codex](https://learn.chatgpt.com/docs/sandboxing/auto-review) / [Claude Code](https://code.claude.com/docs/en/permission-modes#eliminate-permission-prompts-with-auto-mode)

<details>
<summary>権限・承認方針の意味</summary>

権限の範囲は`Read Only`（読み取り専用）、`Workspace`（許可範囲への書き込み）、`Full Access`（Codexのサンドボックス制限なし）などです。OSや組織側の制約は別途適用されます。独自設定は`Custom permissions`またはプロファイル名で表示します。

| 承認方針 | 意味 |
|---|---|
| `Ask for approval` | 必要時にユーザーへ承認を求める |
| `Approve for me` | 承認が必要な操作を自動レビューへ送る |
| `Never` | 承認を求めず、承認が必要な操作は拒否する |
| `On request` | 必要時に承認を求めるが、承認先はログから不明 |
| `Untrusted` | 既知の安全なコマンド以外は承認が必要 |
| `Granular` | 承認の種類ごとに要求の許可・拒否を設定 |
| `On failure` | サンドボックス内の失敗後に制限外での再実行の承認を求める旧設定。Codexでは非推奨 |
| `unknown` | 未取得、または未対応 |

`Never`は権限の広さを表しません。`Read Only | Never`は読み取り専用、`Full Access | Never`はCodexのサンドボックス制限なし・承認要求なしです。個別の許可パスは`/permissions`・`/status`で確認してください。

</details>

### スクロール・画像貼り付け

- 上段はホイール・トラックパッドで履歴をスクロールできます。最下部まで戻すか`q`・`Esc`で通常入力へ戻ります。下段は固定表示です。
- 端末本来の文字選択は、対応する端末で`Shift`を押しながらドラッグします。
- 画像は`Ctrl+v`で貼り付けます。環境により`Alt+v`、Codex標準の代替キー`Ctrl+Alt+v`も使えます。使えなければ画像ファイルのパスを添付してください。

画像貼り付けキーは`/keymap`の編集対象外です。キーが届くかは`/keymap`→`Debug`→`Inspect keypresses`で確認できます（Enterで開始、`Ctrl+c`で終了）。[キー定義](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap.rs#L2164) / [キー検査](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/tui/src/keymap_setup/picker.rs#L312)

WSLでは`Ctrl+v`にWindowsクリップボード補助を使い、PowerShellでPNGへ変換して添付します。取得できなければCodex標準処理へ戻ります。

### 端末の互換表示

狭い端末ではラベルやヒントを短縮します。`TERM=xterm`かつ`COLORTERM`未指定などではASCIIグラフと基本色を使います。`CDSL_RENDER_MODE=ascii codex`で互換表示、`CDSL_RENDER_MODE=unicode codex`で通常表示を明示できます。

## 設定と保存先

### 保存先と起動連携

| 場所 | 用途 |
|---|---|
| `~/.local/share/cdsl/bin/codex` | 専用の起動入口 |
| `~/.config/cdsl/shell.sh` | 専用入口をPATHの先頭へ追加 |
| `~/.bashrc`・Bashのログイン設定 | 設定を読み込む管理ブロック |
| `~/.config/cdsl/config.toml` | 描画コマンドと更新間隔 |
| `~/.local/share/cdsl/startup.json` | 管理情報 |
| `~/.local/share/cdsl/backups/` | 変更前のファイルを0600で保存 |

公式Codexの更新ではCDSLの入口は消えません。ただし、Codexの場所やログ形式が変われば再設定・CDSL側の対応が必要です。本体フォルダーを移した場合は、新しい場所で再インストールし、描画設定の`command`も変更してください。

### 公式Codexのパスを確認する

| 導入方法 | 起動入口の例 |
|---|---|
| standalone | `~/.local/bin/codex`（`~/.codex/packages/standalone/current/bin/codex`へのリンク） |
| npm | `<prefix>/bin/codex`（例：`/usr/local/bin/codex`） |
| nvm | `~/.nvm/versions/node/<version>/bin/codex` |

CDSLはstandaloneの`current`を優先し、次にPATHから探します。候補・npmの配置先・リンク先は次で確認できます。

```bash
type -a codex
type -aP codex
npm prefix -g
readlink -f "$HOME/.local/bin/codex"
```

明示する場合は[管理操作の共通準備](#管理操作の共通準備)で`CDSL_DIR`を設定し、公式Codexの起動入口を指定します。CDSL専用入口や版ごとの内部パスは避けてください。

```bash
python3 "$CDSL_DIR/scripts/cdsl.py" install --codex --real-codex "$HOME/.local/bin/codex"
```

### 描画コマンドの設定（カスタマイズ時のみ）

通常は設定不要です。変更する場合は`~/.config/cdsl/config.toml`を編集します。Pythonと本体のパスは実環境に合わせてください。

```toml
[statusLine]
command = ["/usr/bin/python3", "/absolute/path/to/cdsl/scripts/statusline.py"]
timeout_seconds = 2.0
refresh_interval = 1.0
```

`command`は引数配列で、`~`・変数・パイプなどのシェル展開は使えません。別ファイルを使う場合は、自分で作成して`CDSL_CONFIG`にパスを指定します。

独自描画はバージョン1のJSONを標準入力で受け取り、UTF-8のANSI文字列を返します。仕様は[scripts/statusline.py](scripts/statusline.py)を参照してください。出力上限は標準出力・標準エラー各64KiBです。失敗・タイムアウト時もCodexの操作は継続できます。

## プロジェクト情報

- **セキュリティ**：問題は[非公開報告](https://github.com/takamasa-aiso/cdsl/security/advisories/new)で連絡してください。詳細は[SECURITY.md](SECURITY.md)に記載しています。
- **ライセンス**：[LICENSE](LICENSE)と[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)に、MIT条件・CCSL由来の部分・元の著作権表示を保持しています。OpenAIやCCSL作者の公式提供・推奨を示すものではありません。
- **Release**：[GitHub Releases](https://github.com/takamasa-aiso/cdsl/releases)に、変更内容・検証したCodexのバージョン・既知の制限を日英で記載します。各Releaseは公開コミットへタグを付け、READMEには現在の仕様を記載します。
- **配布ファイル**：本体は[cdsl/](cdsl/)、実行スクリプトは[scripts/](scripts/)、表示画像と仕組み図は[assets/](assets/)です。
