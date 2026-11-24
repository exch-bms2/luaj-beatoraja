package org.luaj.vm2;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import junit.framework.TestCase;
import org.luaj.vm2.compiler.DumpState;
import org.luaj.vm2.lib.VarArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;

public class DebugVarargsRegressionTest extends TestCase {
    private Globals globals;
    protected void setUp() { globals=JsePlatform.debugGlobals(); }
    private Varargs run(String source) { return globals.load(source,"debug-varargs").invoke(); }
    public void testNamesValuesAndNilArity() {
        Varargs r=run("local function f(a,...) local n,v=debug.getlocal(1,-1); assert(n=='(*vararg)' and v==11); "
                + "assert(select('#',debug.getlocal(1,-2))==2); local n,v=debug.getlocal(1,-2); assert(n=='(*vararg)' and v==nil); "
                + "local n,v=debug.getlocal(1,-3); assert(n=='(*vararg)' and v==33); return ... end; return f(7,11,nil,33,nil)");
        assertEquals(4,r.narg()); assertEquals(11,r.arg1().toint()); assertTrue(r.arg(2).isnil()); assertEquals(33,r.arg(3).toint()); assertTrue(r.arg(4).isnil());
    }
    public void testWritesAreVisibleToLaterVarargInstructions() {
        Varargs r=run("local function f(a,...) assert(debug.setlocal(1,-1,99)=='(*vararg)'); "
                + "assert(debug.setlocal(1,-2,nil)=='(*vararg)'); assert(debug.setlocal(1,-3,77)=='(*vararg)'); "
                + "assert(select('#',debug.setlocal(1,-1,99))==1); return a,... end; return f(7,11,22,33)");
        assertEquals(4,r.narg()); assertEquals(7,r.arg1().toint()); assertEquals(99,r.arg(2).toint()); assertTrue(r.arg(3).isnil()); assertEquals(77,r.arg(4).toint());
    }
    public void testFixedCountVarargReadUsesChangedValue() {
        assertEquals(99,run("local function f(...) debug.setlocal(1,-1,99); local a=...; return a end; return f(11)").arg1().toint());
    }
    public void testOutOfRangeAndIntegerMinimumDoNotWrite() {
        Varargs r=run("local function f(...) for _,i in ipairs({-2,-2147483648}) do "
                + "assert(select('#',debug.getlocal(1,i))==1 and debug.getlocal(1,i)==nil); "
                + "assert(debug.setlocal(1,i,99)==nil) end; return ... end; return f(11)");
        assertEquals(11,r.arg1().toint());
    }
    public void testNoVarargsOrNonVarargFunction() {
        run("local function f(...) assert(debug.getlocal(1,-1)==nil); assert(debug.setlocal(1,-1,99)==nil) end; f(); "
                + "local function g(a) assert(debug.getlocal(1,-1)==nil); assert(debug.setlocal(1,-1,99)==nil); return a end; assert(g(7,11)==7); "
                + "assert(debug.getlocal(f,-1)==nil); assert(pcall(function() assert(debug.getlocal(2,-1)==nil); assert(debug.setlocal(2,-1,99)==nil) end))");
    }
    public void testJavaFixedArityCallEntrypoints() {
        LuaValue f=globals.load("return function(...) local n,v=debug.getlocal(1,-1); assert(n=='(*vararg)'); debug.setlocal(1,-1,99); return ... end").call();
        assertEquals(99,f.call(LuaValue.ONE).toint()); assertEquals(99,f.call(LuaValue.ONE,LuaValue.ONE).toint());
        assertEquals(99,f.call(LuaValue.ONE,LuaValue.ONE,LuaValue.ONE).toint());
    }
    public void testCallerOwnedArrayAndPreviouslyReadValueAreNotMutated() {
        LuaValue[] input={LuaValue.valueOf(11),LuaValue.valueOf(22),LuaValue.valueOf(33),LuaValue.valueOf(44)};
        LuaValue f=globals.load("return function(...) local old=...; debug.setlocal(1,-1,99); return old,... end").call();
        Varargs r=f.invoke(LuaValue.varargsOf(input));
        assertEquals(11,input[0].toint()); assertEquals(11,r.arg1().toint()); assertEquals(99,r.arg(2).toint());
    }
    public void testPendingCallArgumentsRemainSnapshot() {
        globals.set("probe",new VarArgFunction() {
            public Varargs invoke(Varargs args) {
                LuaValue name=globals.get("debug").get("setlocal").call(LuaValue.ONE,LuaValue.valueOf(-1),LuaValue.valueOf(99));
                assertEquals("(*vararg)",name.tojstring()); assertEquals(11,args.arg1().toint()); return LuaValue.valueOf(7);
            }
        });
        Varargs r=run("local function f(...) local r=probe(...); return r,... end; return f(11,22,33,44)");
        assertEquals(7,r.arg1().toint()); assertEquals(99,r.arg(2).toint());
    }
    public void testSuspendedCoroutineAfterTemporaryMultivalues() {
        Varargs r=run("local co=coroutine.create(function(a,...) local x,y=string.find('abc','b'); coroutine.yield(x,y); return a,... end); "
                + "assert(coroutine.resume(co,7,11,nil,33)); local n,v=debug.getlocal(co,1,-3); assert(n=='(*vararg)' and v==33); "
                + "assert(debug.setlocal(co,1,-2,22)=='(*vararg)'); assert(debug.setlocal(co,1,-1,nil)=='(*vararg)'); "
                + "local ok,a,b,c,d=coroutine.resume(co); assert(ok); return a,b,c,d,coroutine.status(co)");
        assertEquals(7,r.arg1().toint()); assertTrue(r.arg(2).isnil()); assertEquals(22,r.arg(3).toint()); assertEquals(33,r.arg(4).toint()); assertEquals("dead",r.arg(5).tojstring());
    }
    public void testRecursiveFramesHaveSeparateVarargs() {
        run("local function f(n,...) if n>0 then f(n-1,22); local name,v=debug.getlocal(1,-1); assert(v==11) "
                + "else assert(debug.setlocal(1,-1,99)=='(*vararg)'); local name,v=debug.getlocal(2,-1); assert(v==11) end end; f(1,11)");
    }
    public void testCallHookCanChangeInitialVarargs() {
        Varargs r=run("local f=function(...) return ... end; debug.sethook(function(event) "
                + "if event=='call' and debug.getinfo(1,'f').func==f then "
                + "local name,v=debug.getlocal(1,-1); assert(name=='(*vararg)' and v==11); assert(debug.setlocal(1,-1,99)=='(*vararg)') end end,'c'); "
                + "local v=f(11); debug.sethook(); return v");
        assertEquals(99,r.arg1().toint());
    }
    public void testExceptionAndFrameReuseClearVarargs() {
        run("local function f(...) debug.setlocal(1,-1,99); error('wanted') end; assert(not pcall(f,11)); "
                + "local function g() assert(debug.getlocal(1,-1)==nil); assert(debug.setlocal(1,-1,99)==nil) end; g()");
        assertNull(globals.debuglib.getCallFrame(1));
    }
    public void testRetainedResultsSurviveLaterCallAndDebugWrite() {
        LuaValue f=globals.load("return function(...) debug.setlocal(1,-1,99); return ... end").call();
        Varargs first=f.invoke(LuaValue.varargsOf(new LuaValue[] {LuaValue.ONE,LuaValue.valueOf(2),LuaValue.valueOf(3),LuaValue.valueOf(4)}));
        f.invoke(LuaValue.varargsOf(new LuaValue[] {LuaValue.valueOf(5),LuaValue.valueOf(6),LuaValue.valueOf(7),LuaValue.valueOf(8)}));
        assertEquals(99,first.arg1().toint()); assertEquals(2,first.arg(2).toint()); assertEquals(4,first.arg(4).toint());
    }
    public void testStrippedChunkStillHasVarargValues() throws Exception {
        LuaClosure f=globals.load("return function(...) debug.setlocal(1,-1,99); return ... end").call().checkclosure();
        ByteArrayOutputStream out=new ByteArrayOutputStream(); DumpState.dump(f.p,out,true);
        LuaValue stripped=globals.load(new ByteArrayInputStream(out.toByteArray()),"stripped","b",globals);
        assertEquals(99,stripped.call(LuaValue.ONE).toint());
    }
}
