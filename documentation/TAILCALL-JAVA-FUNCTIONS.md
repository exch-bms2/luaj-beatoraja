# Javaの関数への末尾呼び出しの高速化（試行・不採用）

2026-11-24。文字列キーのintern化に続いて試したが、**採用しなかった**。コードは元に戻してある。

不採用の理由：
- スキンへの効果がごく小さい（1フレームあたり約0.1 µs）。
- Luaの末尾再帰が+4.2%遅くなる。
- エラー位置の表示が変わる。

変更内容と追加テストは [changes/tailcall-java-inplace-trial.patch](changes/tailcall-java-inplace-trial.patch) に保存した。
JMHの `SkinLookupBenchmark.javaFunctionTailCall` と `luaFunctionTailCall` は、今後の比較用に残した。
次の対象は、intern化を含むmasterのjarでJFRを取り直してから決める。

以下は試行時の記録である。

## 動機

ModernChicの選曲画面のJFRで、`TailcallVarargs.eval → LuaClosure.onInvoke` を通る末尾呼び出しの処理が、luaj内のCPUサンプルの約12%を占めた。

スキンでは `return main_state.option(...)` や `return CUSTOM.OP.isMyFrame(i)` のような `return f(...)` が多い。
ModernChicで67か所（うち `return main_state.*(...)` が11か所）、WMII_FHDで9か所ある。

従来のluajは、末尾呼び出しのたびに次の処理をしていた。
1. `TailcallVarargs` を生成して、呼び出し元へ戻る。
2. 呼び出し元で `eval()` → `onInvoke` を経由して、呼び出し先を呼ぶ。

呼び出し先がJavaの関数でも同じだった。

C Lua 5.2（lvm.c）は、`OP_TAILCALL` の呼び出し先がCの関数なら、現在のフレームのまま通常の呼び出しとして実行する（`luaD_precall`）。
フレームを置き換えるのはLuaの関数の場合だけで、これは末尾再帰でスタックが伸びないようにするためである。

## 変更内容

`LuaClosure.execute` の `OP_TAILCALL` を変更した。
呼び出し先が `LuaFunction` かつ `LuaClosure` 以外（Javaの関数）で、DebugLibが無効なときは、`onInvoke` をその場で呼んで結果を返す。

- Luaの関数と、`__call` を持つテーブルは、従来どおり `TailcallVarargs` で処理する。末尾再帰でスタックが伸びない性質はそのまま。
- `onInvoke` を使うので、LuaJCで生成された関数が返す遅延の末尾呼び出しも、遅延のまま保たれる。
  その場合、引数がこのフレームより長く残ることがあるため、可変長と4引数以上のときは `dealias()` で引数を独立させる。
  0引数と1引数は、不変の `LuaValue` なのでそのまま渡す。
- DebugLibが有効なときは、フックとコールスタックの扱いを変えないよう、従来の経路を使う。
- 戻り値がスタックを参照していても、通常の `OP_RETURN` と同様に、呼び出し元（`onInvoke` の `dealias`、`call()` の `arg1`）がスタックの返却前に独立させる。

### エラー位置の変化

Javaの関数を末尾呼び出しして、その中でエラーになったときの位置情報が変わる。
`chunk` は次の3行のコードで、`f` の中の2行目でエラーにしている。

```lua
local function f()
  return error('boom')
end
```

| 呼び出し方 | 変更前（現行jarと同じ） | 変更後 | C Lua 5.2 |
| --- | --- | --- | --- |
| `pcall(f)` | `boom`（位置なし） | `chunk:2 boom` | `chunk:2: boom` |
| Javaから呼ぶ（スキンのプロパティと同じ） | `boom` | `chunk:2 boom` | — |
| Luaの関数内で `local x = f()`（5行目） | `chunk:5 boom` | `chunk:2 boom` | `chunk:2: boom` |
| `error('boom', 2)` | `chunk:5 boom` | `chunk:2 boom` | `chunk:5: boom` |

- レベル1（既定）では、C Luaと同じ位置になった。beatorajaのログに出るスキンのエラーにも、ファイル名と行が付くようになる。
- `error(msg, 2)` では、変更後の位置が正しくない。ただし、DebugLibが無いluajは、通常の呼び出しでもレベルを無視して一番内側のフレームを示す。変更後は通常の呼び出しと同じ扱いになっただけである。
- 区切りにコロンが無いのは、luaj本来の表記である。

