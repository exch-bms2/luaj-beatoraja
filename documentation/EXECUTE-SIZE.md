# execute の縮小

2026-11-25。JFRで最大の割合（描画スレッドのJava CPUの42〜56%）を占める `LuaClosure.execute` を小さくし、JITの結果を安定させることを狙った変更。
**採用した**（2026-11-25）。 パッチは [changes/24-slim-execute.patch](changes/24-slim-execute.patch)。

## 変更内容

`execute` のバイトコードを **4444 bytes → 2967 bytes（−33%）** にした。Luaの意味、エラー位置に使う `pc`、評価の順序は変えていない。

1. **出口を1つにした。** ループ内の `return X;`（TAILCALLに5か所、RETURNに8か所）を、`result = X; break loop;` に置き換えた。
   javacは `try/finally` の中の `return` ごとに `finally` 節を複製するため、以前は同じコードが約10回複製されていた（RETURNが714 bytes、TAILCALLが550 bytes）。
   `finally` の本体（upvalueを閉じる処理とdebugフック）は、`exitFrame` メソッドに移した。
2. **使用頻度の低い命令を別メソッドに移した。** 対象は `LOADKX` の検証、`CONCAT`、`JMP` のupvalueを閉じるループ、`FORPREP`、`TFORCALL`、`SETLIST`、`CLOSURE`、`RETURN` の可変長の場合。
   `pc` を進める処理はメインループに残したので、例外時の位置は従来と同じである。

縮小後の大きい部分は、CALL（438 bytes）、TAILCALL（230）、RETURN（110）と、ホットな命令だけになった。

## 検証

| 項目 | 結果 |
| --- | --- |
| 回帰テスト | 157件すべて成功 |
| スイート全体（cleanしたtargetで実行） | 1013件、既知の失敗25件、新規の失敗0件 |
| 固定649件の監査（この変更はDebugLib有効時の経路も通る） | 要確認の差分0件 |
| DebugLib無しで81スクリプトを実行 | 差0件（`verybig.lua` は除外） |

## JMH（A=master `1634256…`、B=縮小後 `ffa1978…`、A→B→B→Aの順、3 forks）

最後のA2では、`execute` を通らない項目（javaKeyTable 68→82、newStringKeyInsert 72→81）まで一様に遅くなった。
これは測定環境の変動（発熱など）なので、比較はA1とだけ行う。

| 項目 | A1（各forkの平均） | B1 / B2 | 評価 |
| --- | --- | --- | --- |
| recursiveSingleResult | 213 219 221 | 204 208 209 / 204 205 209 | 約−4%（一貫している） |
| zeroArguments / oneArgument / tailRecursion | — | — | 差なし |
| SkinLookupBenchmarkの8項目 | — | — | A1と同程度（揺れの範囲） |

速度の改善は、通常の再帰で約4%だけだった。forkごとのばらつきが小さくなったかは、3 forksでは判断できない。

### 数値boxing変更との組み合わせ（10 forks、S→N→N→Sの順で5 forksずつ）

縮小後のjar（S）と、縮小後＋[数値boxingの変更](TABLE-NUMBER-VALUES.md)（N、`1e69829…`）を比べた。
数値は中央値で、括弧内は10 forks分の最小〜最大。

| 項目 | S | N | 変化 |
| --- | --- | --- | --- |
| luaFunctionTailCall | 143.0 ns（134〜154） | 149.1 ns（134〜171。155以上が5本） | +4.3% |
| skinDrawCondition | 315.3 ns（285〜405） | 336.4 ns（295〜345。332以上が7本） | +6.7% |
| tableNumberReads | 692.3 ns | 651.9 ns | −5.8%（確保量680→368 B） |

**縮小しても、数値boxing変更による遅いモードは解消しなかった。** draw条件とLuaの末尾呼び出しは、数値の読み取り以上に遅くなる。
