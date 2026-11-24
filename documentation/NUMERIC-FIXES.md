# min/max・有限数値の文字列化の個別修正

本書は段階04/05の記録。続くreader EOFとpcall/xpcallの結果・現在の比較ゲートは [保護呼び出しとEOFの修正](PROTECTED-CALL-FIXES.md) を参照。

2026-11-24。前段の弱テーブル・fmod・modf修正済みjarを起点とし、2変更を別パッチ・別jarで検証した。
歴史的な649件の一覧とaudit-matrix.json、前段のcorrectness-fixes.jsonは上書きしていない。

| 段階 | 固定649件の成功 | 失敗 | 直前から成功へ変化 | 今回の回帰テスト | 新規退行 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 03 modfまで | 620 | 29 | — | — | — |
| 04 min/max | 622 | 27 | 2 | 8件成功 | 0 |
| 05 数値表示 | 622 | 27 | 0 | 累計17件成功 | 0 |

新規17件を修正前jarで実行すると14件失敗・3件成功、最終jarでは17件すべて成功した。
以前の新規23件も含めた段階別実行では、04で31件、05で40件が成功。
スタック関連14件も含む確認では54件が成功した。

## 04: min/max

独立差分: [04-minmax.patch](changes/04-minmax.patch)。対象はMathLib、回帰テストはMinMaxRegressionTest 8件。

最初の引数と以後のすべての引数をchecknumberで検証・変換してから比較する。
`max('2','10')` は数値10、`min('2')` はnumberの2を返す。
単一の不正引数も拒否し、tableの比較メタメソッドへ処理を渡さない。
数値の引数は元のLuaNumberを使い、返却数は1のまま。

テストは数値文字列だけの比較、混在、指数表記、空白、小数、double/整数境界、NaNの位置、無限大、
不正引数の各位置、Luaのtype()、保持した返却値を確認する。
Lua 5.2の数値変換・比較順序は [公式の数学ライブラリ](https://www.lua.org/source/5.2/lmathlib.c.html#math_min) と照合した。

### 649件での改善

- JSEとLuaJCのtestMathLibが成功へ変化。
- JMEのtestMathLibはmin/max部分が参照出力と一致するが、JSE専用のacos等の出力を期待するfixtureとの差で失敗が残る。修正前のmin/maxの不一致に隠れていた既存差である。
- ErrorsTest.testMathLibArgsもmin/max部分全体が参照出力と一致する。atan2の第2引数省略時等の既存差が残るため、テスト全体は失敗のまま。

JME/JSE/LuaJCのmathlibのmax開始から乱数テスト直前まで、およびmathlibargsのmax開始からrandom直前までだけを
既存のexpected領域へ置換すると、actual全文と完全に一致することを検証した。
不一致をケース単位で一括許可せず、領域外の変更を拒否する。

## 05: 有限数値の文字列化

独立差分: [05-double-format.patch](changes/05-double-format.patch)。対象はLuaDouble、回帰テストはLuaDoubleFormattingTest 9件。

大きな有限doubleをfloatへ狭めることでInfinityになっていた経路を修正した。
さらに、2^63をlong上限へ飽和変換して整数文字列にしてしまう境界と、極小の非ゼロ値をfloatの0に潰す経路を修正した。

- 実際のNaN・無限大は従来どおりnan / inf / -inf。
- longの半開区間 `[-2^63, 2^63)` 内の整数は従来の整数表記。
- この区間外の有限値はDouble.toStringを使用するため、floatの範囲を超える有限値も失われない。
- 区間内の非整数は従来のfloat表記を保ち、floatへ変換すると0になる非ゼロ値だけDouble.toStringへ切り替える。

例えば1e40は `Infinity` から `1.0E40` へ、最小doubleは `0.0` から `4.9E-324` へ改善する。
通常範囲の既存の桁数・丸め方は維持しており、double全域の表示精度を一括変更したものではない。
数値オブジェクト内の値や演算結果、Luaでのnumber/stringの型区分は変更しない。

テストは±Double.MAX_VALUE、Float.MAX_VALUE前後、最小subnormal、最小normal、±2^63前後、
実際のNaN・無限大、通常表記、JavaとLuaの文字列型、tostring→tonumber、連結、Fibonacciを確認する。
Doubleへ切り替える境界では、文字列をパースしたdoubleのビットが入力と一致することも確認した。

### 649件での改善

変化したのはJME/JSE/LuaJCのtestManyUpvalsの各1行だけ。

```text
199th fibonacci number is  Infinity
                       →  1.7340252117279783E41
```

この有限値は独立に行ったdoubleでのFibonacci反復計算と一致する。
native Cのfixtureは `1.734025211728e+41` という桁数・指数表記を要求するため、3件ともテスト全体では失敗が残る。
有限数値の表示は修正済みだが、この完全一致の期待値を自動的に更新して成功扱いにはしない。
それ以外のケース・診断・全文出力は04の結果から変化していない。

## 比較基準と再実行

[numeric-fixes.json](numeric-fixes.json) は先行する3変更の確認済みレコードを継承し、04/05の変化したケースだけを追加したもの。
jar・パッチ・新規テストのハッシュ、before/after、全文差分、修正前後の新規テスト結果を保存した。
元の基準や先行する3変更のJSONは変更していない。

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -Dtest=MinMaxRegressionTest,LuaDoubleFormattingTest test
mvn -DskipTests package
bash tools/run-test-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/current --reviewed-changes documentation/numeric-fixes.json --stage 05-double-format
```

段階04は `--stage 04-minmax` でそのjarの結果と比較する。
今回のjarとJUnitログは `build/correctness-stages/04-*` / `05-*`、649件の全文は
`build/audit/04-minmax/` / `05-double-format/` に保存した。
パッチ04と05は、前段03のソースへ順番に適用して再現できる。

1テスト1 JVM、128MiB、上限5秒の確認では、新しい2クラスを明示する。

```sh
python3 tools/run-regression-cases.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/numeric-regressions/current --classes MinMaxRegressionTest LuaDoubleFormattingTest --expect-pass
```

確認済みの領域・有限値以外が変化していないことを再検証し、候補JSONを別名で生成するには以下を使う。
既に保存した段階別の結果・JUnitログ・新規テスト結果を入力にする。

```sh
python3 tools/review-numeric-stages.py build/audit build/candidate-numeric-fixes.json
```

固定649件のゲートは一覧・診断・全文出力・テストソースを引き続き検証する。
既知の失敗testManyUpvalsへ別の出力を追加する負の検査でも、ゲートが拒否することを確認した。
残る27件は環境・fixtureやload/xpcall・debug等の既存問題で、今回の性能・実スキンへの効果は未測定。
