"""Classes representing IL commands. Each IL command is represented by a class that inherits from the ILCommand
interface. The implementation provides code that generates ASM for each IL command.

For arithmetic commands like Add or Mult, the arguments and output must all be pre-cast to the same type. In addition,
this type must be size `int` or greater per the C spec. The Set command is exempt from this requirement, and can be
used to cast.
"""

import spots
from asm_gen import ASMCode, MASMCode
from spots import Spot
from re import match


class ILCommand:
    """Base interface for all IL commands."""

    def input_values(self):
        """Return list of values read by this command."""
        raise NotImplementedError

    def output_values(self):
        """Return list of values modified by this command."""
        raise NotImplementedError

    def make_asm(self, spotmap, asm_code):
        """Generate assembly code for this command. Generated assembly can read any of the values returned from
        input_values, may overwrite any values returned from output_values.
            asm_code (ASMCode) - Object to which to save generated code.
            spotmap - Dictionary mapping each input/output value to a spot.
        """
        raise NotImplementedError

    def make_masm(self, spotmap, masm_code):
        """Generate assembly code for this command. Generated assembly can read any of the values returned from
        input_values, may overwrite any values returned from output_values.
            asm_code (ASMCode) - Object to which to save generated code.
            spotmap - Dictionary mapping each input/output value to a spot.
        """
        raise NotImplementedError

    def __eq__(self, other):
        """Check equality by comparing types."""
        return type(other) == type(self)

    def assert_same_ctype(self, il_values):
        """Raise ValueError if all IL values do not have the same type."""
        ctype = None
        for il_value in il_values:
            if ctype and ctype != il_value.ctype:
                raise ValueError("different ctypes")


class Add(ILCommand):
    """ADD - adds arg1 and arg2, then saves to output."""

    def __init__(self, output, arg1, arg2):
        self.output = output
        self.arg1 = arg1
        self.arg2 = arg2

        self.assert_same_ctype([output, arg1, arg2])

    def input_values(self): return [self.arg1, self.arg2]

    def output_values(self): return [self.output]

    def make_asm(self, spotmap, asm_code):
        ctype = self.arg1.ctype
        arg1_asm = spotmap[self.arg1].asm_str(ctype.size)
        arg2_asm = spotmap[self.arg2].asm_str(ctype.size)
        output_asm = spotmap[self.output].asm_str(ctype.size)
        rax_asm = spots.RAX.asm_str(ctype.size)

        # We can just use "mov" without sign extending because these will be same size.
        asm_code.add_command("mov", rax_asm, arg1_asm)
        asm_code.add_command("add", rax_asm, arg2_asm)
        asm_code.add_command("mov", output_asm, rax_asm)

    def make_masm(self, spotmap, masm_code):
        ctype = self.arg1.ctype
        arg1_asm = spotmap[self.arg1].masm_str(ctype.size)
        arg2_asm = spotmap[self.arg2].masm_str(ctype.size)
        output_asm = spotmap[self.output].masm_str(ctype.size)
        eax_asm = spots.EAX.masm_str(ctype.size)

        # We can just use "mov" without sign extending because these will be same size.
        masm_code.add_command("mov", eax_asm, arg1_asm)
        masm_code.add_command("add", eax_asm, arg2_asm)
        masm_code.add_command("mov", output_asm, eax_asm)


class Mult(ILCommand):
    """MULT - multiplies arg1 and arg2, then saves to output."""

    def __init__(self, output, arg1, arg2):
        self.output = output
        self.arg1 = arg1
        self.arg2 = arg2

        self.assert_same_ctype([output, arg1, arg2])

    def input_values(self): return [self.arg1, self.arg2]

    def output_values(self): return [self.output]

    def make_asm(self, spotmap, asm_code):
        ctype = self.arg1.ctype
        arg1_asm = spotmap[self.arg1].asm_str(ctype.size)
        arg2_asm = spotmap[self.arg2].asm_str(ctype.size)
        output_asm = spotmap[self.output].asm_str(ctype.size)
        rax_asm = spots.RAX.asm_str(ctype.size)

        # We can just use "mov" without sign extending because these will be same size.
        asm_code.add_command("mov", rax_asm, arg1_asm)
        asm_code.add_command("imul", rax_asm, arg2_asm)
        asm_code.add_command("mov", output_asm, rax_asm)

    def make_masm(self, spotmap, masm_code):
        ctype = self.arg1.ctype
        arg1_asm = spotmap[self.arg1].masm_str(ctype.size)
        arg2_asm = spotmap[self.arg2].masm_str(ctype.size)
        output_asm = spotmap[self.output].masm_str(ctype.size)
        eax_asm = spots.EAX.masm_str(ctype.size)

        # We can just use "mov" without sign extending because these will be same size.
        masm_code.add_command("mov", eax_asm, arg1_asm)
        masm_code.add_command("imul", eax_asm, arg2_asm)
        masm_code.add_command("mov", output_asm, eax_asm)


