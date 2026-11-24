package org.luaj.vm2;

import junit.framework.TestCase;
import org.luaj.vm2.lib.jse.JsePlatform;

public class FmodRegressionTest extends TestCase {
    private LuaValue fmod;

    protected void setUp() {
        fmod = JsePlatform.standardGlobals().get("math").get("fmod");
    }

    private void remainder(double expected, LuaValue x, LuaValue y) {
        Varargs result = fmod.invoke(LuaValue.varargsOf(x, y));
        assertEquals(1, result.narg());
        assertEquals(LuaValue.TNUMBER, result.arg1().type());
        if (Double.isNaN(expected)) assertTrue(Double.isNaN(result.arg1().todouble()));
        else assertEquals(expected, result.arg1().todouble(), 0.0);
    }

    public void testIntegerAndNumericStringZeroDivisorsReturnNumberNaN() {
        for (LuaValue x : new LuaValue[] {LuaValue.valueOf(2), LuaValue.valueOf(-2), LuaValue.ZERO, LuaValue.valueOf("2")}) {
            for (LuaValue zero : new LuaValue[] {LuaValue.ZERO, LuaValue.valueOf("0"), LuaValue.valueOf("-0.0")})
                remainder(Double.NaN, x, zero);
        }
    }

    public void testFiniteRemaindersTruncateTowardZero() {
        remainder(1, LuaValue.valueOf(7), LuaValue.valueOf(2));
        remainder(-1, LuaValue.valueOf(-7), LuaValue.valueOf(2));
        remainder(1, LuaValue.valueOf(7), LuaValue.valueOf(-2));
        remainder(-1.5, LuaValue.valueOf(-7.5), LuaValue.valueOf(-2));
        remainder(1.5, LuaValue.valueOf("7.5"), LuaValue.valueOf("-2"));
        remainder(0, LuaValue.valueOf(Integer.MIN_VALUE), LuaValue.valueOf(-1));
    }

    public void testIntegralDoubleOutsideSignedLongRange() {
        remainder(2, LuaValue.valueOf(0x1p63), LuaValue.valueOf(3));
        remainder(-2, LuaValue.valueOf(-0x1p63), LuaValue.valueOf(3));
        remainder(1, LuaValue.valueOf(0x1p64), LuaValue.valueOf(3));
    }

    public void testInfinitiesAndNaN() {
        remainder(Double.NaN, LuaValue.valueOf(Double.POSITIVE_INFINITY), LuaValue.ONE);
        remainder(Double.NaN, LuaValue.valueOf(Double.NEGATIVE_INFINITY), LuaValue.ONE);
        remainder(3.5, LuaValue.valueOf(3.5), LuaValue.valueOf(Double.POSITIVE_INFINITY));
        remainder(Double.NaN, LuaValue.valueOf(Double.NaN), LuaValue.ONE);
        remainder(Double.NaN, LuaValue.ONE, LuaValue.valueOf(Double.NaN));
    }

    public void testInvalidArgumentsStillFail() {
        for (LuaValue bad : new LuaValue[] {LuaValue.NIL, LuaValue.TRUE, LuaValue.valueOf("not a number"), new LuaTable()}) {
            try { fmod.call(bad, LuaValue.ONE); fail("invalid dividend accepted"); } catch (LuaError expected) { }
            try { fmod.call(LuaValue.ONE, bad); fail("invalid divisor accepted"); } catch (LuaError expected) { }
        }
    }
}
