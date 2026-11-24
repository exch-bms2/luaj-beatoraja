# 多値返却の性能最適化

2026-11-24。直前の単値呼び出し最適化済みjar（6e5a8076…）を基準00として固定した。
変更は3つに分離し、各段階で同じJMHハーネス・固定649件・既存137件と追加12件の回帰テストを使用した。
既存の比較基準・期待値・先行する性能JSONを上書きしていない。

## 結果

固定4値返却は27.89→21.97 ns/op（約21.2%短縮）、88→48 B/op（約45.5%削減）となった。
この時間差ではJMHの99.9%信頼区間も重ならない。
先頭値付きの返却は176→104 B/op（約40.9%削減）。平均時間は短くなったが、信頼区間が重なるため速度改善は未確定とする。

JMH 1.37 / Liberica OpenJDK 17.0.19+11-LTS、1 thread、3 forks、各forkでwarmup 5回×1秒・measurement 5回×1秒、
-Xms512m -Xmx512m、-prof gc。全段階を順番に測定し、測定中にビルド・監査を実行していない。
新設したMultiReturnBenchmark 4項目と、既存ShortCallBenchmark 4項目を同じハーネスで測定した。
入力は小整数キャッシュ内の値を使い、数値の大量確保と返却処理のコストを分けて比較している。
CPU環境は前段と同じmacOS arm64。以下は当該環境のマイクロベンチマークの平均値であり、実スキンの改善率ではない。

| 項目 | 00 基準 ns/op | 01 所有済み表現 | 02 固定返却直接生成 | 03 先頭値の結合 |
| --- | ---: | ---: | ---: | ---: |
| 固定4値返却 | 27.89 | 28.30 | 22.26 | 21.97 |
| 先頭値＋内側関数の4値 | 67.71 | 55.04 | 69.42 | 59.03 |
| 借用入力の4値を返却 | 16.49 | 16.02 | 16.01 | 15.89 |
| 4値を返す関数からcallで単値取得 | 19.45 | 19.00 | 19.18 | 19.55 |
| 固定2値返却 | 18.57 | 17.77 | 18.55 | 18.23 |
| 0引数・単値 | 8.85 | 8.87 | 9.21 | 9.03 |
| 1引数・単値 | 10.97 | 10.73 | 11.03 | 11.13 |
| 4引数・単値 | 20.02 | 19.97 | 19.87 | 19.95 |

| 項目 | 00 基準 B/op | 01 | 02 | 03 |
| --- | ---: | ---: | ---: | ---: |
| 固定4値返却 | 88 | 80 | 48 | 48 |
| 先頭値＋内側関数の4値 | 176 | 160 | 128 | 104 |
| 借用入力の4値を返却 | 56 | 48 | 48 | 48 |
| 4値を返す関数からcallで単値取得 | 32 | 32 | 32 | 32 |
| 固定2値返却 | 48 | 48 | 48 | 48 |
| 0引数・単値 | ≈0 | ≈0 | ≈0 | ≈0 |
| 1引数・単値 | ≈0 | ≈0 | ≈0 | ≈0 |
| 4引数・単値 | ≈0 | ≈0 | ≈0 | ≈0 |

単値経路の約1〜2%の差や、その他の小さな時間差は、信頼区間が重なるものを改善・悪化と断定していない。
特に先頭値付き返却はfork間のばらつきが大きい。段階02だけを時間の改善として採用したとは扱わず、
段階03までの組み合わせで確保量削減と固定4値の時間短縮を確認した。
2値返却は従来表現を維持した。

通常再帰・末尾再帰は、同じハーネスで基準と最終版を追加比較した。

| 項目 | ns/op（基準→最終） | B/op（基準→最終） |
| --- | ---: | ---: |
| 通常再帰（深さ8） | 209.85 → 210.61 | ≈0 → ≈0 |
| 末尾再帰 | 418.41 → 409.21 | 1120 → 1040 |

通常再帰は約+0.4%で信頼区間も重なり、明確な悪化は確認できない。
末尾再帰の時間差も信頼区間が重なるため高速化は断定しないが、引数独立化の表現変更による確保量削減は確認できた。
JMHの生データ、99.9%信頼区間、forkごとの値、各変更の直前・基準からの比較は
[multi-return-performance.json](multi-return-performance.json)に保存した。

## 19: 独立化済みの内部表現を用意する

[19-owned-varargs-snapshots.patch](changes/19-owned-varargs-snapshots.patch)。対象はVarargs。

3値以上のdealias結果を、非公開のOwnedArrayVarargsで保持する。
値を格納する配列は新規に作り、通常のVarargs APIから変更・取得できないようにする。
この表現のdealiasは自分自身を返せるため、再独立化のコピーを避けられる。
値数は配列長で保持し、末尾のnilも数える。不要になったtailフィールドも持たない。

publicなvarargsOfで受け取る配列や未知のVarargsを、そのまま所有済みとは判定しない。
独立化のコピー先を、オーバーライド可能なcopytoへ渡すことも避けた。
既知の配列表現は直接arraycopyし、未知の実装はargから値を取得する。
独自copytoがコピー先を保持する実装に対しても、内部の所有権判定を破らないようにした。

subargsの切り出しは保守的に従来表現へ戻し、dealias時には必要な範囲だけコピーする。
大きな元配列の不要な先頭部分まで、返却結果が保持し続ける最適化は行っていない。
独立させるのは値の並びであり、LuaTable等のLuaValue自体は従来と同じ同一性を維持する。

