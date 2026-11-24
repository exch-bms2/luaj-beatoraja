package org.luaj.benchmark;

import java.util.concurrent.TimeUnit;
import org.luaj.vm2.*;
import org.luaj.vm2.lib.OneArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;
import org.openjdk.jmh.annotations.*;

/**
 * Skin-shaped string-key lookups: tables defined in one chunk, read from another.
 * Other skin files are loaded in between, which evicts LuaJ's recent-strings cache,
 * so constants and table keys are distinct objects unless they are interned.
 */
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(value = 3, jvmArgsAppend = {"-Xms512m", "-Xmx512m"})
public class SkinLookupBenchmark {
    private LuaValue fieldLookup, drawCondition, dynamicKeys, javaTailCall, luaTailCall, numberReads;
    private int counter;

    @Setup
    public void setup() {
        Globals g = JsePlatform.standardGlobals();
        LuaTable mainState = new LuaTable();
        mainState.set("number", new OneArgFunction() {
            @Override public LuaValue call(LuaValue v) { return LuaInteger.valueOf(v.toint() & 1023); }
        });
        mainState.set("option", new OneArgFunction() {
            @Override public LuaValue call(LuaValue v) { return LuaValue.valueOf((v.toint() & 1) == 0); }
        });
        g.set("main_state", mainState);
        g.load("MAIN = { OP = { ONLINE = 50, SONGBAR = 2 }, NUM = { TOTALNOTES = 74, IR_RANK = 179 } }\n"
                + "CUSTOM = { NUM = {}, OP = {} }\n"
                + "CUSTOM.NUM.maxExscore = function() return main_state.number(MAIN.NUM.TOTALNOTES) * 2 end\n"
                + "CUSTOM.OP.isMyFrame = function(i) return main_state.number(389 + i) == main_state.number(MAIN.NUM.IR_RANK) end\n",
                "root").call();
        for (int i = 0; i < 20000; i++) LuaString.valueOf("skin-file-string-" + i);
        fieldLookup = g.load("return function() return MAIN.OP.ONLINE + MAIN.NUM.TOTALNOTES + MAIN.OP.SONGBAR end",
                "select").call();
        drawCondition = g.load("local refRate = {100, 88.8, 77.7, 66.6, 55.5, 44.4, 33.3, 22.2, -1}\n"
                + "local i, j = 3, 4\n"
                + "return function()\n"
                + "  local exScore = main_state.number(379 + i)\n"
                + "  local rankRate = (exScore / CUSTOM.NUM.maxExscore()) * 100\n"
                + "  return main_state.option(MAIN.OP.SONGBAR) and main_state.option(MAIN.OP.ONLINE)"
                + " and rankRate <= refRate[j] and rankRate > refRate[j + 1]\n"
                + "end", "select2").call();
        // `return f(x)`: a Java function (in-place call) and a Lua function (TailcallVarargs, control).
        javaTailCall = g.load("return function() return main_state.option(MAIN.OP.ONLINE) end", "tail1").call();
        luaTailCall = g.load("return function() return CUSTOM.OP.isMyFrame(3) end", "tail2").call();
        // Like WMII getScoreInfo: fractional and large numbers read from a constant table.
        numberReads = g.load("local rankBorders = {}\n"
                + "for i, v in ipairs({0, 2/9, 3/9, 4/9, 5/9, 6/9, 7/9, 8/9, 1}) do rankBorders[i] = { value = v, ex = 1000 + i } end\n"
                + "return function() local s = 0 for i = 1, #rankBorders do s = s + rankBorders[i].value + rankBorders[i].ex end return s end",
                "numbers").call();
        // Worst case for interning: every insert is a new, never-seen string key.
        dynamicKeys = g.load("return function(n) local t = {} t['key' .. n] = n return t end", "dynamic").call();
    }

    @Benchmark public LuaValue crossChunkFieldLookup() { return fieldLookup.call(); }
    @Benchmark public LuaValue skinDrawCondition() { return drawCondition.call(); }
    @Benchmark public LuaValue javaFunctionTailCall() { return javaTailCall.call(); }
    @Benchmark public LuaValue luaFunctionTailCall() { return luaTailCall.call(); }
    @Benchmark public LuaValue tableNumberReads() { return numberReads.call(); }

    /** Like beatoraja's main_state.offset: a fresh table with Java-created string keys. */
    @Benchmark public LuaTable javaKeyTable() {
        LuaTable t = new LuaTable();
        t.set("x", LuaValue.ZERO); t.set("y", LuaValue.ZERO); t.set("w", LuaValue.ZERO);
        t.set("h", LuaValue.ZERO); t.set("r", LuaValue.ZERO); t.set("a", LuaValue.ZERO);
        return t;
    }

    @Benchmark public LuaValue newStringKeyInsert() { return dynamicKeys.call(LuaValue.valueOf(counter++)); }
}
