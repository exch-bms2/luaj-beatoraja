package org.luaj.benchmark;

import java.util.concurrent.TimeUnit;
import org.luaj.vm2.*;
import org.luaj.vm2.lib.jse.JsePlatform;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(value = 3, jvmArgsAppend = {"-Xms512m", "-Xmx512m"})
public class MultiReturnBenchmark {
    private LuaValue two, prefixed, passthrough, four;
    private Varargs borrowed;
    @Setup public void setup() {
        Globals g=JsePlatform.standardGlobals();
        two=g.load("return function(x) return x,x+1 end").call();
        four=g.load("return function(x) return x,x+1,x+2,x+3 end").call();
        prefixed=g.load("local function f(x) return x,x+1,x+2,x+3 end; return function(x) return x-1,f(x) end").call();
        passthrough=g.load("return function(...) return ... end").call();
        borrowed=LuaValue.varargsOf(new LuaValue[] {LuaValue.ONE,LuaValue.NIL,LuaValue.valueOf(3),LuaValue.NIL});
    }
    @Benchmark public Varargs twoResults() { return two.invoke(LuaValue.ONE); }
    @Benchmark public Varargs prefixedResults() { return prefixed.invoke(LuaValue.ONE); }
    @Benchmark public Varargs borrowedPassthrough() { return passthrough.invoke(borrowed); }
    @Benchmark public LuaValue discardedResults() { return four.call(LuaValue.ONE); }
}
