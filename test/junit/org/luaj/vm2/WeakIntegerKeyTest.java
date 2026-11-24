package org.luaj.vm2;

import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import junit.framework.TestCase;
import org.luaj.vm2.lib.ZeroArgFunction;

/** Integer rehashing must preserve both lookups and the metatable's ownership. */
public class WeakIntegerKeyTest extends TestCase {
    private LuaTable table(String mode) {
        LuaTable t = new LuaTable();
        t.setmetatable(LuaValue.tableOf(new LuaValue[] {LuaValue.MODE, LuaValue.valueOf(mode)}));
        return t;
    }

    private void collected(WeakReference<?>... refs) throws InterruptedException {
        for (int attempt = 0; attempt < 100; attempt++) {
            boolean done = true;
            for (WeakReference<?> ref : refs) done &= ref.refersTo(null);
            if (done) return;
            System.gc();
            Thread.sleep(10);
        }
        for (WeakReference<?> ref : refs) assertNull("weak referent retained", ref.get());
    }

    public void testIntegerStringsInBothInsertionOrders() {
        for (String mode : new String[] {"v", "kv"}) {
            for (boolean reverse : new boolean[] {false, true}) {
                LuaTable t = table(mode);
                for (int n = 1; n <= 64; n++) {
                    int key = reverse ? 65 - n : n;
                    t.set(key, LuaValue.valueOf("value-" + key));
                    for (int j = 1; j <= n; j++) {
                        int inserted = reverse ? 65 - j : j;
                        assertEquals("value-" + inserted, t.rawget(inserted).tojstring());
                        assertEquals(t.rawget(inserted), t.rawget(LuaValue.valueOf(inserted)));
                    }
                }
                assertEquals(64, t.keyCount());
                assertEquals(64, t.rawlen());
            }
        }
    }

    public void testHeldValuesSurviveRehashAndGC() throws Exception {
        for (String mode : new String[] {"v", "kv", "k"}) {
            LuaTable t = table(mode);
            LuaValue[] held = new LuaValue[64];
            for (int n = 64; n >= 1; n--) {
                held[n-1] = new LuaTable();
                t.set(n, held[n-1]);
            }
            collected(new WeakReference<Object>(new Object()));
            for (int n = 1; n <= 64; n++) assertSame(held[n-1], t.rawget(n));
            Reference.reachabilityFence(held);
            Reference.reachabilityFence(t);
        }
    }

    private WeakReference<LuaValue> moveHashToArray(LuaTable t) {
        LuaValue value = new LuaTable();
        t.set(64, value);
        assertEquals(0, t.getArrayLength()); // Start on the hash path.
        for (int n = 1; n < 64; n++) t.set(n, LuaValue.valueOf(n));
        assertTrue("must exercise migration to array", t.getArrayLength() >= 64);
        assertSame(value, t.rawget(64));
        return new WeakReference<LuaValue>(value);
    }

    public void testHashToArrayKeepsValuesWeak() throws Exception {
        for (String mode : new String[] {"v", "kv"}) {
            LuaTable t = table(mode);
            WeakReference<LuaValue> ref = moveHashToArray(t);
            collected(ref);
            assertTrue(t.rawget(64).isnil());
            assertEquals(63, t.keyCount());
            Reference.reachabilityFence(t);
        }
    }

    private WeakReference<LuaValue> moveArrayToHash(LuaTable t) {
        for (int n = 1; n <= 32; n++) t.set(n, LuaValue.valueOf(n));
        LuaValue value = new LuaTable();
        t.set(32, value);
        for (int n = 1; n < 32; n++) t.set(n, LuaValue.NIL);
        t.set("rehash", LuaValue.ONE);
        assertEquals("must exercise migration back to hash", 0, t.getArrayLength());
        assertSame(value, t.rawget(32));
        return new WeakReference<LuaValue>(value);
    }

    public void testArrayToHashKeepsValuesWeak() throws Exception {
        for (String mode : new String[] {"v", "kv"}) {
            LuaTable t = table(mode);
            WeakReference<LuaValue> ref = moveArrayToHash(t);
            collected(ref);
            assertTrue(t.rawget(32).isnil());
            Reference.reachabilityFence(t);
        }
    }

    @SuppressWarnings("unchecked")
    private WeakReference<LuaValue>[] mixedValues(LuaTable t) {
        LuaValue[] held = new LuaValue[48];
        WeakReference<LuaValue>[] refs = new WeakReference[held.length];
        for (int n = held.length; n >= 1; n--) {
            switch (n % 3) {
                case 0: held[n-1] = new LuaTable(); break;
                case 1: held[n-1] = LuaValue.userdataOf(new Object()); break;
                default: held[n-1] = new ZeroArgFunction() {
                    public LuaValue call() { return LuaValue.NIL; }
                };
            }
            refs[n-1] = new WeakReference<LuaValue>(held[n-1]);
            t.set(n, held[n-1]);
        }
        for (int n = 1; n <= held.length; n++) assertSame(held[n-1], t.rawget(n));
        Reference.reachabilityFence(held);
        return refs;
    }

