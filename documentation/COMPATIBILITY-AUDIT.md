# 現行jar・基点ソースの互換性監査

2026-11-24。対象は固定した現行jar、基点ソース、バイトコードからの再構成版、現在の安全なfork。
この監査ではVMの動作を追加変更せず、比較用ツール、テスト出力の保存、分類資料を追加した。
本書は修正前の基準を保存したもの。後続の弱テーブル・fmod・modf修正は [正当性修正](CORRECTNESS-FIXES.md) に記録する。

## 結論

現行jarの独自の実行処理は、`LuaClosure` のスタックキャッシュに絞れた。
それ以外の動作する命令差は、旧Antビルドが埋め込むバージョン文字列と、型消去・冗長キャストで説明できる。
数値表現、文字列変換、リフレクション等に別の独自最適化を移植する必要は見つかっていない。
パッケージ名、公開メンバーのJVM descriptor、継承関係は基点と一致する。

実際の改造ソースを発見したわけではない。`legacy-reconstruction.patch` はバイトコードから推定した比較用の再構成であり、
既知の不具合も意図的に再現する。製品には使用しない。jarのバイト単位の一致を主張するものでもない。

既存51件はすべて分類した。単なる古い期待値だけでなく、データ消失・返却型・例外・数値表示の実不具合を含む。
したがって、51件を一括除外したり、現在の出力で期待値を上書きしたりしない。

## 全350クラスの分類

基点: `daf3da94e3cdba0ac6a289148d7e38bd53d3fe64`。
現行jar SHA-256: `15bcbdd85ddf6f1e189093b28850c086e5bf13085cbc29595f3523444fb5fd8a`。
比較用の基点・再構成版はJDK 17.0.19の `--release 8` でビルドし、現行jarと同じclass major version 52にそろえた。
現行jarのmanifestはAnt 1.10.5 / Oracle JDK 1.8.0_251を記録している。

| 分類 | クラス数 | 内容 |
| --- | ---: | --- |
| 生のjavap表示が一致 | 29 | classファイルの定数プール・デバッグ情報等はバイト単位では異なる |
| 定数プール番号、分岐アドレス、ldc幅、宣言・型情報等 | 308 | 正規化した命令と例外ハンドラは一致 |
| 冗長な連続checkcast | 6 | 同じ型への連続キャスト。削除前後のラベルも対応づけて照合 |
| 配布時のバージョン埋め込み | 6 | lua / luac / luajc、Lua、BaseLib、LuaScriptEngine。luajcにはキャスト差もある |
| 独自のスタックキャッシュ | 1 | LuaClosureのみ |
| 合計 | 350 | クラス名の追加・削除なし |

`LuaClosure.execute`、末尾呼び出し命令、Varargs、UpValueの本体は基点と同じだった。
独自変更は `getNewStack`、追加された `releaseStack`、コンストラクタ、4種類の `call`、`onInvoke` とprivateフィールド。
キャッシュはクロージャごとに `Stack<LuaValue[]>` を最大20本保持し、通常復帰時だけ返却する。
多値返却・末尾呼び出しの配列参照を切らず、返却時に参照を消去しない。これが既に修正した破損・保持の原因になる。
同期されたStackでもempty/popやsize/pushは複合操作として同期されていない。

再構成版では、350クラス全体でバージョン文字列とキャッシュの命令差が消える。
残る命令差は7クラスの冗長キャストのみ。メンバーのアクセスフラグ、定数、例外宣言、max_stack/max_locals・ハンドラ数も照合した。
属性の種類は検査し、未対応の属性が出た場合は比較を失敗させる。
残る非コード差は次のとおり。

- ジェネリクスのSignatureが19クラスで異なる。うち15クラスは公開API表示にも現れるが、JVM descriptorは同じ。
- 旧Antのジェネリクス除去に対応し、`Stat` / `Stat$Assign` のInnerClasses参照に `Exp$VarExp` の有無の差がある。ネストしたクラス自体の追加・削除ではない。
- LineNumberTable、LocalVariableTable、LocalVariableTypeTable、StackMapTable、定数プール配置などの生成情報が異なる。
- JSR-223サービス定義は同じ。manifestのビルド情報が異なり、Maven版はLICENSEとMaven座標のリソースを追加する。

