#!/usr/bin/env python3
"""Run each new correctness test in its own JVM with a bounded timeout."""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import re
import subprocess

p = argparse.ArgumentParser()
p.add_argument('jar', type=pathlib.Path)
p.add_argument('output', type=pathlib.Path)
p.add_argument('--timeout', type=float, default=5)
p.add_argument('--expect-pass', action='store_true')
p.add_argument('--classes', nargs='+', default=['WeakIntegerKeyTest','FmodRegressionTest','ModfRegressionTest'])
a = p.parse_args()
root = pathlib.Path(__file__).resolve().parent.parent
output = a.output.resolve()
output.mkdir(parents=True, exist_ok=True)
jar = a.jar.resolve()
java_home = pathlib.Path(os.environ['JAVA_HOME'])
repo = pathlib.Path(os.environ.get('MAVEN_REPO', str(pathlib.Path.home()/'.m2/repository')))
junit = repo/'junit/junit/4.13.2/junit-4.13.2.jar'
hamcrest = repo/'org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar'
source = output/'RegressionCaseRunner.java'
source.write_text('''import org.junit.runner.*;
import org.junit.runner.notification.Failure;
public class RegressionCaseRunner {
  public static void main(String[] args) throws Exception {
    Result result = new JUnitCore().run(Request.method(Class.forName(args[0]),args[1]));
    for(Failure failure:result.getFailures()) System.out.println(failure.getTrace());
    System.exit(result.wasSuccessful() && result.getRunCount()==1 ? 0 : 1);
  }
}
''')
subprocess.run([str(java_home/'bin/javac'),'--release','17','-cp',str(junit),'-d',str(output),str(source)],check=True)
classpath = os.pathsep.join(map(str,[jar,root/'target/test-classes',output,junit,hamcrest]))
records = {}
for cls in a.classes:
    text = (root/'test/junit/org/luaj/vm2'/(cls+'.java')).read_text()
    for method in re.findall(r'public void (test\w+)\(',text):
        key = 'org.luaj.vm2.'+cls+'#'+method
        command = [str(java_home/'bin/java'),'-Xmx128m','-Dfile.encoding=UTF-8','-Duser.language=en','-Duser.country=US',
                   '-cp',classpath,'RegressionCaseRunner','org.luaj.vm2.'+cls,method]
        try:
            result = subprocess.run(command,capture_output=True,text=True,timeout=a.timeout)
            records[key] = {'status':'pass' if result.returncode==0 else 'fail','diagnostic':result.stdout+result.stderr}
        except subprocess.TimeoutExpired:
            # subprocess.run kills and waits for this child, without a global process lookup.
            records[key] = {'status':'timeout','seconds':a.timeout}
result = {'vm_sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'per_case_heap':'128m','timeout_seconds':a.timeout,'cases':records}
(output/'results.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(dict(collections.Counter(x['status'] for x in records.values())))
if a.expect_pass and any(x['status']!='pass' for x in records.values()):
    raise SystemExit(1)
