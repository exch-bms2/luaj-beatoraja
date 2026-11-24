# 弱テーブル・fmod・modfの個別修正

本書は前段の3変更の記録。後続のmin/max・有限数値表示の結果と現在の比較ゲートは [数値の正当性修正](NUMERIC-FIXES.md) を参照。

2026-11-24。歴史的な [649件の比較基準](audit-matrix.json) と [一覧](audit-test-cases.list) は変更しない。
新規テスト23件を別に実行し、各変更でjarを固定して649件を取り直した。
修正前jarに最終的な23件をテストごとのJVMで実行すると、13件成功・10件失敗だった。
修正後は同じ23件がすべて成功する。
初期確認ではGC後のrehashを含む2件が応答しなかったため、各5秒で停止する検証へ切り替え、
さらに列挙前にキー取得をassertするようテストを改善した。最終テストではタイムアウトもなく、キーの欠落を直接検出できる。
固定649件や修正済みjarの検証は最後まで実行できている。

## 結果

| 段階 | 固定649件の成功 | 失敗 | 直前から成功へ変化 | 新規回帰テスト | 新規退行 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 変更前fork | 598 | 51 | — | — | — |
| 01 弱テーブル | 619 | 30 | 21 | 12件成功 | 0 |
| 02 fmod | 620 | 29 | 1 | 累計17件成功 | 0 |
| 03 modf | 620 | 29 | 0 | 累計23件成功 | 0 |

成功に変わった21件は、整数キーの20件と、配列容量のassertで途中終了していたWeakValueTableTest 1件。
そのテストの後続のGC・userdata・文字列の検証も成功する。
fmodではMathLibTest.testFmodが成功へ変わった。

JME/JSE/LuaJCのtestMathLibはmin/maxのnumeric string対応の問題が残るため、最後まで成功にはならない。
失敗数だけでは改善を測れないため、各段階で数学ライブラリの全文出力も比較した。
fmodによる差は各構成3行、modfによる差は各構成1行だけ。
既知の失敗の内容が変わることを検出したうえで、以下の置換以外がないことを機械的に検証している。

```text
math.fmod(2,0)       false / by zero  → true <nan>
math.fmod(-2,0)      false / by zero  → true <nan>
math.fmod('2','0')   false / by zero  → true <nan>
math.modf('0')      true 0 <zero>     → true <zero> <zero>
```

modfの`0`から`<zero>`への変化は、fixtureが数値0をタグへ変換する一方、旧実装のstring "0"は変換しないため。
新規テストでは表示だけでなく、両方の返却値が `LuaValue.TNUMBER` であることを直接確認する。
上記以外のケース・診断・全文出力に新しい変化はなかった。

## 01: 弱テーブルの整数キー

独立差分: [01-weak-integer-keys.patch](changes/01-weak-integer-keys.patch)。
対象はLuaTableとWeakTable、回帰テストはWeakIntegerKeyTest 12件。

- 新しい正整数キーもrehashの配列サイズ計算に含め、確保された配列へ格納する。
- WeakValueSlotの生存する整数キーも、hashからarrayへ移せるようにする。弱いキーのslotは対象にしない。
- 移動する値はmetatableのwrapを通す。arrayへの移動でテーブル・関数・userdataを強参照にしない。
- GC済みslotをhash先計算の前に除外する。live entryを確保して移動する。

テストはv/kvの順挿入・逆挿入、両rawget、長さ・列挙、強く保持中の値、hash→arrayとarray→hashのGC、
GC後のrehash、非整数の弱いキー・値、kモードでの値保持を確認する。
テーブル・関数・userdataが実際に回収されることと、文字列・数値が回収されないことの両方を検証する。
userdataはJavaの元オブジェクトを保持している間にLuaラッパーが回収されても、取得し直せることを確認した。
GCは上限付きで待ち、保持が必要な箇所ではreachabilityFenceを使用する。

前回のweak-routing-experiment.patchは原因確認用の不完全な実験として残す。本修正はその実験とは異なり、
弱いhash slotの移動とwrap、GC済みslotの処理まで含む。

