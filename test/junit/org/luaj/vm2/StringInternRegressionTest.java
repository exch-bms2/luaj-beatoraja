package org.luaj.vm2;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotSame;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

import java.lang.ref.WeakReference;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReferenceArray;

import org.junit.Test;
import org.luaj.vm2.lib.jse.JsePlatform;

/**
 * Interning lets string-keyed table lookups succeed on reference equality.
 * Lua string semantics (equality by content, GC of unused strings) must not change.
 */
public class StringInternRegressionTest {

	private static LuaString fresh(String s) {
		// A backing array longer than the recent-strings limit always yields a new,
		// uncached instance, so tests control identity and reachability.
		byte[] bytes = LuaString.valueOf(s).m_bytes;
		byte[] buffer = new byte[bytes.length + LuaString.RECENT_STRINGS_MAX_LENGTH + 1];
		System.arraycopy(bytes, 0, buffer, 0, bytes.length);
		return LuaString.valueUsing(buffer, 0, bytes.length);
	}

	@Test
	public void internReturnsOneCanonicalInstancePerContent() {
		LuaString a = fresh("intern-canonical-a");
		LuaString b = fresh("intern-canonical-a");
		assertNotSame(a, b);
		LuaString ca = a.intern();
		assertSame(ca, b.intern());
		assertSame(ca, ca.intern());
		assertTrue(ca.isInterned());
		assertFalse(b.isInterned() && b != ca);
	}

	@Test
	public void equalityStaysByContent() {
		LuaString interned = fresh("intern-eq").intern();
		LuaString plain = fresh("intern-eq");
		LuaString other = fresh("intern-eq-other").intern();
		assertTrue(interned.raweq(plain));
		assertTrue(plain.raweq(interned));
		assertTrue(interned.equals(plain));
		assertEquals(interned.hashCode(), plain.hashCode());
		assertFalse(interned.raweq(other));
		assertFalse(other.raweq(interned));
		// Substrings of a larger buffer compare by bytes, interned or not.
		LuaString sub = fresh("xxintern-eqyy").substring(2, 11);
		assertTrue(sub.raweq(interned));
		assertTrue(interned.raweq(sub));
		assertSame(interned, sub.intern());
	}

	@Test
	public void constantsAcrossChunksAndTableKeysShareInstances() {
		Globals g = JsePlatform.standardGlobals();
		LuaValue table = g.load("return { internFieldName = 1 }").call();
		LuaValue key = g.load("return 'internFieldName'").call();
		LuaValue next = table.next(LuaValue.NIL).arg1();
		assertSame(next, key);
		assertTrue(((LuaString) key).isInterned());
	}

	@Test
	public void javaStringKeysAreInternedAndStillFoundByContent() {
		LuaTable t = new LuaTable();
		// Java APIs such as main_state.set("number", f) share the constants' instance.
		t.set("internJavaKey", LuaValue.valueOf(7));
		LuaValue stored = t.next(LuaValue.NIL).arg1();
		assertTrue(((LuaString) stored).isInterned());
		assertSame(stored, fresh("internJavaKey").intern());
		assertEquals(7, t.get(fresh("internJavaKey")).toint());
		assertEquals(7, t.get("internJavaKey").toint());
		Globals g = JsePlatform.standardGlobals();
		g.set("t", t);
		assertEquals(7, g.load("return t.internJavaKey").call().toint());
		// Overwrite and remove through a different instance with the same bytes.
		t.set(fresh("internJavaKey"), LuaValue.valueOf(8));
		assertEquals(8, t.get("internJavaKey").toint());
		t.set(fresh("internJavaKey"), LuaValue.NIL);
		assertTrue(t.get("internJavaKey").isnil());
		assertTrue(t.next(LuaValue.NIL).arg1().isnil());
	}

	@Test
	public void runtimeKeysAreNotInternedButFoundByConstants() {
		// Interning every new runtime key made never-seen key inserts about 4x slower.
		LuaTable t = new LuaTable();
		LuaString runtimeKey = fresh("internRuntimeKey");
		t.set(runtimeKey, LuaValue.valueOf(3));
		assertSame(runtimeKey, t.next(LuaValue.NIL).arg1());
		assertFalse(runtimeKey.isInterned());
		Globals g = JsePlatform.standardGlobals();
		g.set("t", t);
		assertEquals(3, g.load("return t.internRuntimeKey").call().toint());
		assertEquals(3, g.load("local t = {} t['internRuntime' .. 'Key2'] = 3 return t.internRuntimeKey2").call().toint());
	}

	@Test
	public void luaSemanticsWithDynamicKeys() {
		Globals g = JsePlatform.standardGlobals();
		Varargs v = g.load(
				"local t = {}\n" +
				"for i = 1, 200 do t['k' .. i] = i end\n" +
				"local s = 0\n" +
				"for i = 1, 200 do s = s + t[('xk' .. i .. 'y'):sub(2, -2)] end\n" +
				"local n = 0\n" +
				"for k, v in pairs(t) do n = n + 1; assert(t[k] == v) end\n" +
				"assert(rawequal('ab' .. 'c', 'abc'))\n" +
				"assert(('abc'):upper() == 'ABC')\n" +
				"for i = 1, 200, 2 do t['k' .. i] = nil end\n" +
				"local m = 0\n" +
				"for k in pairs(t) do m = m + 1 end\n" +
				"return s, n, m").invoke();
		assertEquals(20100, v.arg(1).toint());
		assertEquals(200, v.arg(2).toint());
		assertEquals(100, v.arg(3).toint());
	}

	@Test
	public void unreachableInternedStringsAreCollected() throws Exception {
		WeakReference<LuaString> ref = internGarbage();
		for (int i = 0; i < 50 && ref.get() != null; i++) {
			System.gc();
			byte[][] pressure = new byte[64][];
			for (int j = 0; j < pressure.length; j++) pressure[j] = new byte[64 * 1024];
			Thread.sleep(10);
		}
		assertNull("interned string must not be retained by the pool", ref.get());
		// A new instance with the same bytes becomes the canonical one.
		LuaString again = fresh("intern-collectable-string");
		assertSame(again, again.intern());
	}

	private static WeakReference<LuaString> internGarbage() {
		LuaString s = fresh("intern-collectable-string").intern();
		LuaTable t = new LuaTable();
		t.set(s, LuaValue.TRUE);
		return new WeakReference<LuaString>(s);
	}

	@Test
	public void concurrentInternAgreesOnOneInstance() throws Exception {
		final int threads = 16;
		final AtomicReferenceArray<LuaString> results = new AtomicReferenceArray<LuaString>(threads);
		final CountDownLatch start = new CountDownLatch(1);
		Thread[] workers = new Thread[threads];
		for (int i = 0; i < threads; i++) {
			final int index = i;
			workers[i] = new Thread(new Runnable() {
				public void run() {
					try { start.await(); } catch (InterruptedException e) { return; }
					results.set(index, fresh("intern-concurrent").intern());
				}
			});
			workers[i].start();
		}
		start.countDown();
		for (Thread w : workers) w.join();
		for (int i = 1; i < threads; i++) assertSame(results.get(0), results.get(i));
	}
}
