# 単値呼び出しの性能基準と最適化

2026-11-24。互換性修正段階13の最新版jarを性能の基準00として固定し、4候補を比較した。
最終成果物は04-array-overflow。同期区間の短縮だけの候補01は採用していない。
元の固定649件、期待値、audit-matrix.json、確認済みの互換性差分JSONは保持している。

## 採用判断に使った順序交互の追試

基準版A・最終版BをAB・BA・ABの順で実行した。各項目について各版3つの独立JVMを使用し、
各JVMは5回×1秒のウォームアップと5回×1秒の測定を行う。代表値は各fork平均3本の中央値。
順序をそろえて一度ずつ測る比較にも揺れが見えたため、この追試を追加した。

| 項目 | 基準 ns/op | 最終 ns/op | 中央値の変化 | 確保量 B/op（基準→最終） |
| --- | ---: | ---: | ---: | ---: |
| 0引数・単値 | 11.73 | 8.96 | -23.6% | ≈0 → ≈0 |
| 1引数・単値 | 13.22 | 10.85 | -17.9% | ≈0 → ≈0 |
| 通常再帰（深さ8） | 205.75 | 208.56 | +1.4% | ≈0 → ≈0 |
| 末尾再帰 | 437.41 | 401.68 | -8.2% | 1120.00 → 1120.00 |

0引数は3組とも短縮（−25.6%、−22.2%、−24.2%）、1引数も3組とも短縮（−18.8%、−16.0%、−17.8%）。
通常再帰の各組の差は+3.3%、+0.7%、−0.3%だった。通常再帰全体の高速化や、微小な悪化の不存在を断定する結果ではない。
最初の1本キャッシュ候補で見えた約8%の通常再帰の遅れは最終版では小さくなり、標準測定の信頼区間も基準版と重なる。
確保量の≈0は測定上の背景ノイズ程度を意味し、微小な小数の差を確保削減とは扱わない。

追試の全24 JVMの測定値・3組それぞれの比率は[single-call-interleaved.json](single-call-interleaved.json)に保存した。
この結果は当該環境のマイクロベンチマークであり、実スキンのフレーム時間・確保量はまだ測定していない。

## 段階別の標準JMH比較

macOS 26.5.1 arm64、Liberica OpenJDK 17.0.19+11-LTS、JMH 1.37、1 thread、3 forks、
各forkでwarmup 5回×1秒・measurement 5回×1秒、-Xms512m -Xmx512m、-prof gc。
全段階で同じ8項目・同じハーネスjarを使用した。VMクラスをハーネスjarへ含めていないことも確認した。
通常再帰の単値返却1項目を今回ハーネスに追加した。

以下はJMH標準測定の平均値で、上の順序交互追試の中央値とは別の集計である。

| 項目 | 00 基準 ns/op | 01 同期区間短縮 | 02 1本キャッシュ | 03 条件調整 | 04 配列スタック | 確保量 B/op（00→04） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0引数・単値 | 12.53 | 11.60 | 9.09 | 11.50 | 8.88 | ≈0 → ≈0 |
| 1引数・単値 | 13.56 | 13.12 | 11.02 | 10.98 | 10.90 | ≈0 → ≈0 |
| 4引数・単値 | 22.06 | 24.09 | 20.31 | 19.88 | 19.95 | ≈0 → ≈0 |
| 通常再帰（深さ8） | 204.38 | 207.45 | 220.54 | 217.96 | 207.01 | ≈0 → ≈0 |
| 末尾再帰 | 438.62 | 441.95 | 404.76 | 545.93 | 408.46 | 1120.00 → 1120.00 |
| 1引数・4値返却 | 29.40 | 32.25 | 28.84 | 29.87 | 30.18 | 88.00 → 88.00 |
| Java→Lua文字列 | 39.90 | 40.33 | 40.60 | 39.83 | 40.01 | 88.00 → 88.00 |
| Lua→Java文字列 | 47.22 | 47.26 | 39.26 | 41.39 | 38.35 | 152.00 → 152.00 |

各段階の全結果、JMHの99.9%信頼区間、forkごとの実測値、実行条件、VM・ハーネス・ソースのハッシュは
[single-call-performance.json](single-call-performance.json)に保存した。
文字列変換など変更していない経路にも時間の変動があるため、その差を今回のプール変更による高速化とは主張しない。

## 変更の分離と最終構造

- 01：[14-split-stack-lock-trial.patch](changes/14-split-stack-lock-trial.patch)。配列初期化・消去を同期区間の外へ出すだけの試行。
  単値の改善が小さく、4引数単値等に遅い結果も出たため、この候補を独立した最適化としては採用しない。
- 02：[15-single-call-primary-slot.patch](changes/15-single-call-primary-slot.patch)。基準00へ直接適用する、通常呼び出し向けの1本キャッシュ。
  0・1引数は短縮したが通常再帰が約8%遅くなったため、中間段階として保存した。
- 03：[17-overflow-cache-tuning.patch](changes/17-overflow-cache-tuning.patch)。02へ適用する条件判定・予備プールの取り出しの調整。
  単独の十分な改善は確認できず、単独版の採用は見送った。
- 04：[18-overflow-array-stack.patch](changes/18-overflow-array-stack.patch)。03へ適用する、予備プールのArrayDequeから固定長配列スタックへの変更。
  この組み合わせを最終版として評価・採用した。

適用順は00→15→17→18。14は別の試行で、15の前に適用しない。
共通の追加回帰テスト4件は[16-single-call-pool-regressions.patch](changes/16-single-call-pool-regressions.patch)で分離した。
各パッチで対象ソースをバイト単位で再現できることを確認した。

