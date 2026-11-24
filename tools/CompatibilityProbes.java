import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.luaj.vm2.*;
import org.luaj.vm2.lib.jse.JsePlatform;

/** Diagnostic observations, deliberately not assertions blessing known defects. */
public final class CompatibilityProbes {
    public static void main(String[] args) throws Exception { run(Paths.get(args[0])); }
    public static void run(Path output) throws Exception {
        List<String> lines = new ArrayList<>();
        Globals g = JsePlatform.debugGlobals();
        LuaTable weak = new LuaTable();
        weak.setmetatable(LuaValue.tableOf(new LuaValue[] {LuaValue.MODE, LuaValue.valueOf("v")}));
        int lost = 0, inserted = 0, capacity = 0;
        java.lang.reflect.Field array = LuaTable.class.getDeclaredField("array");
        array.setAccessible(true);
        for (int i = 1; i <= 32 && lost == 0; i++) {
            weak.set(i, LuaValue.valueOf("value-" + i));
            for (int j = 1; j <= i; j++) if (weak.get(j).isnil()) {
                lost = j; inserted = i; capacity = ((LuaValue[]) array.get(weak)).length; break;
            }
        }
        lines.add("weak_integer_loss\tlost_key=" + lost + ",after_insert=" + inserted + ",array_capacity=" + capacity);
        LuaValue large = LuaValue.valueOf(1e40);
        lines.add("finite_number_display\tfinite=" + Double.isFinite(large.todouble()) + ",text=" + large.tojstring());
        observe(lines, g, "fmod_zero", "return pcall(math.fmod,2,0)");
        observe(lines, g, "modf_numeric_string", "local a,b=math.modf('0'); return type(a),type(b)");
        observe(lines, g, "max_numeric_strings", "return pcall(math.max,4,'8')");
        observe(lines, g, "load_empty_reader", "local n=0; local parts={'return 1','',' + 2'}; local f=assert(load(function() n=n+1; return parts[n] end)); return n,f()");
        observe(lines, g, "nested_pcall_handler", "local n=0; local ok=xpcall(function() pcall(function() error('x') end) end, function(x) n=n+1; return x end); return ok,n");
        observe(lines, g, "yield_through_pcall", "local c=coroutine.create(function() return pcall(function() coroutine.yield(7); return 8 end) end); local a,b=coroutine.resume(c); local d,e,f=coroutine.resume(c); return a,b,d,e,f");
        observe(lines, g, "out_of_bounds_insert", "return pcall(table.insert,{},10,'x')");
        observe(lines, g, "getlocal_function", "return pcall(debug.getlocal,function(x) return x end,1)");
        observe(lines, g, "binary_quoted_bytes", "local s=string.format('%q',string.char(222,32,223,32,224,32)); local t={}; for i=1,#s do t[i]=string.byte(s,i) end; return table.concat(t,',')");
        Files.write(output.resolve("probes.tsv"), lines, StandardCharsets.UTF_8);
    }
    private static void observe(List<String> lines, Globals g, String name, String script) {
        try {
            Varargs values = g.load(script, "audit-probe").invoke();
            List<String> result = new ArrayList<>();
            for (int i = 1; i <= values.narg(); i++) result.add(values.arg(i).typename() + ":" + values.arg(i).tojstring());
            lines.add(name + "\t" + String.join("|", result));
        } catch (Throwable error) {
            lines.add(name + "\t" + error.getClass().getName() + ":" + error.getMessage().replace('\n', ' '));
        }
    }
}
