package org.luaj.vm2;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import junit.framework.TestCase;
import org.luaj.vm2.compiler.DumpState;
import org.luaj.vm2.lib.ZeroArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;

public class DebugFunctionLocalRegressionTest extends TestCase {
    private Globals globals;
    protected void setUp() { globals=JsePlatform.debugGlobals(); }
    private Varargs get(LuaValue function, LuaValue index) {
        return globals.get("debug").get("getlocal").invoke(LuaValue.varargsOf(function,index));
    }
    private void name(Varargs result,String expected) {
        assertEquals(1,result.narg()); assertEquals(LuaValue.TSTRING,result.arg1().type());
        assertEquals(expected,result.arg1().tojstring());
    }
    private void nilOnly(Varargs result) { assertEquals(1,result.narg()); assertTrue(result.arg1().isnil()); }
    public void testUncalledFunctionParametersWithoutExecutingBody() {
        LuaValue f=globals.load("return function(first,second) error('must not execute') end").call();
        name(get(f,LuaValue.ONE),"first"); name(get(f,LuaValue.valueOf(2)),"second");
        assertNull(globals.debuglib.getCallFrame(1));
    }
    public void testOnlyParametersNotBodyLocalsOrUpvalues() {
        LuaValue f=globals.load("local up=7; return function(a) local b=up; return a+b end").call();
        name(get(f,LuaValue.ONE),"a"); nilOnly(get(f,LuaValue.valueOf(2)));
    }
    public void testNoParameterFunctionAndMainChunk() {
        nilOnly(get(globals.load("return function() local a=7; return a end").call(),LuaValue.ONE));
        nilOnly(get(globals.load("local a=7; return a"),LuaValue.ONE));
    }
    public void testIndexBoundariesAndVarargs() {
        LuaValue f=globals.load("return function(a,...) return a,... end").call();
        name(get(f,LuaValue.ONE),"a");
        for(int i:new int[] {Integer.MIN_VALUE,-1,0,2,Integer.MAX_VALUE}) nilOnly(get(f,LuaValue.valueOf(i)));
    }
    public void testJavaFunctionsHaveNoParameterMetadata() {
        nilOnly(get(globals.get("print"),LuaValue.ONE));
        nilOnly(get(new ZeroArgFunction() { public LuaValue call() { fail("must not execute"); return LuaValue.NIL; } },LuaValue.ONE));
    }
    public void testExplicitThreadDoesNotRequireAnActiveFrame() {
        Varargs r=globals.load("local co=coroutine.create(function() end); local f=function(a) end; "
                + "assert(debug.getlocal(co,f,1)=='a'); assert(coroutine.resume(co)); "
                + "return debug.getlocal(co,f,1)").invoke();
        name(r,"a");
    }
    public void testExecutingFunctionStillReturnsOnlyName() {
        Varargs r=globals.load("local f; f=function(a) local n=debug.getlocal(f,1); "
                + "assert(select('#',debug.getlocal(f,1))==1); assert(debug.getlocal(1,1)=='a'); return n,a end; return f(11)").invoke();
        assertEquals("a",r.arg1().tojstring()); assertEquals(11,r.arg(2).toint());
    }
    public void testStrippedBinaryReturnsNil() throws Exception {
        LuaClosure f=globals.load("return function(a,b) return a,b end").call().checkclosure();
        ByteArrayOutputStream out=new ByteArrayOutputStream(); DumpState.dump(f.p,out,true);
        LuaValue stripped=globals.load(new ByteArrayInputStream(out.toByteArray()),"stripped","b",globals);
        nilOnly(get(stripped,LuaValue.ONE)); nilOnly(get(stripped,LuaValue.valueOf(2)));
    }
    public void testNumericStringIndexAndExtraArguments() {
        LuaValue f=globals.load("return function(a,b) end").call();
        name(get(f,LuaValue.valueOf("2")),"b");
        name(globals.get("debug").get("getlocal").invoke(LuaValue.varargsOf(new LuaValue[] {f,LuaValue.ONE,LuaValue.valueOf(99)})),"a");
    }
    public void testMissingAndInvalidIndicesAreLuaErrors() {
        LuaValue f=globals.load("return function(a) end").call();
        for(Varargs args:new Varargs[] {f,LuaValue.varargsOf(f,LuaValue.NIL),LuaValue.varargsOf(f,new LuaTable()),LuaValue.varargsOf(f,LuaValue.TRUE)}) {
            try { globals.get("debug").get("getlocal").invoke(args); fail("index required"); }
            catch(LuaError e) { assertTrue(e.getMessage().contains("int expected, got "+args.arg(2).typename())); }
        }
    }
}
