#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
baseline=daf3da94e3cdba0ac6a289148d7e38bd53d3fe64
staging=$(mktemp -d "${TMPDIR:-/tmp}/luaj-baseline.XXXXXX")
git archive "$baseline" | tar -x -C "$staging"
cp pom.xml "$staging/pom.xml"
cp test/junit/org/luaj/vm2/StackLifetimeTest.java "$staging/test/junit/org/luaj/vm2/"
variant=upstream
if [ "${RECONSTRUCT_LEGACY:-0}" = 1 ]; then
  # Audit-only reconstruction from bytecode. It deliberately reproduces bugs.
  patch -d "$staging" -p1 < "$root/documentation/legacy-reconstruction.patch"
  variant=legacy-reconstructed
fi
# The historical source uses identifiers reserved by newer Java releases.
# Compile it unchanged to Java 8 bytecode using the same JDK 17 toolchain.
"${MVN:-mvn}" -f "$staging/pom.xml" -Dmaven.compiler.release=8 -DskipTests package "$@"
mkdir -p "$root/build/baseline"
cp "$staging/target/luaj-beatoraja-0.1.0-SNAPSHOT.jar" "$root/build/baseline/$variant.jar"
echo "Baseline: $root/build/baseline/$variant.jar"
echo "Source staging (kept for audit/tests): $staging"
