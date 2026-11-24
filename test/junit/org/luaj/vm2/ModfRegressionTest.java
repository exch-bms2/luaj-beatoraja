package org.luaj.vm2;

import junit.framework.TestCase;
import org.luaj.vm2.lib.jse.JsePlatform;

public class ModfRegressionTest extends TestCase {
    private LuaValue modf;

    protected void setUp() {
        modf = JsePlatform.standardGlobals().get("math").get("modf");
    }

    private void parts(LuaValue input, double integral, double fractional) {
        Varargs result = modf.invoke(input);
        assertEquals(2, result.narg());
        for (int n = 1; n <= 2; n++) assertEquals("return type " + n, LuaValue.TNUMBER, result.arg(n).type());
        number(integral, result.arg1());
        number(fractional, result.arg(2));
    }

    private void number(double expected, LuaValue actual) {
        if (Double.isNaN(expected)) assertTrue(Double.isNaN(actual.todouble()));
        else assertEquals(expected, actual.todouble(), 0.0);
    }

    public void testIntegralNumericStringsReturnTwoNumbers() {
        parts(LuaValue.valueOf("0"), 0, 0);
        parts(LuaValue.valueOf("2"), 2, 0);
        parts(LuaValue.valueOf("-2"), -2, 0);
        parts(LuaValue.valueOf("  2048  "), 2048, 0);
        parts(LuaValue.valueOf("1e12"), 1e12, 0);
    }

    public void testFractionsTruncateTowardZero() {
        parts(LuaValue.valueOf(2.75), 2, 0.75);
        parts(LuaValue.valueOf(-2.75), -2, -0.75);
        parts(LuaValue.valueOf("2.75"), 2, 0.75);
        parts(LuaValue.valueOf("-2.75"), -2, -0.75);
    }

    public void testExistingNumbersAndLargeIntegralDoubles() {
        parts(LuaValue.ZERO, 0, 0);
        parts(LuaValue.valueOf(Integer.MIN_VALUE), Integer.MIN_VALUE, 0);
        parts(LuaValue.valueOf(0x1p63), 0x1p63, 0);
        parts(LuaValue.valueOf(-0x1p63), -0x1p63, 0);
    }

    public void testInfinitiesAndNaN() {
        parts(LuaValue.valueOf(Double.POSITIVE_INFINITY), Double.POSITIVE_INFINITY, 0);
        parts(LuaValue.valueOf(Double.NEGATIVE_INFINITY), Double.NEGATIVE_INFINITY, 0);
        parts(LuaValue.valueOf(Double.NaN), Double.NaN, Double.NaN);
    }

    public void testInvalidArgumentsStillFail() {
        for (LuaValue bad : new LuaValue[] {LuaValue.NIL, LuaValue.TRUE, LuaValue.valueOf("not a number"), new LuaTable()}) {
            try { modf.invoke(bad); fail("non-number accepted"); } catch (LuaError expected) { }
        }
    }

    public void testRetainedResultsAndLuaTypeChecks() {
        Varargs first = modf.invoke(LuaValue.valueOf("-2"));
        modf.invoke(LuaValue.valueOf(9.75));
        assertEquals(2, first.narg());
        assertEquals(LuaValue.TNUMBER, first.arg1().type());
        assertEquals(-2.0, first.arg1().todouble(), 0.0);
        assertEquals(0.0, first.arg(2).todouble(), 0.0);
        Varargs types = JsePlatform.standardGlobals().load("local a,b=math.modf('0'); return type(a),type(b)").invoke();
        assertEquals("number", types.arg1().tojstring());
        assertEquals("number", types.arg(2).tojstring());
    }
}