通常呼び出しは待機中の配列1本を原子的に取り出す。
配列は使用中に公開せず、upvalueのクローズ・返却値の独立化・debugフレーム終了の既存順序を維持し、
参照をnullで消去した後で返却する。再利用時にはNILで初期化する。
公開にはrelease書き込み、取得には原子的な取得を使用し、スレッド間の受け渡しを維持する。
APIの性質は[JDK 17のAtomicReferenceFieldUpdater](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReferenceFieldUpdater.html)を参照。

再帰・再入で1本目が使用中の場合は、同期付きの配列スタックを使う。
配列取得時は予備プール内の参照も消し、使用中の配列を重複して貸し出さない。
本数上限20本と、実行スタック配列の保持スロット上限1024をクロージャごとに維持する。
1本用の予約枠を含めて計算するため、Prototypeのサイズ変更後も上限を超えない。
予約枠に余りが出る場合があり、上限まで必ず保持する保証ではない。管理用配列等を含む総ヒープ量の上限でもない。

同時返却の競合では、待機中の配列を上書きしてキャッシュから落とす場合がある。
使用中の配列を共有することはなく、失った配列はGC対象になる。
並行返却時の確保量・スループットを改善したとは主張していない。
通常呼び出しのwarm状態での確保量を維持した結果であり、未使用クロージャや初回呼び出しのメモリ・時間は別途評価が必要。

## 正当性の比較

00・01・02・03・04の全段階で固定649件は624件成功・25件失敗。
例外型・診断内容・スクリプト全文まで既存の段階13と一致し、未登録差分は0だった。
既存133件と追加4件、計137件の回帰テストも全段階で成功した。
既知の25件を成功に見せる期待値変更は行っていない。

追加テストは20スレッドで同じクロージャを40回ずつ呼び、使用中のスタックが共有されないこと、
Prototypeのサイズ変更後の保持上限・参照消去、全callオーバーロードの不足引数のnil、
多値返却の保持・例外後の再利用を確認する。
並行テストはGlobalsを共有しない環境でプールだけの受け渡しを検証しており、Lua環境全体の並列実行を保証するものではない。
既存テストの再帰・再入・upvalue・例外・yield/resume・孤立コルーチンのGC等も引き続き成功した。

監査は完了後も待機中のコルーチンでJVMが残ることが判明したため、元のTestAuditRunnerを変更せず、
完了後に終了するPerformanceAuditRunnerとrun-performance-audit.shを追加した。
このリポジトリの649件と追加プローブの出力完了を確認した監査JVM 30個を終了した。
それ以前の予備測定は正式比較から除外し、基準を取り直した。
新しいラッパーでも固定結果と追加プローブが一致することを確認した。

## 保存と再現

基準と各候補はbuild/performance-stages/の段階別ディレクトリへ、vm.jar・LuaClosure.java・
完全なソース/テストのcomplete-sources.tar.gz・ファイルごとのsource-manifest.json・JMH生データ・JUnitログを保存した。
基準00と最終04は、アーカイブを別の一時ディレクトリへ展開してオフラインで再ビルドし、jarのSHA-256が完全一致した。
未追跡ソースもアーカイブに含む。実行時のworking-tree.patchは作業中の別候補を含み得るため、
測定VMとの対応は段階別のソースアーカイブ・manifest・VMハッシュを使用する。

| jar | SHA-256 |
| --- | --- |
| 00-baseline | 2a3cb60f918f7bc8a4198364db27330c36ee61d15d07f3e6153affafed3e8ab4 |
| 01-split-lock | c3e58ac1f4e4044f61f35a2057affbec398f451f5c8c273f3c0ad1b8d2d2ddd0 |
| 02-primary-slot | ba14bf77665f918e0597430f5fc319291577457f9d11e4e4b95f08c424b238d5 |
| 03-overflow-tuning | a8547da5a22775a9d4a225152914023894a9ddb8c664d9ecc7eb8de70b7aff06 |
| 04-array-overflow | 6e5a8076343ab7a29f596bd142c3458227134b549a56336453e31e6258dd3914 |

最終成果物はtarget/luaj-beatoraja-0.1.0-SNAPSHOT.jarで、04のjarと同一である。
以下はJDK 17・Mavenでの例。別のキャッシュを使う場合はMavenの-Dmaven.repo.localとMAVEN_REPOをそろえる。

```sh
export JAVA_HOME=/path/to/jdk-17
mvn -DskipTests package
python3 tools/run-focused-regressions.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/current-regressions.log
bash tools/run-performance-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/performance-current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/performance-current --reviewed-changes documentation/debug-vararg-fixes.json --stage 13-debug-stack-level
mvn -f benchmarks/pom.xml -Dvm.jar="$PWD/target/luaj-beatoraja-0.1.0-SNAPSHOT.jar" package
bash tools/run-benchmarks.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/jmh/current
```

JMHは測定用JVM間のローカルソケットを必要とする。ビルド・監査・他の測定と同時には実行しない。
基準版にはbuild/performance-stages/00-baseline/vm.jarを指定し、同じハーネス・JVM条件を使う。
ABBAAB追試は4項目のフィルタと-f 1を各実行へ渡し、各版3 JVM分を集計する。

```sh
python3 tools/review-interleaved-call-benchmarks.py build/performance-stages/interleaved build/performance-stages/04-array-overflow/vm.jar build/candidate-interleaved.json
python3 tools/review-single-call-performance.py build/candidate-single-call-performance.json --accepted 04-array-overflow --interleaved documentation/single-call-interleaved.json --reproduction build/performance-stages/reproduction.json
```

次の性能変更もこの基準と比較し、通常再帰の小さな増加を含め、実スキンでCPU・確保量・フレーム時間を確認する。

後続の多値返却最適化と最新の性能比較は [多値返却の性能検証](MULTI-RETURN-PERFORMANCE.md) を参照。
