package org.luaj.vm2;

import junit.framework.TestCase;
import org.luaj.vm2.lib.VarArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;

public class DebugJavaFrameRegressionTest extends TestCase {
    private Globals globals;
    protected void setUp() { globals = JsePlatform.debugGlobals(); }
    private void nilOnly(Varargs r) { assertEquals(1,r.narg()); assertTrue(r.arg1().isnil()); }
    private Varargs access(String operation, LuaValue thread, int level, int index) {
        LuaValue[] args=thread==null
                ? new LuaValue[] {LuaValue.valueOf(level),LuaValue.valueOf(index),LuaValue.valueOf(99)}
                : new LuaValue[] {thread,LuaValue.valueOf(level),LuaValue.valueOf(index),LuaValue.valueOf(99)};
        return globals.get("debug").get(operation).invoke(LuaValue.varargsOf(args));
    }
    public void testRegisteredJavaFrameGetLocal() { registered("getlocal"); }
    public void testRegisteredJavaFrameSetLocal() { registered("setlocal"); }
    private void registered(final String operation) {
        globals.set("probe",new VarArgFunction() {
            public Varargs invoke(Varargs args) {
                globals.debuglib.onCall(this);
                try {
                    for(int i:new int[] {1,2,Integer.MAX_VALUE,0,-1,Integer.MIN_VALUE})
                        nilOnly(access(operation,null,1,i));
                    assertEquals(11,args.arg1().toint());
                    return LuaValue.NONE;
                } finally { globals.debuglib.onReturn(); }
            }
        });
        assertEquals(7,globals.load("local function f(a) probe(11,22,33,44); return a end; return f(7)").call().toint());
        assertNull(globals.debuglib.getCallFrame(1));
    }
    public void testPcallJavaFrameAndLuaCaller() {
        Varargs r=globals.load("local function f(a) local ok,v=pcall(function() "
                + "assert(select('#',debug.getlocal(2,1))==1); assert(debug.getlocal(2,1)==nil); "
                + "assert(debug.setlocal(2,1,99)==nil); return 8 end); assert(ok,v); return a,v end; return f(7)").invoke();
        assertEquals(7,r.arg1().toint()); assertEquals(8,r.arg(2).toint());
        assertNull(globals.debuglib.getCallFrame(1));
    }
    public void testXpcallJavaFrameAndErrorHandler() {
        Varargs r=globals.load("local hits=0; local reached=false; local ok,v=xpcall(function() "
                + "assert(debug.getlocal(2,1)==nil); assert(debug.setlocal(2,1,99)==nil); reached=true; error('wanted') end, "
                + "function(e) hits=hits+1; assert(e:find('wanted')); return 'handled' end); return ok,v,hits,reached","java-frame-error").invoke();
        assertFalse(r.arg1().toboolean()); assertEquals("handled",r.arg(2).tojstring()); assertEquals(1,r.arg(3).toint()); assertTrue(r.arg(4).toboolean());
        assertNull(globals.debuglib.getCallFrame(1));
    }
    public void testSuspendedPcallJavaFrame() {
        globals.load("co=coroutine.create(function() local ok,v=pcall(function(a) coroutine.yield('paused'); return a end,11); assert(ok,v); return v end); assert(coroutine.resume(co))").call();
        LuaValue co=globals.get("co");
        try {
            nilOnly(access("getlocal",co,2,1)); nilOnly(access("setlocal",co,2,1));
            Varargs local=globals.get("debug").get("getlocal").invoke(LuaValue.varargsOf(new LuaValue[] {co,LuaValue.ONE,LuaValue.ONE}));
            assertEquals("a",local.arg1().tojstring()); assertEquals(11,local.arg(2).toint());
        } finally {
            Varargs r=globals.get("coroutine").get("resume").invoke(co);
            assertTrue(r.arg1().toboolean()); assertEquals(11,r.arg(2).toint());
        }
        assertEquals("dead",globals.get("coroutine").get("status").call(co).tojstring());
    }
    public void testJavaFrameReusedAfterLuaFrame() {
        Varargs r=globals.load("local function f(a) return a+1 end; assert(f(6)==7); "
                + "for i=1,5 do local ok,v=pcall(function(a) "
                + "assert(debug.getlocal(2,1)==nil); assert(debug.setlocal(2,1,99)==nil); "
                + "assert(debug.setlocal(1,1,8)=='a'); return a end,7); assert(ok,v); assert(v==8) end; return 9").invoke();
        assertEquals(9,r.arg1().toint()); assertNull(globals.debuglib.getCallFrame(1));
    }
}
