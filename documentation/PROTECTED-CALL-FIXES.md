# load readerのEOF・pcall/xpcallスコープの個別修正

2026-11-24。前段05の数値表示修正済みjarを起点とし、2変更を別パッチ・別jarで確認した。
固定649件の一覧、元のaudit-matrix.json、先行する確認済みJSONは上書きしていない。

| 段階 | 固定649件の成功 | 失敗 | 直前から成功へ変化 | 今回の回帰テスト | 最終版の新規退行 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 05 数値表示まで | 622 | 27 | — | — | — |
| 06 reader EOF | 622 | 27 | 0 | 10件成功 | 0 |
| 07 protected call | 624 | 25 | 2 | 累計22件成功 | 0 |

新規22件を修正前jarでテストごとのJVMへ実行すると、14件失敗・8件成功だった。
最終jarでは22件すべて成功する。以前の新規40件も含めた段階別実行では06が50件、07が62件成功。
スタック関連14件を含む確認では76件が成功した。

## 06: 空readerを永続的なEOFにする

独立差分: [06-reader-eof.patch](changes/06-reader-eof.patch)。対象はBaseLib.StringInputStream、回帰テストはLoadReaderRegressionTest 10件。

readerの空文字列に対してread()が一度だけ-1を返し、remainingを0のまま残していた。
次のread()でreaderを再呼び出すため、空文字列の後のソースをつなげたり、終了後のreader例外を実行したりしていた。
空文字列でもremainingを-1へ変え、nilと同じ永続的なEOFにする。

テストは最初・途中の空文字列、nil・返却なし、途中で切れたtext、Lua/Java reader例外、
メッセージのないJava例外、reader内のyield/resume、yield後の例外、binaryの正常読み込みと切断を確認する。
空文字列の後に置いたデータ・例外は実行されず、読み込みエラーは従来のnil/errorとして返る。
例外の既存のchunk情報・診断形式は維持する。

649件で変わったのはJME/JSE/LuaJCのtestBaseLibの各1行だけで、誤って出ていた`after empty string`が消える。
この段階では別のxpcallの不一致が残るため、3件とも全体の失敗数には残る。

## 07: pcallの境界で外側ハンドラを遮断・復元する

独立差分: [07-protected-call-scope.patch](changes/07-protected-call-scope.patch)。対象はBaseLib.pcall、回帰テストはPcallScopeRegressionTest 12件。

LuaClosureはエラー時にLuaThread.errorfuncを参照する。
外側xpcallのerrorfuncを残したまま内側pcallを実行すると、pcallが捕捉するエラーにまで外側ハンドラを適用してしまう。
pcallの開始時に現在のハンドラを保存してnullへ切り替え、終了時に元のLuaThreadへ復元する。
内側xpcallは独自のハンドラを使用でき、pcall終了後に外へ逃げたエラーは復元された外側ハンドラで扱う。

復元はfinallyで行い、debugのonReturnが例外を投げても実行する。
onCallも保護されたtry内に置き、call hookの例外でdebugフレームを残さない。
yield中はそのpcallのスコープを維持し、resume後に同じコルーチンへ復元する。

### yieldと孤立コルーチンの回収

最初の実装でLuaThreadを強参照のlocalへ保存すると、yield中のJavaスタックがLuaThreadを保持し、
既存のtestCollectOrphanedPcallClosureThreadが新たに失敗した。
その退行を固定649件で検出し、復元用の所有者をWeakReferenceに変更して解消した。
所有者が回収されていれば復元を省略し、別スレッドのハンドラへ書き戻さない。
この回収条件を新規テストにも追加した。既存の孤立スレッドテスト6件も成功している。

pcallごとに復元用WeakReferenceが1個追加される。性能・確保量の比較は今回行っておらず、正当性の基準として扱う。

### 回帰テストの範囲

- 内側pcallで捕捉したエラーでは外側ハンドラが呼ばれない。
- 後で外へ逃げるエラーでは復元したハンドラが1回だけ呼ばれる。
- 入れ子のxpcallでは最も内側のハンドラだけを使う。
- pcallで捕捉するtableのエラーオブジェクト、多値・nil位置を保持する。
- Javaからの再入・Java例外の捕捉後もハンドラを復元する。
- ハンドラ自体の失敗、ハンドラ内のpcall、ハンドラからのyieldを扱う。
- yieldで中断中にmain threadの別のxpcallを実行しても混同しない。
- call/return hook例外でハンドラとdebugフレームの後処理を行う。
- 放棄されたyield中のpcallコルーチンをGCできる。

649件ではJME/JSEのtestBaseLibが成功へ変化し、全文も既存のexpectedと一致する。
変化は`xpcall(wrappedbad,errfunc)`の前に誤って出ていたhandlerの出力1行だけ。
LuaJCのtestBaseLibには、既存の「Javaコンパイル済み関数のxpcallでhandlerが呼ばれない」差が残り、この段階では全文も変わっていない。
新しく失敗したケースや、確認した行以外の出力変化はない。

loadのEOFと保護呼び出しの意味は [Lua 5.2 manualのload](https://www.lua.org/manual/5.2/manual.html#pdf-load)、
[pcall](https://www.lua.org/manual/5.2/manual.html#pdf-pcall)、
[公式の保護呼び出し実装](https://www.lua.org/source/5.2/lbaselib.c.html#luaB_pcall) を参照した。

## 比較データと再実行

[protected-call-fixes.json](protected-call-fixes.json) に先行5変更を継承し、06/07の変化したケースだけを追加した。
jar・個別パッチ・新規テストのハッシュ、before/after、全文差分、新規テストの修正前後結果を保存した。
readerは指定の1行削除だけ、pcallは指定の文脈内のhandler出力削除だけで全文が一致することを検証する。
pcallで成功へ変わった2件はexpected全文とも一致する。

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -Dtest=LoadReaderRegressionTest,PcallScopeRegressionTest,OrphanedThreadTest test
mvn -DskipTests package
bash tools/run-test-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/current --reviewed-changes documentation/protected-call-fixes.json --stage 07-protected-call
```

段階06は`--stage 06-reader`でそのjarの結果と比較する。
1テスト1 JVM、128MiB、上限5秒の確認には、新規2クラスを明示する。
修正前jarへ実行する場合は--expect-passを外して失敗も記録する。

```sh
python3 tools/run-regression-cases.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/protected-regressions/current --classes LoadReaderRegressionTest PcallScopeRegressionTest --expect-pass
```

今回のjarとJUnitログは`build/correctness-stages/06-*`と`07-*`、全文は`build/audit/06-reader/`と`07-protected-call/`に保存した。
BaseLibの既存CRLFを保ち、2パッチを順に適用して現在の対象3ファイルをバイト単位で再現できることも確認した。
変更のない従来の比較基準を保持し、候補の確認済みJSONは別名で生成できる。

```sh
python3 tools/review-protected-stages.py build/audit build/candidate-protected-call-fixes.json
```

残る25件は既存のfixture・環境・debug・LuaJC等の問題で、mvn testはこれらの失敗で非ゼロ終了する。
既知の失敗全体を一括許可したり、期待値を現在の出力で上書きしたりしていない。
正式な比較には上記の固定649件・確認済み差分のゲートを使用する。

後続のdebug.getlocal/setlocalの個別修正と最新のゲートは [ローカル参照の修正](DEBUG-LOCAL-FIXES.md) を参照。