型情報をreflectionで読む利用者にはSignatureの差が見えるため、「あらゆるreflectionの結果が同一」とはしない。
確認したbeatorajaソースには対象のAST/parser/scriptパッケージの直接使用はなかった。
全クラスの分類・メンバー差・リソースハッシュは [bytecode-audit.json](bytecode-audit.json) に保存した。

## 同一テストによる比較

以前のSurefire結果870件にはsuiteと個別クラスの重複がある。重複を除いた652件から、fork固有のStackPoolTest 3件を分け、
共通649件のclass#method一覧を [audit-test-cases.list](audit-test-cases.list) で固定した。
同一のテストclassファイルを使用し、実行時のVM jarだけを切り替えた。
全構成でJDK 17.0.19、UTF-8、Asia/Tokyo、en_US、512MiBヒープを使用した。

| 構成 | 共通件数 | 成功 | 失敗 |
| --- | ---: | ---: | ---: |
| 現行jar | 649 | 593 | 56 |
| 基点ソースそのまま | 649 | 597 | 52 |
| 現行jarの再構成版 | 649 | 593 | 56 |
| 安全なfork | 649 | 598 | 51 |

現行jarと再構成版は、成功・失敗、例外型、診断文、スクリプト全体の出力が一致した。
比較時に除くのはテーブル・スレッド・LuaJCクラスローダー・upvalueの実行ごとの識別子のみ。
数値、返却内容、エラー種別を一律に正規化していない。

現行jarの追加5件は、StackLifetimeTestの3件と既存のJSE/JME `testTailcalls` 2件。
どちらもキャッシュによる寿命の破損に対応する。基点の追加1件は `testFactoryMetadata` のバージョン表記で、
同じテストが配布jarの `Luaj-jse 3.0.2` を期待する一方、未加工ソースのビルドでは `Luaj 0.0` になるため。
この1件をVMの実行バグとして数えない。
基点とforkの残り648件は、失敗しているテストの全スクリプト出力も含め一致した。

I/Oテストはabc.txtやseektest.txtを生成する。複数構成を同じcwdで実行すると干渉するため、
最終結果は各実行に新しい専用ディレクトリを作り、fixtureをコピーして取り直したもの。
ログ・ハッシュ・全649件の結果は [audit-matrix.json](audit-matrix.json) に保存した。

## 既存51件の失敗原因

| 原因のグループ | 件数 | 切り分け結果・次の扱い |
| --- | ---: | --- |
| 弱テーブルの整数キー | 20 | 実不具合。3番目の挿入時、rehashで配列長が4になるのに新規キー3はhashへ入り、rawgetは空のarray[2]を読む。GCなしで再現 |
| 弱テーブルの内部容量assert | 1 | key 1をhashに保持できるのにarray容量を要求するテスト。容量ではなく取得・弱参照の意味を検証すべき |
| MathLibTest.testFmod | 1 | 実不具合。整数の剰余経路が除数0でArithmeticExceptionを投げる |
| BaseLib | 3 | 空reader文字列をEOFとして扱わない。さらに内側pcallで捕捉するエラーでも外側xpcallのhandlerを実行する |
| コルーチン | 3 | fixtureがC-call境界でのyield失敗を期待。LuaJのpcallをまたぐyieldは成功する。対応機能を壊してfixtureに合わせない |
| デバッグ | 2 | CとJavaのフレーム・hook順序の違いに加え、名前のないローカルでレジスタ値を返す実装上の問題も含む |
| JME I/O / OS | 2 | 実行環境不足。CLDCはAPIスタブで、Connector.openがErrorを投げる。OSテストもファイルを開く |
| manyupvals | 3 | upvalueの計算ではなく表示の不具合。有限doubleをfloatへ縮めるため、約1.734e41の値をInfinityと表示 |
| 数学ライブラリの型変換 | 3 | modf('0')の第1返却値がstring。min/maxのnumeric string変換不足。fmodの除数0も同じテスト内に含む |
| OS時刻 | 2 | fixtureはAmerica/Los_Angelesの日時・DSTを固定。タイムゾーンだけを合わせた再実行で2件とも成功 |
| 文字列・LuaJC dump | 3 | 不正UTF-8のJava文字列化とCのバイト出力の差。string.byteの行は一致。LuaJCだけはstring.dump未対応も含む |
| table.insert | 3 | fixtureの位置10は#t+1=8の範囲外。Lua 5.2.4の実装も拒否する。後続のtableテストに到達しないfixtureを修正すべき |
| ErrorsTestの出力比較 | 5 | 下記。メッセージだけの差と引数検証の実不具合が混在 |
| 合計 | 51 | すべて現行jar・基点・forkに共通 |

