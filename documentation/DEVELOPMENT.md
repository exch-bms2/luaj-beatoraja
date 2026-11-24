# 開発と検証

## 対象と基準

- 成果物: `org.luaj:luaj-beatoraja:0.1.0-SNAPSHOT`、JDK 17。
- LuaJ由来ソースの基点: `daf3da94e3cdba0ac6a289148d7e38bd53d3fe64`。
- 現行jar: 隣接する `beatoraja/lib/luaj-jse.jar`。
- SHA-256: `15bcbdd85ddf6f1e189093b28850c086e5bf13085cbc29595f3523444fb5fd8a`。
- 上流ライセンス、ソース内の著作権表記、READMEの履歴を保持し、配布jarにもLICENSEを格納する。

この基点と現行jarは同一ではない。ローカルで確認できた改造ソースは見つかっていない。
`javap` では現行jarのLuaClosureに、クロージャ単位の `java.util.Stack` と20本までのキャッシュを確認した。
通常復帰時にのみ配列を返却し、返却値・末尾呼び出し引数を独立させず、返却時の参照消去もない。
350クラスを照合し、独自の実行処理はこのキャッシュ、他の命令差はバージョン表記・冗長キャストとして分類した。
比較用の再構成版は、現行jarと固定649件の結果・診断出力も一致する。
原改造ソースの発見・jarのバイト同一化とは区別する。型情報・ビルド情報の差も含む詳細は
[互換性監査](COMPATIBILITY-AUDIT.md) を参照。

## 実装したスタック寿命の規則

1. 各 `call` / `onInvoke` が配列を借り、再帰・再入・yield中は返却しない。
2. `execute` のfinallyがupvalueを閉じ、デバッグフレームを終了する。呼び出しフックもtry内に置き、フックの例外でもフレームを残さない。
3. 標準のinvokeでは固定多値返却や所有済みの結果への先頭値追加を直接独立化する。既に所有済みならonInvokeのdealiasは再コピーしない。debugやexecute拡張ではfinally後の独立化を維持する。単一LuaValueはそのまま返す。
4. 配列を参照する末尾呼び出し引数は、OP_TAILCALLで独立させる。ここで末尾呼び出しを評価しない。
5. 外側finallyで参照を消去し、待機配列のみをキャッシュへ戻す。例外や引数アクセス失敗も同じ規則。

通常呼び出しは待機配列1本を原子的に取得し、参照消去後にrelease書き込みで返却する。
再帰・再入の予備プールは同期付き固定長配列スタックとする。Javaスレッドを使用するコルーチン間の
受け渡しを維持し、実行・Luaコード評価中はモニタを保持しない。
上限はクロージャごとに20本、実行スタック配列は合計1024スロット。全クロージャ合計のメモリ上限ではない。
待機中はnullで参照を消し、借用時にNILで初期化する。現段階では初期化回数削減より正当性を優先する。

JDK 17で予約される内部クラス名 `CoroutineLib.yield` を `Yield` に変更し、上流テストの識別子 `_` も変更した。
これらはパッケージ非公開で、Luaの `coroutine.yield` 名とbeatoraja向け公開APIは維持する。
`Lua._VERSION` は旧Antが生成していた現行jarと同じ `Luaj-jse 3.0.2` とし、forkの成果物バージョンとは分ける。
JSR-223のメタデータテストも、この配布時の表記を確認するよう更新した。
基点ソースをそのままMavenでビルドした比較用jarの `_VERSION` は `Luaj 0.0` のままになる。
Luaの返却値をキャッシュせず、テーブルの同一性・状態を保持する。

## ビルドとテスト

