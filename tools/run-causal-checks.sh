#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: bash tools/run-causal-checks.sh VM_JAR OUTPUT_DIRECTORY" >&2
  exit 2
fi
vm_jar=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
mkdir -p "$2"
output=$(cd "$2" && pwd)
root=$(cd "$(dirname "$0")/.." && pwd)
java_home="${JAVA_HOME:?Set JAVA_HOME to JDK 17}"
repository="${MAVEN_REPO:-$HOME/.m2/repository}"
python3 - "$root" "$output" <<'PY'
import pathlib,sys
root,out=map(pathlib.Path,sys.argv[1:])
methods={'testInOrderIntegerKeyInsertion','testOutOfOrderIntegerKeyInsertion','testInOrderLuaLength','testOutOfOrderLuaLength','testInsertBeginningOfList','testInsertEndOfList','testInsertMiddleOfList','testRemoveBeginningOfList','testRemoveEndOfList','testRemoveMiddleOfList'}
ids=[line for line in (root/'documentation/audit-test-cases.list').read_text().splitlines() if ('WeakValueTableTest#' in line or 'WeakKeyValueTableTest#' in line) and line.rsplit('#',1)[-1] in methods]
assert len(ids)==20
(out/'weak.list').write_text('\n'.join(ids)+'\n')
(out/'os.list').write_text('org.luaj.vm2.CompatibiltyTest$JseCompatibilityTest#testOsLib\norg.luaj.vm2.CompatibiltyTest$LuaJCCompatibilityTest#testOsLib\n')
PY
AUDIT_INVENTORY="$output/os.list" AUDIT_TIMEZONE=America/Los_Angeles bash "$root/tools/run-test-audit.sh" "$vm_jar" "$output/os"
work=$(mktemp -d "$output/weak-source.XXXXXX")
git -C "$root" archive daf3da94e3cdba0ac6a289148d7e38bd53d3fe64 src/core/org/luaj/vm2/LuaTable.java | tar -x -C "$work"
patch -d "$work" -p1 < "$root/documentation/weak-routing-experiment.patch"
"$java_home/bin/javac" --release 17 -cp "$vm_jar" -d "$work/classes" "$work/src/core/org/luaj/vm2/LuaTable.java"
mkdir -p "$output/weak"
shasum -a 256 "$work/classes/org/luaj/vm2/LuaTable.class" > "$output/weak/experimental-overlay.sha256"
cp "$root/documentation/weak-routing-experiment.patch" "$output/weak/experimental-overlay.patch"
cd "$work"
"$java_home/bin/java" -Xmx512m -Dfile.encoding=UTF-8 -Duser.timezone=Asia/Tokyo -Duser.language=en -Duser.country=US \
  -cp "$work/classes:$vm_jar:$root/target/test-classes:$output/os/runner:$repository/junit/junit/4.13.2/junit-4.13.2.jar:$repository/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar" \
  TestAuditRunner "$output/weak.list" "$output/weak"
python3 - "$output" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
for name,expected in [('os',2),('weak',20)]:
 rows=[line.split('\t') for line in (root/name/'tests.tsv').read_text().splitlines()]
 assert len(rows)==expected and all(row[1]=='pass' for row in rows),(name,rows)
print('Causal checks passed: 2 timezone cases; 20 experimental routing cases.')
PY