ErrorsTestの内訳:

- BaseLibArgs: `String` / `string` 等の文言・診断形式、loadの引数エラー。
- DebugLibArgs: 関数を渡すgetlocalの未対応、Javaフレームのnull stack、getinfo等の動作差と文言差。識別子の値も固定できない。
- IoLibArgs: 捕捉した全差分は `io.lines(nil)` の関数表示（Cのアドレスと `function: lnext`）。
- MathLibArgs: atan2の第2引数省略時の扱い、min/maxの非数値・numeric string検証など。文言差だけではない。
- StringLibArgs: Cの8バイトsize_tとLuaJの4バイトsize_t、コンパイラ・upvalue情報、不正バイトの表示、%s引数変換、gsubの負の上限に対する期待値が混在。ネイティブdumpのバイト列を正解としてそのまま移植しない。

51件それぞれのグループ、例外型、根拠、対応方針は [failure-causes.json](failure-causes.json) を参照。
スクリプト出力は `build/audit/<構成>/output/` にexpected/actualの両方を保存する。
テストは最初の不一致で止まるが、出力全体も取得し、最初の差だけで分類しないようにした。

### 原因の確認に使った追加実験

`CompatibilityProbes.java` は既知の不具合を成功扱いするテストではなく、観測値を出す診断用。
全構成で、キー3の消失、有限値のInfinity表示、fmodのエラー、modfのstring返却、空reader後の読み続け、nested pcallのhandler呼び出しを確認した。

弱テーブルは、比較用overlayで整数キーのrehash経路だけを変えると、該当20件がすべて成功した。
[weak-routing-experiment.patch](weak-routing-experiment.patch) に実験差分を保存した。
この変更だけでは弱い値のarray移動時のwrap・GC・参照保持まで保証しないため、本体には適用していない。
OSの2件は専用の2件一覧でAmerica/Los_Angelesを指定し、成功を確認した。

