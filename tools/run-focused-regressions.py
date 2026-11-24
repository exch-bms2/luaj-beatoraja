#!/usr/bin/env python3
"""Run all added correctness regressions against exactly one supplied VM jar."""
import argparse
import os
import pathlib
import subprocess
p = argparse.ArgumentParser()
p.add_argument('jar',type=pathlib.Path)
p.add_argument('log',type=pathlib.Path)
a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent.parent
repo=pathlib.Path(os.environ.get('MAVEN_REPO',str(pathlib.Path.home()/'.m2/repository')))
classes=['StackLifetimeTest','StackPoolTest','WeakIntegerKeyTest','FmodRegressionTest','ModfRegressionTest',
         'MinMaxRegressionTest','LuaDoubleFormattingTest','LoadReaderRegressionTest','PcallScopeRegressionTest',
         'DebugLocalRegressionTest','DebugJavaFrameRegressionTest','DebugFunctionLocalRegressionTest',
         'DebugSetLocalValueRegressionTest','DebugVarargsRegressionTest','DebugStackLevelRegressionTest']
extra=r/'test/junit/org/luaj/vm2/SingleCallPoolRegressionTest.java'
if extra.exists(): classes.append('SingleCallPoolRegressionTest')
cp=os.pathsep.join(map(str,[a.jar.resolve(),r/'target/test-classes',repo/'junit/junit/4.13.2/junit-4.13.2.jar',repo/'org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar']))
a.log.parent.mkdir(parents=True,exist_ok=True)
with a.log.open('w') as log:
 subprocess.run([os.environ['JAVA_HOME']+'/bin/java','-Xmx512m','-cp',cp,'org.junit.runner.JUnitCore']+
                ['org.luaj.vm2.'+c for c in classes],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
print(a.log.read_text().splitlines()[-2])
