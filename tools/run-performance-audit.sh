#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: bash tools/run-test-audit.sh VM_JAR OUTPUT_DIRECTORY" >&2
  exit 2
fi
vm_jar=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
mkdir -p "$2"
output=$(cd "$2" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
repository="${MAVEN_REPO:-$HOME/.m2/repository}"
java_home="${JAVA_HOME:?Set JAVA_HOME to JDK 17}"
inventory="${AUDIT_INVENTORY:-$root/documentation/audit-test-cases.list}"
dependencies="$repository/junit/junit/4.13.2/junit-4.13.2.jar:$repository/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar:$repository/org/apache/bcel/bcel/5.2/bcel-5.2.jar:$repository/org/microemu/cldcapi11/2.0.4/cldcapi11-2.0.4.jar"
runner="$output/runner"
mkdir -p "$runner"
"$java_home/bin/javac" --release 17 -cp "$vm_jar:$dependencies" -d "$runner" "$root/tools/TestAuditRunner.java" "$root/tools/CompatibilityProbes.java" "$root/tools/PerformanceAuditRunner.java"
shasum -a 256 "$vm_jar" > "$output/vm.sha256"
shasum -a 256 "$inventory" > "$output/inventory.sha256"
# Lua IO tests use fixed names such as seektest.txt and abc.txt.
# A fresh cwd prevents cross-run interference and contamination by old files.
work=$(mktemp -d "$output/work.XXXXXX")
mkdir -p "$work/test"
cp -R "$root/test/lua" "$work/test/lua"
cd "$work"
"$java_home/bin/java" -Xmx512m -Dfile.encoding=UTF-8 "-Duser.timezone=${AUDIT_TIMEZONE:-Asia/Tokyo}" -Duser.language=en -Duser.country=US \
  -cp "$vm_jar:$root/target/test-classes:$runner:$root/target/test-classes/org/luaj/vm2/compiler:$root/test/lua:$dependencies" \
  PerformanceAuditRunner "$inventory" "$output"
