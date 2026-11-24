import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.io.*;
import java.util.*;
import org.junit.runner.*;
import org.junit.runner.notification.Failure;

/** One fixed, deduplicated test inventory against exactly one runtime jar. */
public final class TestAuditRunner {
    public static void main(String[] args) throws Exception {
        Path output = Paths.get(args[1]);
        Files.createDirectories(output);
        System.setProperty("luaj.audit.output", output.resolve("output").toAbsolutePath().toString());
        Class<?> value = Class.forName("org.luaj.vm2.LuaValue");
        Files.write(output.resolve("runtime.log"), Arrays.asList(
            "LuaValue=" + value.getProtectionDomain().getCodeSource().getLocation(),
            "Lua._VERSION=" + Class.forName("org.luaj.vm2.Lua").getField("_VERSION").get(null),
            "java=" + System.getProperty("java.runtime.version"),
            "timezone=" + TimeZone.getDefault().getID(),
            "encoding=" + System.getProperty("file.encoding")), StandardCharsets.UTF_8);
        int failed = 0;
        try (PrintWriter report = new PrintWriter(Files.newBufferedWriter(output.resolve("tests.tsv"), StandardCharsets.UTF_8))) {
            for (String id : Files.readAllLines(Paths.get(args[0]), StandardCharsets.UTF_8)) {
                if (id.isEmpty()) continue;
                String[] parts = id.split("#", 2);
                Result result = new JUnitCore().run(Request.method(Class.forName(parts[0]), parts[1]));
                if (result.getRunCount() != 1 || result.getIgnoreCount() != 0)
                    throw new IllegalStateException("Inventory mismatch: " + id + " ran " + result.getRunCount());
                String type = "", message = "";
                if (!result.wasSuccessful()) {
                    failed++;
                    Failure failure = result.getFailures().get(0);
                    type = failure.getException().getClass().getName();
                    message = failure.getTrace();
                }
                report.println(id + "\t" + (result.wasSuccessful()? "pass": "fail") + "\t" + type + "\t"
                    + Base64.getEncoder().encodeToString(message.getBytes(StandardCharsets.UTF_8)));
            }
        }
        System.out.println("Audit failures: " + failed + " (recorded; not ignored by the regression gate)");
        CompatibilityProbes.run(output);
    }
}
