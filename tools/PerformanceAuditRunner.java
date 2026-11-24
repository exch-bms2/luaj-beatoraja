/** Exit after the unmodified audit, even when tests leave suspended Lua threads. */
public final class PerformanceAuditRunner {
    public static void main(String[] args) {
        try {
            TestAuditRunner.main(args);
        } catch (Throwable error) {
            error.printStackTrace();
            System.exit(1);
        }
        System.exit(0);
    }
}
