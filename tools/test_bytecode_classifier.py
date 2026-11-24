import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('classifier', pathlib.Path(__file__).with_name('classify-bytecode.py'))
classifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classifier)

def item(code): return {'body':code.splitlines(), 'declaration':'public void f();'}

class BytecodeClassificationTest(unittest.TestCase):
    def test_pool_indices_and_branch_offsets_are_not_behavior_changes(self):
        a = item('0: aload_0\n1: ifnull 10\n4: ldc #3 // String x\n6: areturn\n10: aconst_null\n11: areturn')
        b = item('0: aload_0\n1: ifnull 12\n4: ldc_w #300 // String x\n8: areturn\n12: aconst_null\n13: areturn')
        self.assertEqual(classifier.normalize(a), classifier.normalize(b))

    def test_branch_target_change_is_preserved(self):
        a = item('0: aload_0\n1: ifnull 6\n4: aconst_null\n5: areturn\n6: aload_0\n7: areturn')
        b = item('\n'.join(a['body']).replace('ifnull 6','ifnull 4'))
        self.assertNotEqual(classifier.normalize(a), classifier.normalize(b))

    def test_symbolic_constant_change_is_preserved(self):
        self.assertNotEqual(classifier.normalize(item('0: ldc #1 // String x\n2: areturn')),
                            classifier.normalize(item('0: ldc #1 // String y\n2: areturn')))

    def test_duplicate_cast_is_explicit_separate_classification(self):
        a = item('0: aload_0\n1: checkcast #1 // class X\n4: checkcast #1 // class X\n7: areturn')
        b = item('0: aload_0\n1: checkcast #1 // class X\n4: areturn')
        self.assertNotEqual(classifier.normalize(a), classifier.normalize(b))
        self.assertEqual(classifier.normalize(a, True), classifier.normalize(b, True))

    def test_exception_type_change_is_preserved(self):
        code = '0: aload_0\n1: areturn\n2: athrow\nException table:\n0 2 2 Class java/lang/Exception'
        self.assertNotEqual(classifier.normalize(item(code)), classifier.normalize(item(code.replace('Exception','Throwable'))))

    def test_constant_parenthesis_is_not_parsed_as_method(self):
        text = '  private static final java.lang.String version = "Copyright (C)";\n    descriptor: Ljava/lang/String;'
        self.assertIn('version:Ljava/lang/String;', classifier.members(text))

    def test_unresolved_branch_target_fails_closed(self):
        with self.assertRaises(ValueError): classifier.normalize(item('0: goto 99\n3: return'))

if __name__ == '__main__': unittest.main()
