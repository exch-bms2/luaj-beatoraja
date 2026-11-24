# debug.getlocal/setlocalの個別修正

2026-11-24。段階07のjarを起点に、無効なローカル参照とJavaフレームのnull stack対策を別パッチ・別jarに分けた。
元の固定649件・期待値・audit-matrix.json・先行する確認済みJSONは保持している。

| 段階 | 固定649件の成功 | 失敗 | 全体が成功へ変化 | 出力が部分改善したケース | 累計の追加回帰テスト成功 | 新規退行 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 07 protected callまで | 624 | 25 | — | — | 76 | — |
| 08 無効なローカル参照 | 624 | 25 | 0 | 2 | 84 | 0 |
| 09 Javaフレーム | 624 | 25 | 0 | 1 | 90 | 0 |

今回追加した14件は最終版ですべて成功した。段階07に対してローカル参照の8件を実行すると5件失敗・3件成功、
段階08に対してJavaフレームの6件を実行すると6件失敗だった。
各ケースは比較対象jarだけを使用した別JVM（128MiB、5秒上限）でも確認した。
スタック・弱テーブル・数値・reader・pcallの従来76件も含むJUnit実行は90件成功した。

## 08: 有効な名前のあるローカルだけを読み書きする

[08-debug-locals.patch](changes/08-debug-locals.patch)はDebugLib.CallFrame.getLocal/setLocalと
DebugLocalRegressionTestの8件を含む。

従来はレジスタ配列内という条件だけで読み書きしていた。
Prototype.getlocalnameがnullでもgetlocalは`nil, レジスタ値`の2値を返し、
setlocalはnilを返しながら作業用レジスタを変更していた。
現在のPCで有効なローカル名が得られた場合に限りアクセスするようにした。
無効な参照はnilを1値返し、書き換えない。有効なローカルの値がLuaのnilでも、名前とnilの2値を返す。

回帰テストは有効な引数・nil値のローカル、無名レジスタの読み出し・書き込み、
負値・0・int最小/最大の添字、スコープ終了後のローカル、yield中のコルーチン、debug情報を除いたbinary chunkを対象にする。
Javaへ渡した4引数のスタック参照を観測し、無効なsetlocalが呼び出し引数を破壊しないことも確認する。

固定649件ではJME/JSEのtestDebugLibだけが変化した。各8行について、無名レジスタからの値の漏出と
無効な書き込みによる後続値の変化が消える。ほかの全文は一致する。
既存のdebugライブラリの差が残るため、この2ケースはまだ失敗として記録する。

## 09: Luaのレジスタ配列を持たないJavaフレームを扱う

[09-debug-java-frame.patch](changes/09-debug-java-frame.patch)は同じ2メソッドのnullガードと
DebugJavaFrameRegressionTestの6件を含む。段階08の後へ独立して適用できる。

pcall/xpcallや明示的に登録されたJava関数のCallFrameはstackがnullである。
配列長を参照する前に確認し、getlocal/setlocalともnilを1値返す。
Luaの呼び出し元のレジスタやJava関数の引数を変更せず、debugフレームの登録・解除の規則も維持する。

回帰テストは登録済みJavaフレームでのgetter/setter、添字境界、pcallのLua呼び出し元、
xpcall内でのアクセス後の意図した例外とハンドラ、yield中のpcallフレーム、Luaフレーム使用後の再利用を確認する。
xpcallテストではアクセス後に到達したことを別のフラグで確認し、予期しない例外をハンドラが捕捉しただけでは成功しない。

固定649件ではErrorsTest.testDebugLibArgsだけが変化した。
正しい引数での6行のnull stack例外が消え、値引数を省略したsetlocalの2行も同じ例外を出さなくなる。
値引数省略時にエラーを要求する既存期待との差は残っており、今回修正済みとは扱わない。
function形式のgetlocal、負の添字による可変長引数、C版のtemporary名の提供は今回の変更範囲に含めていない。
LuaJのPrototypeに登録された有効な名前を対象とする。

## 比較の再現

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -Dtest=StackLifetimeTest,StackPoolTest,WeakIntegerKeyTest,FmodRegressionTest,ModfRegressionTest,MinMaxRegressionTest,LuaDoubleFormattingTest,LoadReaderRegressionTest,PcallScopeRegressionTest,DebugLocalRegressionTest,DebugJavaFrameRegressionTest test
mvn -DskipTests package
bash tools/run-test-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/current --reviewed-changes documentation/debug-local-fixes.json --stage 09-debug-java-frame
python3 tools/run-regression-cases.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/debug-regressions/current --classes DebugLocalRegressionTest DebugJavaFrameRegressionTest --expect-pass
```

Mavenキャッシュを別の場所へ指定する場合はMavenの`-Dmaven.repo.local`とスクリプト用の`MAVEN_REPO`を同じ場所に指定する。
段階08のjarには`--stage 08-debug-locals`を使用する。
確認済み差分の候補を別ファイルへ再生成するには次を使う。

```sh
python3 tools/review-debug-stages.py build/audit build/candidate-debug-local-fixes.json
```

このレビューは前段07の全結果との一致、649件の一覧、変更したケースの集合、
指定行の変換だけで全文が一致すること、例外型、各段階の回帰テストを確認する。
既知の失敗ケース全体を許可する扱いにはしていない。
ゲートは固定テストソースと新規回帰テストソースのハッシュも確認する。

段階別jar・JUnitログはbuild/correctness-stages/08-*・09-*、全文はbuild/audit/08-debug-locals/・09-debug-java-frame/にある。
2パッチを順に適用すると対象ソースと新規テスト2ファイルをバイト単位で再現できることも確認した。

| jar | SHA-256 |
| --- | --- |
| 07 | bcb6dcafcf5f077d94d85a36238d295bd8aa1cac7dcae5b9f1e388e4a8bb8786 |
| 08 | c5e42c8958d02b8d325e269128ad99cce967b35bc38a8f9025051f126c13a5fa |
| 09 / targetのjar | 863f41f339373116275c4b1367b4f86cb65fe54cbffece002bf6b5772929ef84 |

残る25件は引き続き失敗として可視化する。今回の比較は正当性の検証であり、速度や確保量の改善率は測定していない。

後続のgetlocal関数形式・setlocal値引数検証と最新のゲートは [debug APIの修正](DEBUG-API-FIXES.md) を参照。