class Div(ILCommand):
    """DIV - divides arg1 and arg2, then saves to output."""

    def __init__(self, output, arg1, arg2):
        self.output = output
        self.arg1 = arg1
        self.arg2 = arg2

        self.assert_same_ctype([output, arg1, arg2])

    def input_values(self): return [self.arg1, self.arg2]

    def output_values(self): return [self.output]

    def make_asm(self, spotmap, asm_code):
        ctype = self.arg1.ctype
        arg1_asm = spotmap[self.arg1].asm_str(ctype.size)
        arg2_asm = spotmap[self.arg2].asm_str(ctype.size)
        output_asm = spotmap[self.output].asm_str(ctype.size)
        rax_asm = spots.RAX.asm_str(ctype.size)

        # If the divisor is a literal, we must move it to a register.
        if spotmap[self.arg2].spot_type == Spot.LITERAL:
            arg2_final_asm = spots.RSI.asm_str(ctype.size)
            asm_code.add_command("mov", arg2_final_asm, arg2_asm)
        else:
            arg2_final_asm = arg2_asm

        # When arg1 can be bigger than integer, we need to split it between EAX and EDX.
        asm_code.add_command("mov", rax_asm, arg1_asm)

        asm_code.add_command("cdq")  # sign extend EAX into EDX
        asm_code.add_command("idiv", arg2_final_asm)

        # Output has ctype integer.
        asm_code.add_command("mov", output_asm, rax_asm)

    def make_masm(self, spotmap, masm_code):
        ctype = self.arg1.ctype
        arg1_asm = spotmap[self.arg1].masm_str(ctype.size)
        arg2_asm = spotmap[self.arg2].masm_str(ctype.size)
        output_asm = spotmap[self.output].masm_str(ctype.size)
        eax_asm = spots.EAX.masm_str(ctype.size)

        # If the divisor is a literal, we must move it to a register.
        if spotmap[self.arg2].spot_type == Spot.LITERAL:
            arg2_final_asm = spots.ESI.masm_str(ctype.size)
            masm_code.add_command("mov", arg2_final_asm, arg2_asm)
        else:
            arg2_final_asm = arg2_asm

        # When arg1 can be bigger than integer, we need to split it between EAX and EDX.
        masm_code.add_command("mov", eax_asm, arg1_asm)

        masm_code.add_command("cdq")  # sign extend EAX into EDX
        masm_code.add_command("idiv", arg2_final_asm)

        # Output has ctype integer.
        masm_code.add_command("mov", output_asm, eax_asm)


class Set(ILCommand):
    """SET - sets output IL value to arg IL value."""

    def __init__(self, output, arg):
        self.output = output
        self.arg = arg

    def input_values(self): return [self.arg]

    def output_values(self): return [self.output]

    def make_asm(self, spotmap, asm_code):
        arg_spot = spotmap[self.arg]
        output_spot = spotmap[self.output]

        output_asm = output_spot.asm_str(self.output.ctype.size)

        both_stack = (arg_spot.spot_type == Spot.STACK and output_spot.spot_type == Spot.STACK)

        if both_stack: temp = spots.RAX.asm_str(self.output.ctype.size)
        else: temp = output_asm

        if self.output.ctype.size <= self.arg.ctype.size:
            asm_code.add_command("mov", temp, arg_spot.asm_str(self.output.ctype.size))
        elif self.output.ctype.size > self.arg.ctype.size:
            # self.arg
            mov = "movsx" if self.output.ctype.signed else "movzx"
            asm_code.add_command(mov, temp, arg_spot.asm_str(self.arg.ctype.size))

        if both_stack:
            # We can move because rax_asm has same size as output_asm
            asm_code.add_command("mov", output_asm, temp)

    def make_masm(self, spotmap, masm_code):
        arg_spot = spotmap[self.arg]
        output_spot = spotmap[self.output]

        output_masm = output_spot.masm_str(self.output.ctype.size)

        both_stack = (arg_spot.spot_type == Spot.STACK and output_spot.spot_type == Spot.STACK)

        if both_stack: temp = spots.EAX.masm_str(self.output.ctype.size)
        else: temp = output_masm

        if self.output.ctype.size <= self.arg.ctype.size:
            masm_code.add_command("mov", temp, arg_spot.masm_str(self.output.ctype.size))
        elif self.output.ctype.size > self.arg.ctype.size:
            # self.arg
            mov = "movsx" if self.output.ctype.signed else "movzx"
            masm_code.add_command(mov, temp, arg_spot.masm_str(self.arg.ctype.size))

        if both_stack:
            # We can move because eax_asm has same size as output_masm
            masm_code.add_command("mov", output_masm, temp)


