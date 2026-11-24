# debug.getlocalの関数形式・setlocalの値引数検証

2026-11-24。段階09のjarを起点に、2変更を別パッチ・別jarで検証した。
固定649件の一覧・期待値・audit-matrix.json・先行する確認済みJSONは保持している。

| 段階 | 固定649件の成功 | 失敗 | 全体が成功へ変化 | 出力が部分改善したケース | 累計の追加回帰テスト成功 | 新規退行 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 09 Javaフレームまで | 624 | 25 | — | — | 90 | — |
| 10 getlocal関数形式 | 624 | 25 | 0 | 1 | 100 | 0 |
| 11 setlocal値引数検証 | 624 | 25 | 0 | 1 | 109 | 0 |

各段階で部分改善したのは同じErrorsTest.testDebugLibArgsである。
残る引数エラーメッセージ等の差によりケース全体は引き続き失敗として記録する。
今回の19件と従来90件、合計109件の回帰テストはすべて成功した。
1件1 JVM・128MiB・5秒上限の比較でも、関数形式の10件は段階09で10件失敗、段階10で10件成功、
値引数の9件は段階10で6件失敗・3件成功、段階11で9件成功となった。

## 10: debug.getlocalの関数形式

独立差分: [10-debug-function.patch](changes/10-debug-function.patch)。
DebugLib.getlocalとDebugFunctionLocalRegressionTestの10件を含む。

[Lua 5.2の仕様](https://www.lua.org/manual/5.2/manual.html#pdf-debug.getlocal)に合わせ、
最初の対象が関数なら固定引数の名前だけを1値で返す。関数本体の実行や実行中のスタックは必要ない。
LuaClosureのPrototypeについて、固定引数の範囲内でPC 0のローカル名を取得する。
範囲外、Java関数、debug情報を除去した関数はnilを1値返す。
任意のthread引数にも対応し、指定threadにフレームがない場合や終了済みの場合でも名前を取得できる。
数値のスタックレベルを指定する従来の経路は維持する。

テストは未実行の関数、本文を実行しないこと、名前だけの返却型・個数、本文のローカルやupvalueの除外、
引数なし・main chunk、可変長引数、添字境界、Java関数、明示的thread、実行中の同じ関数、
stripしたbinary、数値文字列の添字、余分な引数、欠落・不正な添字を確認する。

固定649件ではErrorsTest.testDebugLibArgsの9行だけが変化した。
関数形式の3行が引数名x/yを返し、残り6行は添字の検証へ進むため診断が変わる。
不正な数値文字列の1行は既存のnumber expected期待とも一致する。
他のケース、その他の出力、例外型は一致した。

## 11: debug.setlocalの値省略を拒否する

独立差分: [11-debug-setlocal-value.patch](changes/11-debug-setlocal-value.patch)。
DebugLib.setlocalとDebugSetLocalValueRegressionTestの9件を含む。段階10の後へ適用する。

args.argで省略値をnilと見なしていた箇所をargs.checkvalueに変更した。
[Lua 5.2の実装](https://www.lua.org/source/5.2/ldblib.c.html#db_setlocal)も値の存在を確認する。
値を省略するとLuaErrorのvalue expectedを返し、明示的なnilは有効な値として受け付ける。
引数番号はthreadなしで3、threadありで4となる。
値の確認はフレーム探索や書き込みの前に行い、無効なローカルや存在しないフレームでも省略を見逃さない。
レベル・添字を数値へ変換する既存の検証順序は維持する。

テストはthreadの有無、通常Luaローカルを破壊しないこと、明示的nilの代入と返却名、
Javaフレームへの明示的nil、無効なローカル・フレーム、yield中のコルーチンの値保持、
pcall/xpcallでの捕捉とハンドラ・フレームの後処理、先行するレベル・添字の型検証を確認する。

固定649件ではErrorsTest.testDebugLibArgsの2行だけが変わり、
省略時にnilを返していた箇所が既存のvalue expected期待に一致するようになった。
明示的nilの行を含むその他の全文は一致する。既知の失敗をまとめて許可してはいない。

## 再現と比較ゲート

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -Dtest=DebugFunctionLocalRegressionTest,DebugSetLocalValueRegressionTest test
mvn -DskipTests package
bash tools/run-test-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/current --reviewed-changes documentation/debug-api-fixes.json --stage 11-debug-setlocal-value
python3 tools/run-regression-cases.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/debug-api-regressions/current --classes DebugFunctionLocalRegressionTest DebugSetLocalValueRegressionTest --expect-pass
```

従来分を含む109件の実行クラスはREADMEのMavenコマンドを参照。
別のMavenキャッシュを使用するときはMavenの-Dmaven.repo.localとスクリプトのMAVEN_REPOをそろえる。
段階10のjarには--stage 10-debug-functionを指定する。

```sh
python3 tools/review-debug-api-stages.py build/audit build/candidate-debug-api-fixes.json
```

前段09の全結果、固定649件の一覧、変更ケースの集合、指定した9行・2行の変換だけで全文が一致すること、
例外型、各段階の回帰テストを検証し、既存の基準を上書きせず確認済み差分の候補を生成する。
確認済みJSONを使用するゲートは、固定テストと追加回帰テストのソースハッシュも確認する。
今回も各段階で変更確認を必要とする未登録差分は0だった。

jar・JUnitログはbuild/correctness-stages/10-*・11-*、全文はbuild/audit/10-debug-function/・11-debug-setlocal-value/に保存した。
2パッチの順次適用で対象ソースと新規テスト2ファイルをバイト単位で再現できることも確認した。

| jar | SHA-256 |
| --- | --- |
| 10 | 98957fcd2850094277cc123c8cf5709bed32254e7a691edfb3eb53d51dd236b8 |
| 11 / targetのjar | 991fbcc0f4a0218e765345abba242212e5d232abbe29201bb1bf420134d19b95 |

負の添字による実行中の可変長引数取得、C版のtemporary名、範囲外レベルの扱い、
既存の引数型エラー表記・検証順序の差は今回の変更範囲に含めていない。残る25件も失敗として保持する。
速度・確保量の測定は今回行っていない。

後続の負の添字・レベル検証と最新のゲートは [debug可変長引数の修正](DEBUG-VARARG-FIXES.md) を参照。
