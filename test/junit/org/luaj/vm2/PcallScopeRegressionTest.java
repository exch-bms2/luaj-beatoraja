package org.luaj.vm2;

import java.lang.ref.WeakReference;
import junit.framework.TestCase;
import org.luaj.vm2.lib.OneArgFunction;
import org.luaj.vm2.lib.TwoArgFunction;
import org.luaj.vm2.lib.ZeroArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;

public class PcallScopeRegressionTest extends TestCase {
    private Globals globals;

    protected void setUp() { globals = JsePlatform.debugGlobals(); }

    private Varargs run(String script) {
        Varargs result = globals.load(script, "protected-scope").invoke();
        assertNull("main debug frame leaked", globals.debuglib.getCallFrame(1));
        assertNull("main handler leaked", globals.running.errorfunc);
        return result;
    }

    public void testCaughtInnerErrorDoesNotCallOuterHandler() {
        Varargs result = run("local n=0; local ok,value=xpcall(function() "
                + "local caught,msg=pcall(function() error('inner') end); assert(not caught); "
                + "return 7 end,function(e) n=n+1; return 'outer' end); return ok,value,n");
        assertTrue(result.arg1().toboolean());
        assertEquals(7, result.arg(2).toint());
        assertEquals(0, result.arg(3).toint());
    }

    public void testOuterHandlerRestoredForLaterError() {
        Varargs result = run("local n=0; local ok,msg=xpcall(function() "
                + "assert(not pcall(function() error('caught') end)); error('escaping') end, "
                + "function(e) n=n+1; assert(e:find('escaping',1,true)); return 'handled' end); return ok,msg,n");
        assertFalse(result.arg1().toboolean());
        assertEquals("handled", result.arg(2).tojstring());
        assertEquals(1, result.arg(3).toint());
    }

    public void testNestedXpcallUsesOnlyNearestHandler() {
        Varargs result = run("local outer,inner=0,0; local ok,msg=xpcall(function() "
                + "local ok2,msg2=xpcall(function() "
                + "assert(not pcall(function() error('caught') end)); error('inner escaping') end, "
                + "function(e) inner=inner+1; return 'inner handled' end); "
                + "assert(not ok2 and msg2=='inner handled'); error('outer escaping') end, "
                + "function(e) outer=outer+1; return 'outer handled' end); return ok,msg,outer,inner");
        assertFalse(result.arg1().toboolean());
        assertEquals("outer handled", result.arg(2).tojstring());
        assertEquals(1, result.arg(3).toint());
        assertEquals(1, result.arg(4).toint());
    }

    public void testNestedPcallPreservesErrorObjectAndResults() {
        Varargs result = run("local object={}; local n=0; local ok,a,b,c=xpcall(function() "
                + "local ok2,ok3,value=pcall(function() return pcall(function() error(object) end) end); "
                + "assert(ok2 and not ok3 and rawequal(value,object)); return 1,nil,3 end, "
                + "function(e) n=n+1; return 'unexpected' end); return ok,a,b,c,n");
        assertEquals(5, result.narg());
        assertTrue(result.arg1().toboolean());
        assertEquals(1, result.arg(2).toint());
        assertTrue(result.arg(3).isnil());
        assertEquals(3, result.arg(4).toint());
        assertEquals(0, result.arg(5).toint());
    }

    public void testJavaReentryAndJavaExceptionRemainProtected() {
        globals.set("inner", globals.load("return function() error('Java reentry') end").call());
        globals.set("reenter", new ZeroArgFunction() {
            public LuaValue call() { return globals.get("inner").call(); }
        });
        globals.set("javaFailure", new ZeroArgFunction() {
            public LuaValue call() { throw new IllegalStateException("Java exception"); }
        });
        Varargs result = run("local n=0; local ok,msg=xpcall(function() "
                + "assert(not pcall(reenter)); assert(not pcall(javaFailure)); error('escaping') end, "
                + "function(e) n=n+1; return 'handled' end); return ok,msg,n");
        assertFalse(result.arg1().toboolean());
        assertEquals("handled", result.arg(2).tojstring());
        assertEquals(1, result.arg(3).toint());
    }

    public void testJavaHandlerFieldRestoredAfterSuccessAndFailure() {
        final int[] calls = {0};
        LuaValue handler = new OneArgFunction() {
            public LuaValue call(LuaValue error) { calls[0]++; return LuaValue.valueOf("handled"); }
        };
        LuaValue bad = globals.load("return function() error('caught') end").call();
        LuaValue good = globals.load("return function() return 7 end").call();
        LuaThread thread = globals.running;
        thread.errorfunc = handler;
        try {
            assertFalse(globals.get("pcall").invoke(bad).arg1().toboolean());
            assertSame(handler, thread.errorfunc);
            assertTrue(globals.get("pcall").invoke(good).arg1().toboolean());
            assertSame(handler, thread.errorfunc);
            assertEquals(0, calls[0]);
        } finally { thread.errorfunc = null; }
    }

