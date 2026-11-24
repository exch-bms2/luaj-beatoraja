package org.luaj.vm2;

import junit.framework.TestCase;
import org.luaj.vm2.lib.jse.JsePlatform;

public class DebugStackLevelRegressionTest extends TestCase {
    private Globals globals;
    protected void setUp() { globals=JsePlatform.debugGlobals(); }
    private void invalid(String operation,LuaValue thread,int level) {
        LuaValue[] args=thread==null? new LuaValue[] {LuaValue.valueOf(level),LuaValue.ONE,LuaValue.NIL}
                :new LuaValue[] {thread,LuaValue.valueOf(level),LuaValue.ONE,LuaValue.NIL};
        try { globals.get("debug").get(operation).invoke(LuaValue.varargsOf(args)); fail("invalid level accepted"); }
        catch(LuaError e) { assertEquals("bad argument #"+(thread==null?1:2)+": level out of range",e.getMessage()); }
    }
    public void testGetLocalRejectsAbsentAndNegativeLevels() {
        for(int level:new int[] {Integer.MIN_VALUE,-1,1,2,Integer.MAX_VALUE}) invalid("getlocal",null,level);
    }
    public void testSetLocalRejectsAbsentAndNegativeLevels() {
        for(int level:new int[] {Integer.MIN_VALUE,-1,1,2,Integer.MAX_VALUE}) invalid("setlocal",null,level);
    }
    public void testExplicitThreadErrorsUseSecondArgument() {
        LuaValue co=globals.load("return coroutine.create(function() end)").call();
        for(String op:new String[] {"getlocal","setlocal"}) for(int level:new int[] {-1,1,Integer.MAX_VALUE}) invalid(op,co,level);
    }
    public void testDeadCoroutineHasNoCallerFrame() {
        LuaValue co=globals.load("local co=coroutine.create(function() end); assert(coroutine.resume(co)); return co").call();
        invalid("getlocal",co,1); invalid("setlocal",co,1);
    }
    public void testZeroLevelIsTheDebugJavaFunction() {
        for(String op:new String[] {"getlocal","setlocal"}) {
            Varargs r=globals.get("debug").get(op).invoke(LuaValue.varargsOf(new LuaValue[] {LuaValue.ZERO,LuaValue.ONE,LuaValue.NIL}));
            assertEquals(1,r.narg()); assertTrue(r.arg1().isnil());
        }
    }
    public void testLastCallerFrameAndNextLevel() {
        globals.load("local function f(a) assert(debug.getlocal(1,1)=='a'); assert(debug.getinfo(2)~=nil); assert(debug.getlocal(2,1)=='f'); "
                + "local ok,e=pcall(debug.getlocal,4,1); assert(not ok and e:find('level out of range')); "
                + "local ok,e=pcall(debug.setlocal,4,1,nil); assert(not ok and e:find('level out of range')) end; f(11)","debug-level-boundary").call();
    }
    public void testSuspendedCoroutineRangeAndValidVarargs() {
        LuaValue co=globals.load("local co=coroutine.create(function(...) coroutine.yield(); return ... end); assert(coroutine.resume(co,11)); return co").call();
        try {
            invalid("getlocal",co,2); invalid("setlocal",co,2);
            Varargs r=globals.get("debug").get("getlocal").invoke(LuaValue.varargsOf(new LuaValue[] {co,LuaValue.ONE,LuaValue.valueOf(-1)}));
            assertEquals("(*vararg)",r.arg1().tojstring()); assertEquals(11,r.arg(2).toint());
        } finally { assertTrue(globals.get("coroutine").get("resume").invoke(co).arg1().toboolean()); }
    }
    public void testFunctionFormDoesNotRequireStackLevel() {
        Varargs r=globals.load("local co=coroutine.create(function() end); local f=function(a) end; return debug.getlocal(co,f,1)").invoke();
        assertEquals(1,r.narg()); assertEquals("a",r.arg1().tojstring());
    }
    public void testInvalidLocalOnValidFrameStillReturnsNil() {
        globals.load("local function f() assert(select('#',debug.getlocal(1,1000))==1); "
                + "assert(debug.getlocal(1,1000)==nil and debug.setlocal(1,1000,99)==nil); "
                + "assert(debug.getlocal(1,-1000)==nil and debug.setlocal(1,-1000,99)==nil) end; f()").call();
    }
    public void testProtectedErrorsRestoreFramesAndHandlers() {
        Varargs r=globals.load("local hits=0; local ok,e=xpcall(function() debug.getlocal(1000,1) end, "
                + "function(e) hits=hits+1; assert(e:find('level out of range')); return 'handled' end); return ok,e,hits","debug-level-error").invoke();
        assertFalse(r.arg1().toboolean()); assertEquals("handled",r.arg(2).tojstring()); assertEquals(1,r.arg(3).toint());
        assertNull(globals.running.errorfunc); assertNull(globals.debuglib.getCallFrame(1));
    }
}
