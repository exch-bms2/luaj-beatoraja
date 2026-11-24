package org.luaj.vm2;

import junit.framework.TestCase;
import org.luaj.vm2.lib.jse.JsePlatform;

public class LuaDoubleFormattingTest extends TestCase {
    private void finiteRoundTrip(double number) {
        LuaValue value = LuaValue.valueOf(number);
        String text = value.tojstring();
        double parsed = Double.parseDouble(text);
        assertTrue("finite value printed as " + text, Double.isFinite(parsed));
        assertEquals(Double.doubleToLongBits(number), Double.doubleToLongBits(parsed));
        assertEquals(LuaValue.TSTRING, value.strvalue().type());
        assertEquals(text, value.strvalue().tojstring());
    }

    public void testLargeFiniteNumbersDoNotBecomeInfinity() {
        for (double number : new double[] {1e40, -1e40, Double.MAX_VALUE, -Double.MAX_VALUE, Math.nextDown(Double.MAX_VALUE)})
            finiteRoundTrip(number);
    }

    public void testFloatOverflowBoundary() {
        double edge = Float.MAX_VALUE;
        for (double number : new double[] {edge, -edge, Math.nextUp(edge), Math.nextDown(edge), -Math.nextUp(edge)})
            finiteRoundTrip(number);
    }

    public void testSmallNonzeroNumbersDoNotBecomeZero() {
        double halfFloatMinimum = ((double) Float.MIN_VALUE) / 2;
        for (double number : new double[] {Double.MIN_VALUE, -Double.MIN_VALUE, Double.MIN_NORMAL, -Double.MIN_NORMAL,
                halfFloatMinimum, -halfFloatMinimum, Math.nextDown(halfFloatMinimum)})
            finiteRoundTrip(number);
    }

    public void testLongRangeBoundariesDoNotSaturate() {
        for (double number : new double[] {0x1p63, Math.nextDown(0x1p63), Math.nextUp(0x1p63), -0x1p63,
                Math.nextDown(-0x1p63), Math.nextUp(-0x1p63)})
            finiteRoundTrip(number);
        assertEquals("9.223372036854776E18", LuaValue.valueOf(0x1p63).tojstring());
        assertEquals("-9223372036854775808", LuaValue.valueOf(-0x1p63).tojstring());
    }

    public void testOrdinaryFormattingCompatibility() {
        assertEquals("0", LuaValue.valueOf(-0.0).tojstring());
        assertEquals("2147483648", LuaValue.valueOf(2147483648.0).tojstring());
        assertEquals("1.25", LuaValue.valueOf(1.25).tojstring());
        assertEquals("-1.25", LuaValue.valueOf(-1.25).tojstring());
        assertEquals("3.1415927", LuaValue.valueOf(Math.PI).tojstring());
    }

    public void testActualInfinityAndNaNTokensAreUnchanged() {
        assertEquals("inf", LuaValue.valueOf(Double.POSITIVE_INFINITY).tojstring());
        assertEquals("-inf", LuaValue.valueOf(Double.NEGATIVE_INFINITY).tojstring());
        assertEquals("nan", LuaValue.valueOf(Double.NaN).tojstring());
    }

    public void testLuaTostringAndTonumberPreserveExtremeValues() {
        Varargs result = JsePlatform.standardGlobals().load(
                "local a,b=1e40,5e-324; return type(tostring(a)),tonumber(tostring(a))==a,tonumber(tostring(b))==b").invoke();
        assertEquals("string", result.arg1().tojstring());
        assertTrue(result.arg(2).toboolean());
        assertTrue(result.arg(3).toboolean());
    }

    public void testFibonacciValueIsFiniteInText() {
        LuaValue value = JsePlatform.standardGlobals().load(
                "local a,b=1,1; for i=3,199 do a,b=b,a+b end; return b").call();
        assertEquals(LuaValue.TNUMBER, value.type());
        assertTrue(Double.isFinite(value.todouble()));
        finiteRoundTrip(value.todouble());
    }

    public void testLuaConcatenationUsesFiniteString() {
        LuaValue value = JsePlatform.standardGlobals().load("return ''..1e40").call();
        assertEquals(LuaValue.TSTRING, value.type());
        assertEquals(1e40, Double.parseDouble(value.tojstring()), 0.0);
    }
}
