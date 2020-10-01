"""Integration tests for the compiler. Tests the entire pipeline, from
C source to executable.
These tests should focus on verifying that the generated asm code behaves as
expected. If the main test is verifying the lexer/parser steps, put the test in
the corresponding test_* file.
"""

import subprocess
import unittest
import main

from errors import CompilerError


class integration_tests(unittest.TestCase):
    def setUp(self):
        pass

    def test_basic_return_main(self):
        self.expect_return("int main() { return 15; }", 15)

    def test_multiple_return_main(self):
        self.expect_return("int main() { return 15; return 20; return 10; }", 15)

    # Support functions for the the tests
    def compile_and_run(self, code):
        """Compile, assemble, link, and run the provided C code. Raises an
        exception if any of these steps fails; otherwise, returns the return
        code of the executed program.
        """
        asm_code = main.compile_code([(code, "file_name.c", 7)])
        with open("temp/out.s", "w") as asm_file:
            asm_file.write(asm_code[0])
        main.assemble_and_link("temp/out", "temp/out.s", "temp/temp.o")
        return subprocess.run(["temp/out"]).returncode

    def expect_return(self, code, value):
        self.assertEqual(self.compile_and_run(code), value)

    def expect_exception(self, code, exception, regex):
        with self.assertRaisesRegex(exception, regex):
            self.compile_and_run(code)