JDK 17とMavenを使用する。依存バージョンをpomで固定し、jar内タイムスタンプも固定する。
従来のAnt/JME配布ビルドは履歴として残す。JMEクラスとCLDC APIは既存テスト用で、配布jarには含めない。
BCELは従来のLuaJC機能に必要な任意依存であり、jarには同梱しない。

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -Dtest=StackLifetimeTest,StackPoolTest,WeakIntegerKeyTest,FmodRegressionTest,ModfRegressionTest,MinMaxRegressionTest,LuaDoubleFormattingTest,LoadReaderRegressionTest,PcallScopeRegressionTest,DebugLocalRegressionTest,DebugJavaFrameRegressionTest,DebugFunctionLocalRegressionTest,DebugSetLocalValueRegressionTest,DebugVarargsRegressionTest,DebugStackLevelRegressionTest,SingleCallPoolRegressionTest,MultiReturnOwnershipTest,StringInternRegressionTest test
mvn -DskipTests package
```

追加した意味の回帰テスト11件、保持メモリ・デバッグフレームの不変条件テスト3件は成功。
現行jarでは同じ意味のテスト11件中3件が失敗し、多値返却の上書き・4引数末尾再帰・遅延末尾呼び出し引数の破損を再現した。
コルーチンのyield/resume、pcallをまたぐyield、Java再入、通常／相互再帰、可変長引数、nil位置、upvalue、例外も対象にする。

既存スイートは基点ソースでも51件失敗する。古い出力比較、JMEスタブ、弱参照・数値などを含み、
これらは修正済みと見なしていない。修正前後で失敗名の集合が同一であることを確認した。
`mvn test` はこれらの既存失敗で非ゼロ終了する。既知失敗を隠さず、新規退行を判定するには以下を使う。

```sh
mvn -Dmaven.test.failure.ignore=true test
python3 tools/check-test-regressions.py documentation/upstream-test-failures.json target/surefire-reports
```

全件の結果を残し、未登録の失敗があれば後段が失敗する。部分実行の結果だけでは成功と判定しない。
登録済み失敗は [upstream-test-failures.json](upstream-test-failures.json) に記録した。
失敗数だけでなく原因の変化も今後の全互換性監査で確認する必要がある。
51件は現在すべて原因を分類済み。正式な比較には、重複を除いた固定649件を使う
`run-test-audit.sh` と `check-audit-regressions.py` を使用する。
こちらは一覧の一致に加え、例外型・診断内容・スクリプト全文・テストソースの変化も検出する。
上記の件数・失敗名のゲートは簡易確認用であり、全文比較の代わりにはしない。
その後、弱テーブル・fmod・modfを個別に修正し、新規23件が成功、固定649件の残る失敗は29件となった。
51件の元の基準は保存したまま、確認済みの差分だけを明示して比較する。
現在のゲートの実行方法と段階別結果は [正当性修正](CORRECTNESS-FIXES.md) を参照。
さらにmin/maxの数値変換と有限数値の表示を修正し、固定649件は622件成功・27件失敗となった。
最新の確認済み差分は [数値の正当性修正](NUMERIC-FIXES.md) とnumeric-fixes.jsonを使用する。
Fibonacciの3件は有限表示に改善したが、Cの桁数・表記との完全一致が必要なため失敗には残る。
続いてreaderの空文字列EOFとpcallのハンドラスコープを修正し、新規22件が成功、固定649件は624件成功・25件失敗となった。
その段階の確認済み差分と手順は [保護呼び出しとEOFの修正](PROTECTED-CALL-FIXES.md) とprotected-call-fixes.jsonを使用する。

続いてdebug.getlocal/setlocalの無効な参照・Javaフレームのnull stack例外を別々に修正した。
追加14件と従来76件が成功し、固定649件は624件成功・25件失敗を維持。3ケースの出力が部分改善し、新規退行はない。
その段階のゲートは [ローカル参照の修正](DEBUG-LOCAL-FIXES.md) とdebug-local-fixes.jsonを使用する。

さらにgetlocalの関数形式とsetlocalの値省略時検証を個別に修正した。追加19件を含む109件が成功し、
固定649件は624件成功・25件失敗を維持。同じErrorsTestの出力が段階別に改善し、新規退行はない。
その段階のゲートは [debug APIの修正](DEBUG-API-FIXES.md) とdebug-api-fixes.jsonを使用する。

さらに負の添字による可変長引数アクセスと範囲外レベルのエラーを個別に修正した。追加24件を含む133件が成功。
固定649件は624件成功・25件失敗を維持し、レベル検証の2行が部分改善、新規退行はない。
意味の比較ゲートは [debug可変長引数の修正](DEBUG-VARARG-FIXES.md) とdebug-vararg-fixes.jsonを使用する。

最新版jarをJMH基準として固定し、単値呼び出し用の1本キャッシュと予備プールの配列化を実施した。
既存133件と追加4件の計137件が全段階で成功し、固定649件の結果・診断全文も維持した。
測定値、順序交互の追試、再現手順は [単値呼び出しの性能検証](SINGLE-CALL-PERFORMANCE.md) とsingle-call-performance.jsonを参照。
性能比較時の監査には、終了後に待機JVMを残さないrun-performance-audit.shを使う。

続いて多値返却の所有済み表現・固定返却の直接生成・先頭値の結合を3変更に分けて最適化した。
既存137件と追加12件の計149件が全4段階で成功し、固定649件の結果・診断も維持した。
最新の測定値と再現手順は [多値返却の性能検証](MULTI-RETURN-PERFORMANCE.md) とmulti-return-performance.jsonを参照。

## 修正前ソースと現行jarの比較

```sh
bash tools/build-baseline.sh
python3 tools/compare-jars.py ../beatoraja/lib/luaj-jse.jar build/baseline/upstream.jar build/baseline/comparison
```

基点ソースは別ディレクトリへ `git archive` で展開する。JDK 17で旧ソースを変更せずビルドするため、
基点のみ `--release 8` を指定する。実行JVMは全構成で17にそろえる。
`MVN` 環境変数でMaven実行ファイルを指定でき、追加のMavenオプションも引数で渡せる。
比較ツールはSHA-256、クラス一覧、公開API表示、バイトコード表示を出力する。
コンパイラの生成差も報告するため、差がすべて動作変更とは限らない。

`StackLifetimeTest` は現行jar・基点・forkで共通に使用できる。
`target/test-classes` とJUnit 4.13.2、Hamcrest 1.3を、比較対象jarとともにクラスパスへ指定し、
`org.junit.runner.JUnitCore org.luaj.vm2.StackLifetimeTest` を実行する。
その際 `target/classes` や他のLuaJ jarを混在させない。

## JMH

```sh
mvn -f benchmarks/pom.xml -Dvm.jar="$PWD/target/luaj-beatoraja-0.1.0-SNAPSHOT.jar" package
bash tools/run-benchmarks.sh ../beatoraja/lib/luaj-jse.jar build/benchmarks/legacy
bash tools/run-benchmarks.sh build/baseline/upstream.jar build/benchmarks/upstream
bash tools/run-benchmarks.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/benchmarks/fork
```

同じハーネスを使い、実行時クラスパスでVMだけを切り替える。ハーネスにVMクラスを含めない。
標準は3 JVM forks、各5秒のウォームアップと測定、512MiBヒープ、GCプロファイラで確保量を記録する。
出力先にJSON、ログ、JVM情報、VMとハーネスのハッシュ、Git差分を保存する。
未追跡ファイルは一覧のみのため、測定を正式保存する前にソースをGitで管理すること。
現行jarのtailRecursionは既知不具合により測定できない。全件測定時もこのエラーを性能値として扱わない。

短い動作確認・予備測定には末尾へ以下を追加する。正式な性能判断では標準設定と実スキン測定を使用する。

```sh
'.*(zeroArguments|oneArgument|multipleResults)' -f 3 -wi 3 -i 3 -w 500ms -r 500ms
```

2026-11-24の予備測定結果（OpenJDK 17.0.19、各3 forks、上記短縮設定）:

| 経路 | 現行jar ns/op・B/op | 上流基点 ns/op・B/op | fork基準版 ns/op・B/op |
| --- | --- | --- | --- |
| 0引数・単値 | 12.47・ほぼ0 | 5.41・24 | 11.59・ほぼ0 |
| 1引数・単値 | 14.65・ほぼ0 | 7.02・24 | 14.54・ほぼ0 |
| 1引数・4値返却 | 21.60・32 | 20.68・72 | 30.63・88 |

多値返却は独立化のコピーで時間・確保量とも増えている。現行jarは保持した結果が壊れるため、
その値を正当性が同等な実装の性能として扱わない。単値経路は上流基点より確保量を減らす一方、
同期などのコストで時間が増えている。実ゲームでの速度やフレーム時間への効果は、この表から判断しない。
生データと測定対象jarのハッシュは [preliminary-jmh.json](preliminary-jmh.json) に保存した。
このハッシュはスタック修正基準版のもので、後続の弱テーブル・fmod・modf修正後のjarとは異なる。
正式なリリース性能の判定には標準設定と実スキンで再測定する。

上記の予備測定を履歴として保持し、最新版の正式なローカルJMH基準と最適化結果は
[単値呼び出しの性能検証](SINGLE-CALL-PERFORMANCE.md) を使用する。実スキンの性能判定とは分ける。

その後の多値返却の変更別結果と最新のJMHハーネスは [多値返却の性能検証](MULTI-RETURN-PERFORMANCE.md) を参照。

## 0.1.0までの残作業

- 監査で残るdebugやLuaJCのxpcall等の既存問題を切り分ける。環境・古い期待値と混在するテストを意味の回帰テストへ分離する。
- 本基準版の後、初期化・数値キャッシュ・文字列変換・固定引数経路などを一変更ずつ評価する。
- beatoraja側の文字列変換前キャッシュ、LuaStringキー、呼び出し側テーブルへ書き込むoffset API、フィールド情報キャッシュを別変更として用意する。
- A=現行/現行、B=fork/現行、C=現行/改善版、D=fork/改善版の4構成を固定する。
- 選曲・プレイ・リザルトの代表スキン、楽曲、描画設定、入力、ウォームアップ、JVM条件を固定する。
- Lua呼び出し回数／時間、CPU、確保量、GC、フレーム中央値/p95/p99、ロード時間、画面遷移後の保持メモリを測る。
- 原因調査のプロファイラ実行と性能比較を分け、長時間動作と既存スキンの互換性を確認する。

実スキンによる確保量削減とフレーム時間非悪化は未検証。0.1.0のリリース判定はまだ行わない。
数値レジスタ等の大規模改造は、この実測結果を得てから選ぶ。
