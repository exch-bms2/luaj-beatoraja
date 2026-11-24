package org.luaj.vm2;

import junit.framework.TestCase;
import org.luaj.vm2.lib.VarArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;

/** Runs unchanged against the pinned legacy jar and the fork. */
public class StackLifetimeTest extends TestCase {
    private Globals globals;

    protected void setUp() {
        globals = JsePlatform.standardGlobals();
    }

    private LuaValue function(String body) {
        return globals.load(body, "stack-lifetime").call();
    }

    private void values(Varargs actual, int... expected) {
        assertEquals(expected.length, actual.narg());
        for (int i = 0; i < expected.length; i++)
            assertEquals("argument " + (i + 1), LuaValue.valueOf(expected[i]), actual.arg(i + 1));
    }

    public void testRetainedMultipleResults() {
        LuaValue f = function("return function(x) return x,x+1,x+2,x+3 end");
        Varargs first = f.invoke(LuaValue.valueOf(10));
        values(f.invoke(LuaValue.valueOf(20)), 20,21,22,23);
        values(first, 10,11,12,13);
    }

    public void testOpenReturnWithPrefix() {
        LuaValue f = function("local function pair(x) return x,x+1 end "
                + "return function(x) return x-1,pair(x) end");
        Varargs first = f.invoke(LuaValue.valueOf(10));
        f.invoke(LuaValue.valueOf(20));
        values(first, 9,10,11);
    }

    public void testFourArgumentTailRecursion() {
        LuaValue f = function("local function f(n,a,b,c) if n==0 then return a,b,c end "
                + "return f(n-1,a+1,b+2,c+3) end return f");
        values(f.invoke(LuaValue.varargsOf(new LuaValue[] {
                LuaValue.valueOf(10000), LuaValue.ZERO, LuaValue.ZERO, LuaValue.ZERO})),
                10000,20000,30000);
    }

    public void testDeferredTailcallArgumentsSurviveAnotherCall() {
        LuaClosure f = function("local function id(...) return ... end "
                + "return function(a,b,c,d) return id(a,b,c,d) end").checkclosure();
        Varargs deferred = f.onInvoke(LuaValue.varargsOf(new LuaValue[] {
                LuaValue.valueOf(1), LuaValue.valueOf(2), LuaValue.valueOf(3), LuaValue.valueOf(4)}));
        f.invoke(LuaValue.NONE);
        values(deferred.eval(), 1,2,3,4);
    }

    public void testRecursionAndMutualRecursion() {
        values(globals.load("local function sum(n) if n==0 then return 0 end return n+sum(n-1) end "
                + "local a,b; a=function(n) if n==0 then return 1 end return b(n-1) end; "
                + "b=function(n) if n==0 then return 2 end return a(n-1) end; "
                + "return sum(100),a(1001)").invoke(), 5050,2);
    }

    public void testJavaReentry() {
        globals.set("reenter", new VarArgFunction() {
            public Varargs invoke(Varargs args) {
                return globals.get("recursive").invoke(args);
            }
        });
        globals.load("function recursive(n) if n==0 then return 0,1,2,3 end "
                + "local a,b,c,d=reenter(n-1); return a+1,b+1,c+1,d+1 end").call();
        values(globals.get("recursive").invoke(LuaValue.valueOf(30)), 30,31,32,33);
    }

    public void testVarargsAndNilPositions() {
        LuaValue f = function("return function(x,...) return x,... end");
        Varargs first = f.invoke(LuaValue.varargsOf(new LuaValue[] {
                LuaValue.valueOf(1), LuaValue.NIL, LuaValue.valueOf(3), LuaValue.NIL}));
        f.invoke(LuaValue.valueOf(99));
        assertEquals(4, first.narg());
        assertEquals(1, first.arg1().toint());
        assertTrue(first.arg(2).isnil());
        assertEquals(3, first.arg(3).toint());
        assertTrue(first.arg(4).isnil());
    }

    public void testClosedUpvaluesSurviveReuseAndException() {
        LuaValue f = function("return function(x,fail) local function read() return x end "
                + "saved=read; if fail then error('expected') end return read end");
        LuaValue first = f.call(LuaValue.valueOf(10));
        try {
            f.call(LuaValue.valueOf(20), LuaValue.TRUE);
            fail("exception expected");
        } catch (LuaError expected) { }
        LuaValue afterError = globals.get("saved");
        f.call(LuaValue.valueOf(30));
        assertEquals(10, first.call().toint());
        assertEquals(20, afterError.call().toint());
    }

    public void testPcallAndCoroutineResume() {
        values(globals.load("local function f(n) local x=n; "
                + "local ok=pcall(function() error('expected') end); "
                + "assert(not ok); coroutine.yield(x,x+1,x+2,x+3); return x+4 end; "
                + "local a=coroutine.create(f); local b=coroutine.create(f); "
                + "local ok,x,y,z,w=coroutine.resume(a,10); assert(ok); "
                + "assert(coroutine.resume(b,20)); local ok,last=coroutine.resume(a); assert(ok); "
                + "assert(coroutine.resume(b)); return x,y,z,w,last").invoke(), 10,11,12,13,14);
    }

    public void testYieldThroughPcall() {
        values(globals.load("local co=coroutine.create(function() "
                + "local ok,a,b,c,d=pcall(function() local x=coroutine.yield(1,2,3,4); "
                + "return x,x+1,x+2,x+3 end); assert(ok); return a,b,c,d end); "
                + "local ok,a,b,c,d=coroutine.resume(co); assert(ok); "
                + "local ok,e,f,g,h=coroutine.resume(co,10); assert(ok); "
                + "return a,b,c,d,e,f,g,h").invoke(), 1,2,3,4,10,11,12,13);
    }

    public void testStateAndFreshTableIdentity() {
        LuaValue f = function("local n=0; return function() n=n+1; return {n=n},n end");
        Varargs first = f.invoke();
        Varargs second = f.invoke();
        assertNotSame(first.arg1(), second.arg1());
        assertEquals(1, first.arg1().get("n").toint());
        assertEquals(1, first.arg(2).toint());
        assertEquals(2, second.arg(2).toint());
    }
}