    public void testTablesFunctionsAndUserdataAreCollected() throws Exception {
        for (String mode : new String[] {"v", "kv"}) {
            LuaTable t = table(mode);
            collected(mixedValues(t));
            for (int n = 1; n <= 48; n++) assertTrue(t.rawget(n).isnil());
            assertEquals(0, t.keyCount());
            Reference.reachabilityFence(t);
        }
    }

    public void testWeakKeysDoNotWeakenIntegerValues() throws Exception {
        LuaTable t = table("k");
        WeakReference<LuaValue>[] refs = mixedValues(t);
        collected(new WeakReference<Object>(new Object()));
        for (int n = 1; n <= refs.length; n++) {
            assertNotNull(refs[n-1].get());
            assertSame(refs[n-1].get(), t.rawget(n));
        }
        Reference.reachabilityFence(t);
    }

    private WeakReference<LuaValue> nonIntegerKey(LuaTable t) {
        LuaValue key = new LuaTable();
        t.set(key, LuaValue.valueOf("value"));
        return new WeakReference<LuaValue>(key);
    }

    public void testNonIntegerKeysStillUseWeakSlots() throws Exception {
        for (String mode : new String[] {"k", "kv"}) {
            LuaTable t = table(mode);
            collected(nonIntegerKey(t));
            assertEquals(0, t.keyCount());
            Reference.reachabilityFence(t);
        }
    }

    private WeakReference<LuaValue> nonIntegerValue(LuaTable t) {
        LuaValue value = new LuaTable();
        t.set("key", value);
        return new WeakReference<LuaValue>(value);
    }

    public void testNonIntegerValuesStillUseWeakSlots() throws Exception {
        for (String mode : new String[] {"v", "kv"}) {
            LuaTable t = table(mode);
            collected(nonIntegerValue(t));
            assertTrue(t.rawget("key").isnil());
            Reference.reachabilityFence(t);
        }
    }

    public void testRehashAfterHashValueCollection() throws Exception {
        for (String mode : new String[] {"v", "kv"}) {
            LuaTable t = table(mode);
            collected(nonIntegerValue(t));
            t.set(1, LuaValue.ONE);
            t.set(2, LuaValue.valueOf(2));
            assertTrue(t.rawget("key").isnil());
            assertEquals(LuaValue.ONE, t.rawget(1));
            assertEquals(LuaValue.valueOf(2), t.rawget(2));
            assertEquals(2, t.keyCount());
            Reference.reachabilityFence(t);
        }
    }

    public void testRehashAfterHashKeyCollection() throws Exception {
        for (String mode : new String[] {"k", "kv"}) {
            LuaTable t = table(mode);
            collected(nonIntegerKey(t));
            t.set(1, LuaValue.ONE);
            t.set(2, LuaValue.valueOf(2));
            assertEquals(LuaValue.ONE, t.rawget(1));
            assertEquals(LuaValue.valueOf(2), t.rawget(2));
            assertEquals(2, t.keyCount());
            Reference.reachabilityFence(t);
        }
    }

    @SuppressWarnings("unchecked")
    private WeakReference<LuaValue>[] scalarValues(LuaTable t) {
        LuaValue[] values = {LuaValue.valueOf("x".repeat(2048)), LuaValue.valueOf(1973.125), LuaValue.valueOf(500000)};
        WeakReference<LuaValue>[] refs = new WeakReference[values.length];
        for (int n = 0; n < values.length; n++) {
            t.set(n + 1, values[n]);
            refs[n] = new WeakReference<LuaValue>(values[n]);
        }
        return refs;
    }

    public void testStringsAndNumbersStayStrongAcrossGC() throws Exception {
        for (String mode : new String[] {"v", "kv"}) {
            LuaTable t = table(mode);
            WeakReference<LuaValue>[] refs = scalarValues(t);
            collected(new WeakReference<Object>(new Object()));
            for (int n = 0; n < refs.length; n++) {
                assertNotNull(refs[n].get());
                assertSame(refs[n].get(), t.rawget(n + 1));
            }
            assertEquals(LuaValue.TSTRING, t.rawget(1).type());
            assertEquals(2048, t.rawget(1).rawlen());
            assertEquals(1973.125, t.rawget(2).todouble(), 0.0);
            Reference.reachabilityFence(t);
        }
    }

    private WeakReference<LuaValue> rehashedUserdata(LuaTable t, Object owner) {
        LuaValue value = LuaValue.userdataOf(owner);
        t.set(64, value);
        for (int n = 1; n < 64; n++) t.set(n, LuaValue.valueOf(n));
        assertSame(value, t.rawget(64));
        return new WeakReference<LuaValue>(value);
    }

    public void testUserdataCanBeRecreatedWhileJavaOwnerIsHeld() throws Exception {
        for (String mode : new String[] {"v", "kv"}) {
            LuaTable t = table(mode);
            Object owner = new Object();
            collected(rehashedUserdata(t, owner));
            assertSame(owner, t.rawget(64).checkuserdata());
            Reference.reachabilityFence(owner);
            Reference.reachabilityFence(t);
        }
    }
}