## 02: fmod

独立差分: [02-fmod.patch](changes/02-fmod.patch)。回帰テストはFmodRegressionTest 5件。

整数の高速経路は、実際のLua整数2個・非ゼロ除数だけに限定する。
整数0、numeric string、その他の数値はcheckdoubleと浮動小数点の剰余を使用する。
ゼロ除数はArithmeticExceptionではなく、numberのNaNを返す。

合わせて、`islong()`がdoubleの2^63をlong上限へ飽和変換した後も真になる経路を回避した。
旧実装はfmod(2^63,3)が1だったが、修正後は2になる。
通常の整数高速経路は残し、大きなdoubleをlongへ丸めて計算しない。
返却数・型、負数と小数の剰余、数値文字列、整数境界、NaN・無限大、不正引数も検証した。

## 03: modf

独立差分: [03-modf.patch](changes/03-modf.patch)。回帰テストはModfRegressionTest 6件。

整数の高速経路へ入る前にchecknumberで数値へ変換する。
数値文字列をそのまま第1返却値に使わず、整数部・小数部の両方をnumberとして返す。
既存のLua数値の高速経路は維持する。
正負の小数、整数の数値文字列、大きな整数double、NaN・無限大、不正引数、
再呼び出し後に保持した返却値と、Luaのtype()でも確認した。

## 比較データとゲート

[correctness-fixes.json](correctness-fixes.json) に各段階のjar・パッチ・新規テストのハッシュと、
649件のうち変化したケースだけのbefore/after、数学ライブラリの全文差分を保存した。
原基準のaudit-matrix.jsonを無条件に上書きしていない。
従来ゲートは現在のjarに対して3件の全文変化を引き続き報告する。
確認済みの差分を明示した場合だけ、段階別の結果と比較できる。

```sh
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/01-weak --reviewed-changes documentation/correctness-fixes.json --stage 01-weak
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/02-fmod --reviewed-changes documentation/correctness-fixes.json --stage 02-fmod
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/03-modf --reviewed-changes documentation/correctness-fixes.json --stage 03-modf
```

参照JSONのハッシュ、649件の一覧、修正前レコードとの一致を検査してから差分を適用する。
新規テストのソース変更も検出する。対象外の出力・例外・ケースの変化は従来どおり失敗する。

## 再実行

JDK 17でMavenビルドを行う。今回の環境では既に取得した依存関係を使用した。

```sh
mvn -Dtest=WeakIntegerKeyTest,FmodRegressionTest,ModfRegressionTest test
mvn -DskipTests package
bash tools/run-test-audit.sh target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/audit/current
python3 tools/check-audit-regressions.py documentation/audit-matrix.json build/audit/current --reviewed-changes documentation/correctness-fixes.json --stage 03-modf
```

新規23件を1テスト1 JVM・128MiBヒープ・上限5秒で実行する場合は以下を使う。
修正前に実行する場合は--expect-passを外し、失敗とタイムアウトも結果JSONに記録する。

```sh
python3 tools/run-regression-cases.py target/luaj-beatoraja-0.1.0-SNAPSHOT.jar build/regression-cases/current --expect-pass
```

段階別に取り直す場合は、変更前ソースへ3パッチを順番に適用して各jarを保存し、
01-weak / 02-fmod / 03-modfの監査ディレクトリへ実行する。
新規テストは01で12件、02で17件、03で23件を同じVM jarで実行する。
今回保存したjarと新規テストのJUnitログは `build/correctness-stages/`、649件の全文出力は `build/audit/<段階>/` にある。
3パッチを基点ソースへ順に適用し、現在の対象6ファイルをバイト単位で再現できることも確認した。

残る29件はこの修正では隠さない。min/max、load/xpcall、有限数値の文字列化、debug、環境・期待値の問題などは
[元の原因分類](failure-causes.json) を参照する。分類ファイルは修正前の歴史的な51件を記録したもの。
今回の変更の性能・実スキンへの効果は測定していない。
