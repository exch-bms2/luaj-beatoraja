# テーブルの数値をboxしたまま保持する（保留）

2026-11-25。masterのjar（intern化済み）で取り直したJFRを受けて試した変更。
**採否は保留中で、コミットしていない。**

## 動機（masterのjarでのJFR、1 msサンプリング）

| | 選曲（ModernChic） | リザルト（WMII） |
| --- | ---: | ---: |
| 描画スレッドのJava CPUに占めるluaj | 64% | 83% |
| `LuaInteger`/`LuaDouble.valueOf` | 6.6% | 8.4% |
| うち `LuaTable$NumberValueEntry.value` 経由 | — | 4.3% |
| 描画スレッドの確保量に占める `LuaInteger`/`LuaDouble` | 87% | 81% |

luajは、文字列キーなど整数以外のキーに対する数値の値を、`NumberValueEntry` に `double` として保持していた。
そのため、読むたびに `valueOf(double)` で新しい `LuaInteger` または `LuaDouble` を作っていた。−256〜255の外の値と小数は、毎回オブジェクトの確保になる。

## 変更内容

`LuaTable.defaultEntry` で数値の値も `NormalEntry` に保持し、`NumberValueEntry` を削除した。
`NormalEntry` はもともと値をその場で更新するので、`t.x = t.x + 1` でエントリが新しく作られることもない。

Luaの意味は変わらない。`LuaDouble.valueOf` は整数値のときに必ず `LuaInteger` を返すため、`5.0` を値に持つ `LuaDouble` は存在しない。
つまり、保存した数値オブジェクトをそのまま返しても、従来の再変換と同じ型・値になる。

パッチは [changes/23-table-number-values.patch](changes/23-table-number-values.patch)、テストは [TableNumberValueRegressionTest](../test/junit/org/luaj/vm2/TableNumberValueRegressionTest.java)（5件）。

## 検証

| 項目 | 結果 |
| --- | --- |
| 回帰テスト | 162件すべて成功（追加5件） |
| スイート全体 | 1018件、既知の失敗25件、新規の失敗0件 |
| 固定649件の監査 | 要確認1件（`ErrorsTest#testDebugLibArgs`）→ 確認のうえ段階14として記録し、0件 |
| DebugLib無しで81スクリプトを実行 | 差0件（`verybig.lua` は除外） |

`ErrorsTest#testDebugLibArgs` の差は、オブジェクトの識別ハッシュの値だけだった。
- `debug.setmetatable` の行に出る `table: 5822ecda` などのアドレス
- `debug.upvalueid` の値（8桁か9桁かで末尾の `...` の有無が変わる）

識別ハッシュの値はjarごとに決まっていて、同じjarなら毎回同じになる（変更前のjarでは監査を2回とも通過した）。
JVMが生成する識別ハッシュの並びが変わっただけで、テーブルの数値とは関係ない。このテストは既知の失敗で、状態と例外型も同じである。
`LuaJCCompatibilityTest#testStringLib` の出力にも、クラスローダーの `@73bb573d` の差があったが、監査はこれを正規化するため検出されない。
記録は [table-number-value-fixes.json](table-number-value-fixes.json) の段階 `14-table-number-values`（debug-vararg-fixes.jsonの13段階に追加）。

```sh
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/numvalue --reviewed-changes documentation/table-number-value-fixes.json --stage 14-table-number-values
```

## JMH（SkinLookupBenchmark、A→B→B→A、3 forks）

| 項目 | A1 | B1 | B2 | A2 | 変化 | B/op |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| tableNumberReads（WMIIのgetScoreInfo相当） | 678.19 | 670.51 | 650.56 | 742.09 | −7.0% | **680→368** |
| crossChunkFieldLookup（`MAIN.OP.*` などの数値を読む） | 94.17 | 67.90 | 71.74 | 99.57 | **−27.9%** | 0→0 |
| skinDrawCondition | 302.51 | 321.43 | 321.52 | 304.15 | +6.0% | 80→80 |
| luaFunctionTailCall | 135.16 | 153.23 | 153.52 | 145.42 | +9.3% | 56→56 |
| javaFunctionTailCall / javaKeyTable / newStringKeyInsert | — | — | — | — | ±1.3%以内 | 変化なし |

悪化した2項目を10 forksで測り直した（生データは `build/numvalue/jmh10/`）。

| 項目 | 変更前の各forkの平均（ns） | 変更後の各forkの平均（ns） |
| --- | --- | --- |
| luaFunctionTailCall | 125.5〜139.0（10本とも） | 129.0〜143.4が4本、**164.7〜171.3が6本** |
| skinDrawCondition | 中央値301.4、平均304.0（CI 293〜315） | 中央値310.5、平均318.3（CI 308〜328） |

luaFunctionTailCallは、変更後だけ二峰性になる。JVMによって、速い状態と遅い状態のどちらかになる。
`-XX:+PrintInlining` と `-XX:+PrintCompilation` で、速いJVMと遅いJVMを比べた。インライン化の判断と、コンパイルの順序・段階は同じだった。
巨大な `execute`（4445 bytes）の中に、テーブル参照などがインライン化される。そのため、エントリの型が変わると、ウォームアップ中に集まる型やbranchのプロファイルが変わり、C2が生成するコードの質が揺れると考えられる。確定はしていない。

## 判断材料

- 対象とした数値の読み取りは確実に改善した（−7〜−28%、確保量−46%）。
- 一方、Luaの関数への末尾呼び出しで、JVMによっては18%遅くなる。実機で比べても、1回ずつの揺れが15〜30%あるため判定できない。
- 根本には、`execute` が巨大なため、JITの結果がプロファイルに左右されやすいという問題があると考えられる。
  これはJFRで最大の割合（42〜56%）を占める部分でもある。先に `execute` を小さくしてJITの結果を安定させ、そのうえでこの変更を評価し直す、という順序も考えられる。

## 追記：execute縮小後に再評価（2026-11-25）

[execute の縮小](EXECUTE-SIZE.md) の上でも、10 forksで比べた。結果は、luaFunctionTailCall +4.3%（遅いモードが5/10）、skinDrawCondition +6.7%、tableNumberReads −5.8%。
JITの遅いモードは解消しなかった。スキンでよく使う経路が遅くなる分のほうが大きいため、この変更は採用しない方向とする。