class Return(ILCommand):
    """RETURN - returns the given value from function."""

    def __init__(self, arg):
        self.arg = arg

    def input_values(self): return [self.arg]

    def output_values(self): return []

    def make_asm(self, spotmap, asm_code):
        arg_asm = spotmap[self.arg].asm_str(self.arg.ctype.size)
        rax_asm = spots.RAX.asm_str(self.arg.ctype.size)

        # Check for negative number and add neg command
        if match(r'^-[0-9]+$', arg_asm):
            asm_code.add_command("mov", rax_asm, str(abs(int(arg_asm))))
            asm_code.add_command("neg", rax_asm)
        elif match(r'^-0[bB][01]+$', arg_asm):
            asm_code.add_command("mov", rax_asm, arg_asm[3:]+'B')
            asm_code.add_command("neg", rax_asm)
        else:
            asm_code.add_command("mov", rax_asm, arg_asm)

        asm_code.add_command("mov", "rsp", "rbp")
        asm_code.add_command("pop", "rbp")
        asm_code.add_command("ret")

    def make_masm(self, spotmap, masm_code):
        arg_asm = spotmap[self.arg].masm_str(self.arg.ctype.size)
        eax_asm = spots.EAX.masm_str(self.arg.ctype.size)

        # Check for negative number and add neg command
        if match(r'^-[0-9]+$', arg_asm):
            masm_code.add_command("mov", eax_asm, str(abs(int(arg_asm))))
            masm_code.add_command("neg", eax_asm)
        elif match(r'^-0[bB][01]+$', arg_asm):
            masm_code.add_command("mov", eax_asm, arg_asm[3:]+'B')
            masm_code.add_command("neg", eax_asm)
        else:
            masm_code.add_command("mov", eax_asm, arg_asm)

        masm_code.add_command("mov", "esp", "ebp")
        masm_code.add_command("pop", "ebp")
        masm_code.add_command("ret")


class Label(ILCommand):
    """Label - Analogous to an ASM label."""

    def __init__(self, label):
        """The label argument is an integer identifier unique to this label."""
        self.label = label

    def input_values(self): return []

    def output_values(self): return []

    def make_asm(self, spotmap, asm_code): asm_code.add_label(ASMCode.to_label(self.label))

    def make_masm(self, spotmap, masm_code): masm_code.add_label(MASMCode.to_label(self.label))


class JumpZero(ILCommand):
    """Jumps to a label if given condition is zero."""

    def __init__(self, cond, label):
        self.cond = cond
        self.label = label

    def input_values(self): return [self.cond]

    def output_values(self): return []

    def make_asm(self, spotmap, asm_code):
        cond_asm = spotmap[self.cond].asm_str(self.cond.ctype.size)
        if spotmap[self.cond].spot_type == Spot.LITERAL:
            # Must do manual comparison in this case.
            if cond_asm == "0":
                asm_code.add_command("jmp", ASMCode.to_label(self.label))
        else:
            asm_code.add_command("cmp", cond_asm, "0")
            asm_code.add_command("je", ASMCode.to_label(self.label))

    def make_masm(self, spotmap, masm_code):
        cond_masm = spotmap[self.cond].masm_str(self.cond.ctype.size)
        if spotmap[self.cond].spot_type == Spot.LITERAL:
            # Must do manual comparison in this case.
            if cond_masm == "0":
                masm_code.add_command("jmp", MASMCode.to_label(self.label))
        else:
            masm_code.add_command("cmp", cond_masm, "0")
            masm_code.add_command("je", MASMCode.to_label(self.label))
