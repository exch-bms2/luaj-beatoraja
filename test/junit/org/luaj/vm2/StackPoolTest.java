package org.luaj.vm2;

import java.lang.reflect.Field;
import java.util.Collection;
import junit.framework.TestCase;
import org.luaj.vm2.lib.jse.JsePlatform;
import org.luaj.vm2.lib.TwoArgFunction;

/** Retention invariants of idle stacks, separate from cross-jar semantic tests. */
public class StackPoolTest extends TestCase {
    private void assertIdleStacks(LuaClosure f) throws Exception {
        Field field = LuaClosure.class.getDeclaredField("freeStacks");
        field.setAccessible(true);
        Collection<?> idle = (Collection<?>) field.get(f);
        assertNotNull(idle);
        assertFalse(idle.isEmpty());
        assertTrue(idle.size() <= 20);
        int slots = 0;
        for (Object item : idle) {
            LuaValue[] stack = (LuaValue[]) item;
            slots += stack.length;
            for (LuaValue value : stack)
                assertNull("idle stack must not retain Lua objects", value);
        }
        assertTrue("per-closure slot budget", slots <= 1024);
    }

    public void testRecursiveStacksRespectSlotBudget() throws Exception {
        LuaClosure f = JsePlatform.standardGlobals().load(
                "local function f(n) if n==0 then return 0 end return f(n-1)+1 end return f")
                .call().checkclosure();
        f.p.maxstacksize = 200;
        assertEquals(100, f.call(LuaValue.valueOf(100)).toint());
        assertIdleStacks(f);
    }

    public void testExceptionClearsIdleReferences() throws Exception {
        LuaClosure f = JsePlatform.standardGlobals().load(
                "return function(x) local t={x}; error('expected') end").call().checkclosure();
        for (int i = 0; i < 20; i++) {
            try {
                f.call(new LuaTable());
                fail("exception expected");
            } catch (LuaError expected) { }
            assertIdleStacks(f);
        }
    }

    public void testCallHookExceptionUnwindsDebugFrame() throws Exception {
        Globals g = JsePlatform.debugGlobals();
        LuaClosure f = g.load("return function(x) return x end").call().checkclosure();
        g.running.state.hookfunc = new TwoArgFunction() {
            public LuaValue call(LuaValue event, LuaValue line) {
                throw new LuaError("expected hook failure");
            }
        };
        g.running.state.hookcall = true;
        try {
            f.call(new LuaTable());
            fail("hook exception expected");
        } catch (LuaError expected) {
        } finally {
            g.running.state.hookfunc = null;
            g.running.state.hookcall = false;
        }
        assertNull("no frame may retain a released stack", g.debuglib.getCallFrame(1));
        assertIdleStacks(f);
        assertEquals(42, f.call(LuaValue.valueOf(42)).toint());
    }
}
