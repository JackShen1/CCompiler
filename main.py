"""Main executable for JackShenC compiler. For usage, run "./main.py --help"."""

import argparse
import subprocess
import sys

from errors import error_collector, CompilerError
from asm_gen import ASMCode, MASMCode, ASMGen
from il_gen import ILCode, SymbolTable
from myparser import Parser
from lexer import Lexer


def main():
    """Run the main compiler script."""
    # Each of these functions should add any issues to the global error_collector -- NOT raise them. After each stage of
    # the compiler, compilation only proceeds if no errors were found.

    arguments = get_arguments()

    code_lines = get_code_lines(arguments)
    if not error_collector.ok():
        error_collector.show()
        return 1

    token_list = Lexer().tokenize(code_lines)
    if not error_collector.ok():
        error_collector.show()
        return 1

    ast_root = Parser(token_list).parse()
    if not error_collector.ok():
        error_collector.show()
        return 1

    il_code = ILCode()
    ast_root.make_code(il_code, SymbolTable())
    if not error_collector.ok():
        error_collector.show()
        return 1

    asm_code, masm_code = ASMCode(), MASMCode()
    ASMGen(il_code, asm_code, masm_code).make_asm()
    ASMGen(il_code, asm_code, masm_code).make_masm()
    asm_source, masm_source = asm_code.full_code(), masm_code.full_code()
    if not error_collector.ok():
        error_collector.show()
        return 1

    asm_filename = "out.s"
    write_asm(asm_source, asm_filename)
    if not error_collector.ok():
        error_collector.show()
        return 1

    masm_filename = "masm.asm"
    write_asm(masm_source, masm_filename)
    if not error_collector.ok():
        error_collector.show()
        return 1

    assemble_and_link("out", asm_filename, "out.o")
    if not error_collector.ok():
        error_collector.show()
        return 1

    return 0


def get_arguments():
    """Get the command-line arguments. This function sets up the argument parser and returns an object storing the
    argument values (as returned by argparse.parse_args()).
    """
    parser = argparse.ArgumentParser(description="Compile C files.")

    # The file name of the C file to compile. The file name gets saved to the file_name attribute of the returned object
    # but this parameter appears as "filename" (no underscore) on the command line.
    parser.add_argument("file_name", metavar="filename")
    return parser.parse_args()


def get_code_lines(arguments):
    """Open the file(s) in arguments and return lines of code."""
    try:
        with open(arguments.file_name) as c_file:
            return [(line_text.strip(), arguments.file_name, line_num + 1) for line_num, line_text in enumerate(c_file)]
    except IOError:
        descr = "could not read file: '{}'"
        error_collector.add(CompilerError(descr.format(arguments.file_name)))


def write_asm(asm_source, asm_filename):
    """Save the given assembly source to disk at asm_filename.
        asm_source (str) - Full assembly source code.
        asm_filename (str) - Filename to which to save the generated assembly.
    """
    try:
        with open(asm_filename, "w") as s_file:
            s_file.write(asm_source)
    except IOError:
        descr = "could not write output file '{}'"
        error_collector.add(CompilerError(descr.format(asm_filename)))


def assemble_and_link(binary_name, asm_name, obj_name):
    """Assmble and link the assembly file into an object file and binary. If the assembly/linking fails, raise exception
        binary_name (str) - Name of the binary file to output.
        asm_name (str) - Name of the assembly file to read in.
        obj_name (str) - Name of the obj file to output.
    """
    subprocess.check_call(["nasm", "-f", "elf64", "-o", obj_name, asm_name])
    subprocess.check_call(["ld", "-dynamic-linker", "/lib64/ld-linux-x86-64.so.2",
                           "/usr/lib/x86_64-linux-gnu/crt1.o", "/usr/lib/x86_64-linux-gnu/crti.o",
                           "-lc", obj_name, "/usr/lib/x86_64-linux-gnu/crtn.o", "-o", binary_name])


if __name__ == "__main__":
    sys.exit(main())
