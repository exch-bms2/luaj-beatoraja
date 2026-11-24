#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -lt 2 ]; then
  echo "Usage: bash tools/run-benchmarks.sh VM_JAR OUTPUT_DIRECTORY [JMH options...]" >&2
  exit 2
fi
vm_jar=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
output=$2
shift 2
mkdir -p "$output"
output=$(cd "$output" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
java_bin="${JAVA_HOME:?Set JAVA_HOME to JDK 17}/bin/java"
"$java_bin" -version > "$output/jvm.log" 2>&1
shasum -a 256 "$vm_jar" > "$output/vm.sha256"
shasum -a 256 "$root/benchmarks/target/benchmarks.jar" > "$output/harness.sha256"
git -C "$root" rev-parse HEAD > "$output/commit.log"
git -C "$root" diff > "$output/working-tree.patch"
git -C "$root" ls-files --others --exclude-standard > "$output/untracked-files.log"
# Runtime classes come only from the selected VM jar; JMH forks inherit it.
"$java_bin" -cp "$vm_jar:$root/benchmarks/target/benchmarks.jar" \
  org.openjdk.jmh.Main -foe true -prof gc -rf json -rff "$output/results.json" "$@" \
  | tee "$output/run.log"
