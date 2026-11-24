# debugの可変長引数・スタックレベルの個別修正

2026-11-24。段階11を起点に、2変更を別パッチ・別jarに分けて検証した。
固定649件の一覧・既存期待値・元のaudit-matrix.json・先行する確認済みJSONは保持している。

| 段階 | 固定649件の成功 | 失敗 | 全体が成功へ変化 | 出力が部分改善したケース | 累計の追加回帰テスト成功 | 新規退行 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 11 値引数検証まで | 624 | 25 | — | — | 109 | — |
| 12 可変長引数 | 624 | 25 | 0 | 0 | 123 | 0 |
| 13 レベル検証 | 624 | 25 | 0 | 1 | 133 | 0 |

追加24件は最終版ですべて成功した。段階11に対する可変長引数の14件は11件失敗・3件成功、
段階12に対するレベル検証の10件は8件失敗・2件成功だった。
各ケースは比較対象jarだけを使用する別JVM（128MiB、5秒上限）でも確認している。
従来109件を含むJUnit実行とMavenの対象テスト実行は133件成功した。

## 12: 負の添字で可変長引数を取得・変更する

[12-debug-varargs.patch](changes/12-debug-varargs.patch)はLuaClosure・DebugLibと
DebugVarargsRegressionTestの14件を含む。

[Lua 5.2の実装](https://www.lua.org/source/5.2/ldebug.c.html#findvararg)に合わせ、-1から順に可変長引数を参照する。
getlocalは名前`(*vararg)`と値の2値、setlocalは同じ名前の1値を返す。
存在しない添字、非可変長関数、Javaフレームはnilを1値返し、変更しない。
int最小値でも符号反転のオーバーフローを起こさない範囲判定にした。
関数形式のgetlocalは引き続き固定引数名だけを対象とし、負の添字にnilを返す。

CallFrame.vは各命令の一時的な多値結果で上書きされるため、元の可変長引数の保持先には使用できない。
デバッグ有効時のLuaClosureで、可変長引数がある場合にDebugVarargsを用意し、CallFrameへ別フィールドで保持する。
終了時のresetで参照を解除する。既存のonCallシグネチャは維持し、内部VM/debug連携用のネスト型を追加した。

保持する値は入口で独立させる。最初の実装では元の引数への参照を残したため、
yield中に呼び出し元のレジスタが再利用され、再開後の引数が変わることを回帰テストが検出した。
入口のdealiasで解消し、コルーチンの中断中も元の値を保持するようにした。
setlocalの書き込みは毎回新しい配列へ値をコピーして置き換える。
OP_VARARGはその時点の値を読み出し、後の書き込みが取得済みの結果や別関数へ渡した引数を変えないようにする。
値そのもののテーブル等は共有し、同一性やnil位置、返却数は維持する。

テストは名前・型・個数、途中と末尾のnil、後続の可変長引数命令への反映、固定個数の読み出し、
添字境界、引数なし・非可変長関数・Javaフレーム、Javaの1～3引数call、元の引数配列の保持、
実行中の別関数へ渡した引数の保持、yield/resume、再帰、call hook、例外とフレーム再利用、
保持済み返却値の再呼び出し後の安定性、stripしたbinaryを確認する。
call hook内のフレーム参照は、hook自身のフレームを登録しない既存LuaJの規則に合わせている。

固定649件は、例外・診断・スクリプト全文も含め段階11と一致した。
この一覧には今回の負の添字を直接検証するケースがなかったため、14件を別の回帰テストとして追加した。
既存の孤立コルーチンGCテストも成功している。

デバッグ有効時には、非空の可変長引数呼び出しごとにラッパーとdealiasの確保が加わり、
setlocalの書き込みごとにコピーが発生する。DebugLibをロードしない通常経路ではこの保持領域を作らない。
今回の目的は正当性であり、速度・確保量の改善率は測定していない。

## 13: 存在しないスタックレベルをLuaErrorにする

[13-debug-stack-level.patch](changes/13-debug-stack-level.patch)はDebugLibと
DebugStackLevelRegressionTestの10件を含む。段階12の後へ適用する。

getlocal/setlocalで指定レベルのCallFrameが見つからない場合は、従来の返却なしから
`level out of range`のLuaErrorへ変更した。
エラーの引数番号はthreadなしで1、threadありで2となる。
レベルと添字の数値変換、setlocalの値存在確認は先に行い、それらの既存検証順序は維持する。

レベル1以降は既存LuaJのフレーム番号を維持する（指定threadの最上段も1）。
LuaJが登録しないdebug関数自身に対応するレベル0は、Javaフレームと同じくnilを1値返す扱いにした。
C版のtemporaryスロットの提供や、指定threadのフレーム番号体系全体の変更は行っていない。
有効なフレーム上での存在しないローカル添字は、エラーではなく従来どおりnilを1値返す。
関数形式のgetlocalはこのスタックレベル検証を通らず、未実行・終了済みthreadでも引数名を取得できる。

テストは負値・int最小/最大・空スタック、thread付き引数番号、終了済みコルーチン、レベル0、
最後の有効フレームとその次、yield中のコルーチン、関数形式、無効なローカルとの区別、
xpcallによる捕捉とハンドラ・フレームの後処理を確認する。

固定649件で変化したのはErrorsTest.testDebugLibArgsの2行のみ。
`debug.getlocal(thread,100,1)`と`debug.setlocal(10,1,'foo')`が、既存のlevel out of range期待に一致するようになった。
同ケースには別の既知差分が残るため、全体の失敗数は25件を維持する。
その他のケースと全文、例外型は一致し、新規退行はない。

## 再現手順

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -Dtest=DebugVarargsRegressionTest,DebugStackLevelRegressionTest test
mvn -DskipTests package
bash tools/run-test-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/current --reviewed-changes documentation/debug-vararg-fixes.json --stage 13-debug-stack-level
python3 tools/run-regression-cases.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/debug-vararg-regressions/current --classes DebugVarargsRegressionTest DebugStackLevelRegressionTest --expect-pass
```

従来分を含む133件のクラス一覧はREADMEのMavenコマンドを参照。
Mavenキャッシュを別の場所へ指定する場合は-Dmaven.repo.localとスクリプトのMAVEN_REPOをそろえる。
段階12のjarには--stage 12-debug-varargsを指定する。
監査中にtarget/test-classesを再コンパイルしないこと。段階別のビルドを済ませてから監査する。

確認済み差分の候補は次のコマンドで別名に再生成できる。

```sh
python3 tools/review-debug-vararg-stages.py build/audit build/candidate-debug-vararg-fixes.json
```

前段11の全結果、固定一覧、段階12で全文変化がないこと、段階13の変更ケースと2行だけの全文変換、
例外型、追加回帰テストの前後結果を検証する。
ゲートは固定・追加テストソースのハッシュも確認する。失敗ケース全体を一括で許可してはいない。

jar・JUnitログはbuild/correctness-stages/12-*・13-*、全文はbuild/audit/12-debug-varargs/・13-debug-stack-level/に保存した。
2パッチの順次適用で対象ソース2ファイルと新規テスト2ファイルをバイト単位で再現できることも確認した。

| jar | SHA-256 |
| --- | --- |
| 12 | 9d426cf252f0960e90de0cfa4dcb8d905d54b65301ca1edc26d39dcda3f15bc6 |
| 13 / targetのjar | 2a3cb60f918f7bc8a4198364db27330c36ee61d15d07f3e6153affafed3e8ab4 |

後続のJMH基準固定・単値呼び出し最適化は [単値呼び出しの性能検証](SINGLE-CALL-PERFORMANCE.md) を参照。