    public void testFailingHandlerDoesNotInvokeEnclosingHandler() {
        Varargs result = run("local outer,inner=0,0; local ok=xpcall(function() "
                + "local ok2,msg=pcall(function() return xpcall(function() "
                + "assert(not pcall(function() error('caught') end)); error('escaping') end, "
                + "function(e) inner=inner+1; error('handler failure') end) end); "
                + "assert(ok2 and msg==false); return 7 end, "
                + "function(e) outer=outer+1; return 'unexpected' end); return ok,outer,inner");
        assertTrue(result.arg1().toboolean());
        assertEquals(0, result.arg(2).toint());
        assertEquals(1, result.arg(3).toint());
    }

    public void testYieldResumePreservesHandlerScopesAcrossThreads() {
        Varargs result = run("local main,coCalls=0,0; local co=coroutine.create(function() "
                + "return xpcall(function() local ok=pcall(function() coroutine.yield('paused'); "
                + "error('caught') end); assert(not ok); error('coroutine escaping') end, "
                + "function(e) coCalls=coCalls+1; return 'co handled' end) end); "
                + "local ok,tag=coroutine.resume(co); assert(ok and tag=='paused'); "
                + "local ok2,msg=xpcall(function() error('main') end,function(e) main=main+1; return 'main handled' end); "
                + "assert(not ok2 and msg=='main handled'); local ok3,ok4,msg2=coroutine.resume(co); "
                + "assert(ok3 and not ok4 and msg2=='co handled'); return main,coCalls,coroutine.status(co)");
        assertEquals(1, result.arg1().toint());
        assertEquals(1, result.arg(2).toint());
        assertEquals("dead", result.arg(3).tojstring());
    }

    public void testYieldFromErrorHandlerAndNestedPcall() {
        Varargs result = run("local n=0; local co=coroutine.create(function() "
                + "return xpcall(function() error('escaping') end,function(e) n=n+1; "
                + "assert(not pcall(function() error('handler caught') end)); "
                + "local reply=coroutine.yield('handling'); return 'handled:'..reply end) end); "
                + "local ok,tag=coroutine.resume(co); assert(ok and tag=='handling'); "
                + "assert(not pcall(function() error('main caught') end)); "
                + "local ok2,ok3,msg=coroutine.resume(co,'reply'); assert(ok2 and not ok3); return msg,n");
        assertEquals("handled:reply", result.arg1().tojstring());
        assertEquals(1, result.arg(2).toint());
    }

    public void testCallHookExceptionRestoresHandlerAndFrame() {
        LuaValue handler = new OneArgFunction() {
            public LuaValue call(LuaValue error) { fail("outer handler called"); return LuaValue.NIL; }
        };
        LuaValue function = globals.load("return function() return 7 end").call();
        globals.running.errorfunc = handler;
        globals.running.state.hookfunc = new TwoArgFunction() {
            public LuaValue call(LuaValue event, LuaValue line) { throw new LuaError("hook failure"); }
        };
        globals.running.state.hookcall = true;
        try {
            Varargs result = globals.get("pcall").invoke(function);
            assertFalse(result.arg1().toboolean());
            assertSame(handler, globals.running.errorfunc);
            assertNull(globals.debuglib.getCallFrame(1));
        } finally {
            globals.running.state.hookcall = false;
            globals.running.state.hookfunc = null;
            globals.running.errorfunc = null;
        }
    }

    public void testReturnHookExceptionStillRestoresHandler() {
        LuaValue handler = new OneArgFunction() {
            public LuaValue call(LuaValue error) { fail("outer handler called"); return LuaValue.NIL; }
        };
        LuaValue function = globals.load("return function() return 7 end").call();
        globals.running.errorfunc = handler;
        globals.running.state.hookfunc = new TwoArgFunction() {
            public LuaValue call(LuaValue event, LuaValue line) {
                if (globals.debuglib.getCallFrame(1) == null) throw new LuaError("return hook failure");
                return LuaValue.NONE;
            }
        };
        globals.running.state.hookrtrn = true;
        try {
            try {
                globals.get("pcall").invoke(function);
                fail("return hook exception expected");
            } catch (LuaError expected) { assertTrue(expected.getMessage().contains("return hook failure")); }
            assertSame(handler, globals.running.errorfunc);
            assertNull(globals.debuglib.getCallFrame(1));
        } finally {
            globals.running.state.hookrtrn = false;
            globals.running.state.hookfunc = null;
            globals.running.errorfunc = null;
        }
    }

    private WeakReference<LuaThread> suspendedProtectedThread() {
        LuaValue function = globals.load("return function() return pcall(function() coroutine.yield(7) end) end").call();
        LuaThread thread = new LuaThread(globals, function);
        Varargs result = thread.resume(LuaValue.NONE);
        assertTrue(result.arg1().toboolean());
        assertEquals(7, result.arg(2).toint());
        return new WeakReference<LuaThread>(thread);
    }

    public void testAbandonedSuspendedPcallThreadCanBeCollected() throws Exception {
        long previous = LuaThread.thread_orphan_check_interval;
        LuaThread.thread_orphan_check_interval = 5;
        try {
            WeakReference<LuaThread> ref = suspendedProtectedThread();
            for (int attempt = 0; attempt < 100 && !ref.refersTo(null); attempt++) {
                System.gc();
                Thread.sleep(10);
            }
            assertNull("pcall restoration retained the suspended LuaThread", ref.get());
        } finally { LuaThread.thread_orphan_check_interval = previous; }
    }
}
