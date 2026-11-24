package org.luaj.vm2;

import java.lang.reflect.Field;
import java.util.Collection;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import junit.framework.TestCase;
import org.luaj.vm2.lib.ZeroArgFunction;
import org.luaj.vm2.lib.jse.JsePlatform;

/** Semantic and retention checks shared by all measured pool implementations. */
public class SingleCallPoolRegressionTest extends TestCase {
    private void idle(LuaClosure f) throws Exception {
        Field field=LuaClosure.class.getDeclaredField("freeStacks"); field.setAccessible(true);
        Collection<?> arrays=(Collection<?>)field.get(f);
        assertNotNull(arrays); assertTrue(arrays.size()<=20);
        int slots=0;
        for(Object item:arrays) {
            LuaValue[] stack=(LuaValue[])item; slots+=stack.length;
            for(LuaValue value:stack) assertNull(value);
        }
        assertTrue(slots<=1024);
    }
    public void testConcurrentBorrowAndReleaseNeverShareLiveStack() throws Exception {
        final CyclicBarrier barrier=new CyclicBarrier(20);
        LuaTable env=new LuaTable();
        env.set("hold",new ZeroArgFunction() {
            public LuaValue call() {
                try { barrier.await(5,TimeUnit.SECONDS); return LuaValue.NIL; }
                catch(Exception e) { throw new LuaError(e); }
            }
        });
        Prototype p=JsePlatform.standardGlobals().load("return function(x) local y=x; hold(); return x+y end").call().checkclosure().p;
        // No shared Globals/LuaThread state: this tests closure stack handoff only.
        final LuaClosure f=new LuaClosure(p,env);
        ExecutorService executor=Executors.newFixedThreadPool(20);
        try {
            List<Callable<Void>> jobs=new ArrayList<Callable<Void>>();
            for(int i=1;i<=20;i++) {
                final int id=i;
                jobs.add(new Callable<Void>() { public Void call() {
                    for(int n=0;n<40;n++) assertEquals(2*id,f.call(LuaValue.valueOf(id)).toint());
                    return null;
                }});
            }
            for(Future<Void> result:executor.invokeAll(jobs,20,TimeUnit.SECONDS)) result.get();
        } finally {
            executor.shutdownNow(); assertTrue(executor.awaitTermination(5,TimeUnit.SECONDS));
        }
        idle(f);
    }
    public void testPrototypeSizeChangesRespectTotalRetentionBudget() throws Exception {
        LuaClosure f=JsePlatform.standardGlobals().load("return function(x) return x end").call().checkclosure();
        for(int size:new int[] {2,200,3,250,10,2}) {
            f.p.maxstacksize=size;
            for(int i=0;i<20;i++) assertEquals(i,f.call(LuaValue.valueOf(i)).toint());
            idle(f);
        }
    }
    public void testMissingParametersRemainNilForEveryCallOverload() throws Exception {
        LuaValue f=JsePlatform.standardGlobals().load("return function(a,b,c,d) assert(d==nil); return a,b,c end").call();
        for(int n=0;n<20;n++) {
            assertTrue(f.call().isnil()); assertEquals(1,f.call(LuaValue.ONE).toint());
            assertEquals(1,f.call(LuaValue.ONE,LuaValue.ONE).toint());
            assertEquals(1,f.call(LuaValue.ONE,LuaValue.ONE,LuaValue.ONE).toint());
            assertTrue(f.call().isnil());
        }
        idle(f.checkclosure());
    }
    public void testRetainedMultipleResultsAndExceptionsAcrossReuse() throws Exception {
        LuaClosure f=JsePlatform.standardGlobals().load("return function(x) if x==nil then error('expected') end; return x,x+1,x+2,x+3 end").call().checkclosure();
        Varargs first=f.invoke(LuaValue.ONE);
        for(int i=0;i<20;i++) {
            try { f.call(); fail("expected error"); } catch(LuaError expected) { }
            f.call(LuaValue.valueOf(10));
        }
        assertEquals(4,first.narg()); assertEquals(1,first.arg1().toint()); assertEquals(4,first.arg(4).toint());
        idle(f);
    }
}
