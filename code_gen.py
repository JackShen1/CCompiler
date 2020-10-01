"""Defines the classes necessary for the code generation step of the compiler."""


class CodeStore:
    """Stores the asm code being generated. The implementation of this class is currently very naive.

    lines (List[Tuple, String]) - A list of the lines of code stored.

    Commands are stored as tuples and labels are stored as strings without the terminating colon.
    """
    def __init__(self):
        self.lines = []

    def add_command(self, command):
        """Add a command to the code at current position

        command (tuple) - The command to add, split by spaces across a tuple; e.g. ("mov", "rax", "rbx")
        """
        if not isinstance(command, tuple):
            raise ValueError("Command is not a tuple")
        self.lines.append(command)

    def add_label(self, label):
        """Add a label to the code at current position

        label (str) - The label name, without a colon
        """
        if not isinstance(label, str):
            raise ValueError("Label is not a string")
        self.lines.append(label)

    def full_code(self):
        """Return as a string the full assembly code generated."""
        def to_string(line):
            """Convert a single line from the `lines` variable into a string of nasm code"""
            if isinstance(line, str):
                # It's a label
                return line + ":"
            else:
                # It's a command
                return "     " + line[0] + (" " + ", ".join(line[1:]) if len(line) > 1 else "")

        # This code starts every nasm program, so we put it here.
        header = ["global _start",
                  "",
                  "_start:",
                  "     call main",
                  "     mov rdi, rax",
                  "     mov rax, 60",
                  "     syscall"]
        return "\n".join(header + [to_string(line) for line in self.lines])
