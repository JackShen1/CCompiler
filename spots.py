"""The Spot object definition and and some predefined spots, like registers."""


class Spot:
    """Spot in the machine where an IL value can be.
        spot_type (enum) - One of the values below describing the general type of spot this is.
        detail - Additional information about this spot. The this attribute's type and meaning depend on the spot_type;
        see below for more.
    """

    # Register spot. The `detail` attribute is the full 64-bit register name (rax, rdi, etc.) as a string.
    REGISTER = 1
    # Memory spot, like on the stack or in .data section. The `detail` attribute is a tuple with first argument base as
    # a string, and second argument offset as an integer. For example, ("rbp", -5).
    MEM = 2
    # A literal value. This is a bit of a hack, since a literal value isn't /really/ a storage spot. The detail
    # attribute is the integer representation of the value of this literal.
    LITERAL = 3

    def __init__(self, spot_type, detail):
        """Initialize a spot."""
        self.spot_type = spot_type
        self.detail = detail

    def asm_str(self, size):
        """Make the ASM form of this spot, for the given size in bytes.
        This function raises NotImplementedError for unsupported sizes.
            Examples:
                spots.RAX.asm_str(4) -> "eax"
                spots.RAX.asm_str(8) -> "rax"
                spot(STACK, -16).asm_str(4) -> "DWORD [rbp-16]"
                spot(LITERAL, 14).asm_str(4) -> "14"
            size (int) - Size in bytes of the data stored at this spot.
            return (str) - ASM form of this spot.
        """
        spot_map = {"rax": ["rax", "eax", "ax", "al"],
                    "rbx": ["rbx", "ebx", "bx", "bl"],
                    "rcx": ["rcx", "ecx", "cx", "cl"],
                    "rdx": ["rdx", "edx", "dx", "dl"],
                    "rsi": ["rsi", "esi", "si", "sil"],
                    "rdi": ["rdi", "edi", "di", "dil"],
                    "r8": ["r8", "r8d", "r8w", "r8b"],
                    "r9": ["r9", "r9d", "r9w", "r9b"],
                    "r10": ["r10", "r10d", "r10w", "r10b"],
                    "r11": ["r11", "r11d", "r11w", "r11b"]}

        if self.spot_type == self.REGISTER:
            if size == 1: return spot_map[self.detail][3]
            elif size == 2: return spot_map[self.detail][2]
            elif size == 4: return spot_map[self.detail][1]
            elif size == 8: return spot_map[self.detail][0]
        elif self.spot_type == self.MEM:
            if size == 1: size_desc = "BYTE"
            elif size == 2: size_desc = "WORD"
            elif size == 4: size_desc = "DWORD"
            elif size == 8: size_desc = "QWORD"
            else: size_desc = ""

            if self.detail[1] > 0:
                t = "{} [{}+{}]"
                return t.format(size_desc, self.detail[0], self.detail[1])
            elif self.detail[1] == 0:
                t = "{} [{}]"
                return t.format(size_desc, self.detail[0])
            else:  # self.detail[1] < 0
                t = "{} [{}-{}]"
                return t.format(size_desc, self.detail[0], -self.detail[1])

        elif self.spot_type == self.LITERAL:
            return str(self.detail)

        raise NotImplementedError("Unsupported spot_type/size combo")

    def __repr__(self):
        return self.detail

    def __eq__(self, other):
        """Test equality by comparing type and detail."""
        if not isinstance(other, Spot): return False
        return (self.spot_type, self.detail) == (other.spot_type, other.detail)

    def __hash__(self):
        """Hash based on type and detail."""
        return hash((self.spot_type, self.detail))


RAX = Spot(Spot.REGISTER, "rax")
RCX = Spot(Spot.REGISTER, "rcx")
RDX = Spot(Spot.REGISTER, "rdx")
RSI = Spot(Spot.REGISTER, "rsi")
RDI = Spot(Spot.REGISTER, "rdi")
R8 = Spot(Spot.REGISTER, "r8")
R9 = Spot(Spot.REGISTER, "r9")
R10 = Spot(Spot.REGISTER, "r10")
R11 = Spot(Spot.REGISTER, "r11")

registers = [RAX, RCX, RDX, RSI, RDI, R8, R9, R10, R11]