## 20: invokeの固定多値返却を直接生成する

[20-fixed-return-snapshot.patch](changes/20-fixed-return-snapshot.patch)。対象はLuaClosureとVarargs。

標準LuaClosureのinvokeで3値以上を返す場合、OP_RETURNから必要な範囲を独立した配列へ直接コピーする。
従来の「スタック参照用のArrayPartVarargsを返し、後でdealiasする」中間オブジェクトを省く。
所有済み表現なので、その後のonInvokeのdealiasで再コピーしない。

単値を受け取るcall経路では、この早期コピーをしない。
返却する値をすべて計算した後で先頭だけ取得する既存動作と、確保量32 B/opを維持する。

protected execute(LuaValue[], Varargs)のシグネチャを維持し、実装は同じVM本体を共有する。
サブクラスでは従来のexecuteを通し、サブクラスのfinallyが返却レジスタへ加えた変更も従来どおり反映する。
debugライブラリ有効時も早期コピーをせず、返却処理の観測・変更が終わってから独立化する。
内部の返却モードは各呼び出しの引数として保持し、クロージャ共有フィールドやThreadLocalに置いていない。

## 21: 先頭値と所有済みの多値結果を一度で結合する

[21-owned-prefix-return.patch](changes/21-owned-prefix-return.patch)。対象は同じ2ファイル。

return prefix, inner()のような返却で、内側の結果が所有済み配列なら、先頭のレジスタ値と内側の値を
最終配列へ直接コピーする。PairVarargs等の中間表現を作ってから平坦化する処理を省く。
先頭値がない場合は従来と同じtailを返し、借用入力はonInvokeで必要なコピーを行う。
未知の結果、debug有効時、executeを拡張したサブクラスは従来経路を維持する。

最終結果は必要な個数だけの平坦な配列であり、元のVMスタックや内側の結果コンテナは保持しない。
状態を持つ関数の実行結果をキャッシュしたり、APIが返すテーブルを勝手に共有したりはしない。

## 正当性と再現性

全4段階で固定649件は624件成功・25件既知失敗。
例外型、診断内容、スクリプト全文まで段階13の確認済み結果と一致し、未登録差分は0だった。
既存137件と追加12件、計149件の回帰テストも全段階で成功した。

追加テストは[22-multi-return-regressions.patch](changes/22-multi-return-regressions.patch)に分離した。
返却値保持後の再呼び出し、先頭値付きの返却、Javaの借用配列、独自Varargs・copyto、
subargsの境界・nil・copytoのパディング、executeサブクラスのfinally・借用結果、
Javaのdebug返却処理、callでの単値取得、状態とテーブル同一性、pcall、yield/resume、例外・末尾呼び出しを確認する。
既存の多値返却の上書き、4引数末尾再帰、再入、upvalue、弱参照・孤立コルーチンGC等も引き続き成功した。

public/protected APIの表示も基準版・最終版で一致することを確認した。
各変更を順に適用して対象ソースをバイト単位で再現し、全4段階の完全なソースアーカイブから
オフラインで再ビルドしたjarのSHA-256が測定対象と完全一致した。

| jar | SHA-256 |
| --- | --- |
| 00-baseline | 6e5a8076343ab7a29f596bd142c3458227134b549a56336453e31e6258dd3914 |
| 01-owned-snapshots | cffc892e4de134444564382320e3389ea546d12ac0f3d3841896ab05c6af2670 |
| 02-fixed-results | 13e042f80fb78721d7697fee58c29dca3f4834e941cd783d53e2e57eb721df04 |
| 03-owned-prefix | a7356e4f1da6ff203e4978aa939d395273048837c454126a1b827e3da773e8bd |

段階別jar・ソース・source-manifest.json・完全なソース/テストのcomplete-sources.tar.gz・JUnitログ・JMH生データは
build/multi-return-stages/以下に保存した。測定対象はimmutableなvm.jarで選択し、作業中の別候補のソースを使って実行していない。
最終成果物target/luaj-beatoraja-0.1.0-SNAPSHOT.jarは段階03のjarと同一である。

## 再実行

JDK 17を指定する。別のMavenキャッシュを使うときは-Dmaven.repo.localとMAVEN_REPOをそろえる。

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -DskipTests package
python3 tools/run-multi-return-regressions.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/multi-current-regressions.log
bash tools/run-performance-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/multi-current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/multi-current --reviewed-changes documentation/debug-vararg-fixes.json --stage 13-debug-stack-level
mvn -f benchmarks/pom.xml -Dvm.jar="$PWD/target/luaj-beatoraja-0.1.0-SNAPSHOT.jar" package
bash tools/run-benchmarks.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/jmh/multi-current '.*ShortCallBenchmark.(zeroArguments|oneArgument|fourArguments|multipleResults)|.*MultiReturnBenchmark.*'
```

同じハーネスで基準版のvm.jarを指定して比較する。JMHとビルド・監査を同時に実行しない。
今回の保存済みデータと再ビルド証拠を再検証する例:

```sh
python3 tools/review-multi-return-performance.py build/candidate-multi-return-performance.json --reproduction build/multi-return-stages/reproduction.json
```

実スキンのCPU・確保量・フレーム時間、長時間実行後の保持メモリは未測定。
マイクロベンチマークの高速化率を、そのままゲーム全体の高速化率とは扱わない。