## 検証

| 項目 | 結果 |
| --- | --- |
| 回帰テスト（READMEの一覧＋TailcallJavaFunctionRegressionTest） | 163件すべて成功（追加6件） |
| スイート全体 | 1019件、既知の失敗25件、新規の失敗0件 |
| 固定649件の監査 | 要確認の差分0件 |
| DebugLib無しで81スクリプトを実行（下記） | 変更前と変更後で出力の差0件 |

**固定649件の監査は、この変更を検証できていない。** 監査の大部分を占めるLuaスクリプトのテスト（`ScriptDrivenTest`）は、`debugGlobals()`（DebugLib有効）で実行される。
この変更はDebugLibが無効なときだけ有効になるため、監査では新しい経路を通らない。beatorajaはDebugLib無しで動くので、この点は特に重要である。

そこで、テスト用zipにある81のスクリプトすべてを `standardGlobals()`（DebugLib無し）で実行する方法で補った。
変更前→変更後→変更前の順に実行し、出力とエラーメッセージをスクリプトごとに比べた。
- 差が出たスクリプトは0件。
- `verybig.lua` は変更前の2回でも出力が異なる（時刻に依存）ため、比較から除外した。
- これらのスクリプトには、Javaの関数への末尾呼び出しが約80か所ある（`return pcall` 19、`return getmetatable` 12、`return coroutine.yield` 4 など）。
- エラーで終わる28スクリプトでも、エラー行は一致した。

TailcallJavaFunctionRegressionTestの6件で確認した内容：
- 単一の戻り値と多値の戻り値、`select('#', ...)` での可変長引数の数
- 引数を参照する戻り値（`select(1, ...)` 相当）が、スタックの再利用後も壊れないこと（可変長の場合と固定4引数の場合）
- Luaの末尾再帰（20万段）でスタックが伸びないこと。Lua→Java→Luaの組み合わせも確認
- `pcall` 経由での再入と、`coroutine.yield` の末尾呼び出し
- エラー位置（上の表）
- `__call` を持つテーブルが従来の経路で動くこと

## JMH

SkinLookupBenchmark と ShortCallBenchmark.tailRecursion を、変更前（A、`1634256…`）と変更後（B、`a9c63a7…`）でA→B→B→Aの順に測った。
条件は3 forks、warmup 5×1秒、measurement 5×1秒、512MiB、-prof gc。数値はns/opで、生データは `build/tailcall/jmh/` にある。

| 項目 | A1 | B1 | B2 | A2 | 変化 | B/op |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| javaFunctionTailCall（`return main_state.option(...)`） | 45.36 | 41.00 | 45.20 | 46.76 | −6.4% | 24→0 |
| luaFunctionTailCall（`return CUSTOM.OP.isMyFrame(3)`、経路は不変） | 144.41 | 135.46 | 128.51 | 136.59 | −6.1% | 56→56 |
| tailRecursion（Luaの末尾再帰、経路は不変） | 393.92 | 414.71 | 413.59 | 400.94 | +4.2% | 1040→1040 |
| skinDrawCondition | 331.32 | 321.65 | 290.66 | 290.30 | −1.5% | 80→80 |
| crossChunkFieldLookup / javaKeyTable / newStringKeyInsert | — | — | — | — | ±0.6%以内 | 変化なし |

### 評価

- **Javaの関数への末尾呼び出しは、1回あたり約3 ns速くなり、24 Bの確保がなくなった。** ただし、スキン全体で見ると効果はごく小さい。
  1フレームに数十回呼ばれても0.1 µs程度で、選曲画面のLua時間（約200 µs）の0.1%未満にしかならない。
- luaFunctionTailCallの−6%は、経路を変えていない項目なので、測定の揺れと考えられる。
- **tailRecursionは+4.2%で、2回の測定とも一貫していた。** `OP_TAILCALL` のたびに型判定（`instanceof`）が2つ増えたためと考えられる。1回の末尾呼び出しあたり約1.5 ns。
- JFRで約12%を占めていた末尾呼び出しの大半は、Luaの関数への末尾呼び出し（`return CUSTOM.OP.isMyFrame(i)` など）だったと考えられる。
  この変更はその経路を対象にしていない。なお、あのJFRは現行jarで取ったもので、forkの経路とは内訳が異なる可能性がある。
