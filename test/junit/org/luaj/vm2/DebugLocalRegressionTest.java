package org.luaj.vm2;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import junit.framework.TestCase;
import org.luaj.vm2.compiler.DumpState;
import org.luaj.vm2.lib.VarArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;

public class DebugLocalRegressionTest extends TestCase {
    private Globals globals;
    protected void setUp() { globals = JsePlatform.debugGlobals(); }

    private Varargs get(int index) {
        return globals.get("debug").get("getlocal").invoke(
                LuaValue.varargsOf(LuaValue.ONE, LuaValue.valueOf(index)));
    }
    private Varargs set(int index, LuaValue value) {
        return globals.get("debug").get("setlocal").invoke(
                LuaValue.varargsOf(new LuaValue[] {LuaValue.ONE, LuaValue.valueOf(index), value}));
    }
    private void nilOnly(Varargs result) {
        assertEquals(1, result.narg());
        assertTrue(result.arg1().isnil());
    }
    public void testNamedNilAndWritableLocals() {
        Varargs r = globals.load("local function f(a) local b=nil; "
                + "assert(select('#',debug.getlocal(1,2))==2); "
                + "local n,v=debug.getlocal(1,2); assert(n=='b' and v==nil); "
                + "assert(debug.setlocal(1,1,42)=='a'); assert(debug.setlocal(1,2,9)=='b'); return a,b end; return f(11)").invoke();
        assertEquals(42,r.arg1().toint()); assertEquals(9,r.arg(2).toint());
    }
    public void testUnnamedRegistersDoNotEscape() {
        globals.set("probe",new VarArgFunction() {
            public Varargs invoke(Varargs args) {
                for(int i=1;i<=5;i++) nilOnly(DebugLocalRegressionTest.this.get(i));
                return LuaValue.NONE;
            }
        });
        assertEquals(7,globals.load("local function f() probe(11,22,33,44); return 7 end; return f()").call().toint());
    }
    public void testUnnamedRegistersCannotBeWritten() {
        globals.set("probe",new VarArgFunction() {
            public Varargs invoke(Varargs args) {
                nilOnly(DebugLocalRegressionTest.this.set(2,LuaValue.valueOf(99)));
                assertEquals(11,args.arg1().toint());
                nilOnly(DebugLocalRegressionTest.this.set(3,LuaValue.NIL));
                assertEquals(22,args.arg(2).toint());
                return LuaValue.NONE;
            }
        });
        globals.load("local function f() probe(11,22,33,44); return 7 end; return f()").call();
    }
    public void testInvalidIndexBoundaries() {
        globals.set("probe",new VarArgFunction() {
            public Varargs invoke(Varargs args) {
                for(int i:new int[] {Integer.MIN_VALUE,-1,0,100,Integer.MAX_VALUE}) {
                    nilOnly(DebugLocalRegressionTest.this.get(i)); nilOnly(DebugLocalRegressionTest.this.set(i,LuaValue.ONE));
                }
                assertEquals(11,args.arg1().toint()); return LuaValue.NONE;
            }
        });
        globals.load("local function f() probe(11,22,33,44); return 7 end; return f()").call();
    }
    public void testExpiredLocalDoesNotNameReusedRegister() {
        globals.set("probe",new VarArgFunction() {
            public Varargs invoke(Varargs args) {
                assertEquals("a",DebugLocalRegressionTest.this.get(1).arg1().tojstring());
                nilOnly(DebugLocalRegressionTest.this.get(2)); nilOnly(DebugLocalRegressionTest.this.set(3,LuaValue.valueOf(99)));
                assertEquals(11,args.arg1().toint()); return LuaValue.NONE;
            }
        });
        globals.load("local function f(a) do local hidden=8; tostring(hidden) end; probe(11,22,33,44); return a end; return f(7)").call();
    }
    public void testSuspendedCoroutineLocals() {
        Varargs r=globals.load("local co=coroutine.create(function(a) local b=nil; coroutine.yield('paused'); return a,b end); "
                + "assert(coroutine.resume(co,11)); local n,v=debug.getlocal(co,1,2); assert(n=='b' and v==nil); "
                + "assert(debug.setlocal(co,1,1,42)=='a'); assert(debug.setlocal(co,1,2,9)=='b'); "
                + "local ok,a,b=coroutine.resume(co); assert(ok); return a,b,coroutine.status(co)").invoke();
        assertEquals(42,r.arg1().toint()); assertEquals(9,r.arg(2).toint()); assertEquals("dead",r.arg(3).tojstring());
    }
    public void testSuspendedCoroutineUnnamedRegisters() {
        globals.load("co=coroutine.create(function() coroutine.yield('paused'); return 7 end); assert(coroutine.resume(co))").call();
        try {
            nilOnly(globals.get("debug").get("getlocal").invoke(LuaValue.varargsOf(new LuaValue[] {globals.get("co"),LuaValue.ONE,LuaValue.ONE})));
            nilOnly(globals.get("debug").get("setlocal").invoke(LuaValue.varargsOf(new LuaValue[] {globals.get("co"),LuaValue.ONE,LuaValue.ONE,LuaValue.NIL})));
        } finally { globals.get("coroutine").get("resume").call(globals.get("co")); }
    }
    public void testStrippedChunkHasNoNamedLocals() throws Exception {
        globals.set("probe",new VarArgFunction() {
            public Varargs invoke(Varargs args) { nilOnly(DebugLocalRegressionTest.this.get(1)); nilOnly(DebugLocalRegressionTest.this.set(1,LuaValue.valueOf(99))); return LuaValue.NONE; }
        });
        LuaClosure source=globals.load("local function f(a) probe(); return a end; return f(11)").checkclosure();
        ByteArrayOutputStream bytes=new ByteArrayOutputStream(); DumpState.dump(source.p,bytes,true);
        assertEquals(11,globals.load(new ByteArrayInputStream(bytes.toByteArray()),"stripped","b",globals).call().toint());
    }
}