仕様の照合には [Lua 5.2 manual](https://www.lua.org/manual/5.2/manual.html#pdf-load)、
[table.insertの公式実装](https://www.lua.org/source/5.2/ltablib.c.html#tinsert)、
[数学ライブラリの公式実装](https://www.lua.org/source/5.2/lmathlib.c.html) を用いた。
Lua 5.2との一致と、既存LuaJ/現行jarの互換性は区別する。両者が異なる箇所の修正は個別に評価する。

## 互換性のために必要な判断

| 対象 | 判断 |
| --- | --- |
| パッケージ・JVM descriptor | 維持。今回の照合で未移植の独自APIはない |
| _VERSIONとJSR-223のversion | 旧配布jarのLuaj-jse 3.0.2を維持。forkの成果物名・リリース番号とは分離（実装済み） |
| スタックキャッシュ | unsafeな再構成を移植しない。寿命分離・例外・参照消去を備えた現在の修正版を基準とする |
| 冗長キャスト・生のジェネリクス | 独自高速化ではない。バイト同一化のために追加しない。reflectionの型情報差は明記する |
| 弱テーブル、fmod、modf、有限値の表示 | 既存jarにもある実不具合。0.1.0に向け別変更で正当性を修正し、コピー・GC・数値の意味を検証する |
| load / xpcall / min-max / debug | 既存の動作差・制約を最小テストへ分離する。診断文字列の更新だけで解決したことにしない |
| Cのコルーチン境界、範囲外insert、ネイティブdump | fixtureへ合わせるために現在のVM動作を戻さない。正しい対象・意味のテストに置き換える |
| タイムゾーン、関数アドレス、JMEスタブ | 環境・診断とVMの意味を分離。JSEの既定時刻やJava APIを変更してテストに合わせない |

## 再現手順

JDK 17とMavenを用意する。`MVN` はMaven実行ファイル、`MAVEN_REPO` は監査用Javaクラスパスに使うローカルリポジトリ。
通常は両方省略できる。Maven自身に独自リポジトリを渡す場合、`-Dmaven.repo.local=...` とMAVEN_REPOを同じ場所にそろえる。

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -DskipTests package
bash tools/build-baseline.sh
RECONSTRUCT_LEGACY=1 bash tools/build-baseline.sh

python3 tools/compare-jars.py ../beatoraja/lib/luaj-jse.jar build/baseline/upstream.jar build/baseline/comparison --expected-legacy-sha256 15bcbdd85ddf6f1e189093b28850c086e5bf13085cbc29595f3523444fb5fd8a
python3 tools/classify-bytecode.py build/baseline/comparison build/baseline/comparison/normalized
python3 tools/compare-jars.py ../beatoraja/lib/luaj-jse.jar build/baseline/legacy-reconstructed.jar build/reconstructed-comparison --expected-legacy-sha256 15bcbdd85ddf6f1e189093b28850c086e5bf13085cbc29595f3523444fb5fd8a
python3 tools/classify-bytecode.py build/reconstructed-comparison build/reconstructed-comparison/normalized
python3 tools/summarize-bytecode-audit.py build/baseline/comparison build/reconstructed-comparison build/bytecode-audit.json

bash tools/run-test-audit.sh ../beatoraja/lib/luaj-jse.jar build/audit/legacy
bash tools/run-test-audit.sh build/baseline/upstream.jar build/audit/upstream
bash tools/run-test-audit.sh build/baseline/legacy-reconstructed.jar build/audit/reconstructed
bash tools/run-test-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/fork

python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/fork
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/legacy --variant legacy
python3 tools/test_bytecode_classifier.py
python3 tools/test_audit_results.py
```

監査ランナーは失敗も全件記録するため、それ自体の終了コードを合否に使わず、必ずcheck-audit-regressionsを実行する。
ゲートはテスト一覧の欠落・差し替え、失敗の例外型・内容の変化、全文出力の変化を検出する。
既知の失敗が成功に変わる場合は改善として報告する。変更を反映する際は原因を確認してから基準JSONを更新する。
現在の基準を無条件に上書きせず、候補の一覧を別ファイルへ生成する。

```sh
python3 tools/summarize-audit.py build/audit build/candidate-audit-matrix.json
```

OSの原因確認のみでは、2件のclass#method一覧を作り、`AUDIT_INVENTORY=/absolute/path/list` と
`AUDIT_TIMEZONE=America/Los_Angeles` を指定して別の出力先へ実行する。
部分一覧の結果は、共通649件のゲートでは成功扱いにならない。
タイムゾーンと実験用overlayの2つの原因確認は、次のスクリプトで再現できる。
本体のソースや配布jarは変更せず、20件の実験用LuaTableは出力ディレクトリ内だけに生成する。

```sh
bash tools/run-causal-checks.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/causal
```

生の比較はdebug情報等の完全一致を要求しない。正規化は一般的な意味の等価性を証明するものではなく、
分岐先、例外ハンドラ、メンバーdescriptor、定数を残した構造比較と、固定テストによる確認を組み合わせている。
