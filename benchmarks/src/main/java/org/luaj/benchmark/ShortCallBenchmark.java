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
public class ShortCallBenchmark {
    private LuaValue zero, one, four, multi, tail, text, recursive;
    private Varargs arguments;

    @Setup
    public void setup() {
        Globals g = JsePlatform.standardGlobals();
        zero = g.load("return function() return 42 end").call();
        one = g.load("return function(x) return x+1 end").call();
        four = g.load("return function(a,b,c,d) return a+b+c+d end").call();
        multi = g.load("return function(a) return a,a+1,a+2,a+3 end").call();
        tail = g.load("local function f(n,a,b,c) if n==0 then return a end return f(n-1,a+1,b,c) end return f").call();
        arguments = LuaValue.varargsOf(new LuaValue[] {LuaValue.valueOf(10), LuaValue.ONE, LuaValue.ONE, LuaValue.ONE});
        recursive = g.load("local function f(n) if n==0 then return 0 end return f(n-1)+1 end return f").call();
        text = LuaValue.valueOf("選曲画面 / beatoraja");
    }

    @Benchmark public LuaValue zeroArguments() { return zero.call(); }
    @Benchmark public LuaValue oneArgument() { return one.call(LuaValue.ONE); }
    @Benchmark public Varargs fourArguments() { return four.invoke(arguments); }
    @Benchmark public Varargs multipleResults() { return multi.invoke(LuaValue.ONE); }
    @Benchmark public Varargs tailRecursion() { return tail.invoke(arguments); }
    @Benchmark public LuaValue recursiveSingleResult() { return recursive.call(LuaValue.valueOf(8)); }
    @Benchmark public String toJavaString() { return text.tojstring(); }
    @Benchmark public LuaValue fromJavaString() { return LuaValue.valueOf("選曲画面 / beatoraja"); }
}
