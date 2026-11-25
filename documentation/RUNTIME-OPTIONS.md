# 実行環境（JDK・JITフラグ）の比較

2026-11-25。Luaのコードを変えずに速くできるかを確かめた。
対象はmasterのjar（`ffa1978…`）、macOS arm64。JMH 3 forks、warmup 5×1秒、measurement 5×1秒、512MiB。
各構成を2回ずつ交互に測った。数値は6 forks分の中央値の、JDK 17（既定）との比。

| 項目 | JDK 21.0.4 | JDK 17 + `-XX:FreqInlineSize=500 -XX:InlineSmallCode=4000` | JDK 17 + `-XX:MaxNodeLimit=240000 -XX:NodeLimitFudgeFactor=8000` |
| --- | ---: | ---: | ---: |
| skinDrawCondition | +39.5% | +24.6% | −0.4% |
| luaFunctionTailCall | +16.1% | +5.0% | +5.1% |
| tableNumberReads | +6.2% | +9.3% | +9.7% |
| crossChunkFieldLookup | +12.0% | −2.3% | −0.5% |
| recursiveSingleResult | +5.3% | −4.1% | −4.4% |
| zeroArguments | +2.9% | −1.2% | −2.9% |

結論：どの構成も、スキンでよく使う経路（draw条件、末尾呼び出し、数値の読み取り）が遅くなる。JDK 17の既定設定のままがよい。
生データは `build/runtime/jmh/`（JDK）と `build/runtime/jmh-flags/`（フラグ）にある。
