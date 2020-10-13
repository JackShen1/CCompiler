"""Classes for the nodes that form our abstract syntax tree (AST). Each node corresponds to a rule in the C grammar and
has a make_code function that generates code in our three-address IL.
"""
from abc import ABC

import il_commands
import token_kinds
import decl_tree
import ctypes

from il_gen import ILValue, LValue, check_cast, set_type
from errors import CompilerError, error_collector
from ctypes import PointerCType, ArrayCType
from tokens import Token
from re import match


class Node:
    """General class for representing a single node in the AST.

    Inherit all AST nodes from this class. Every AST node also has a make_code function that accepts a il_code (ILCode)
    to which the generated IL code should be saved.
        symbol (enum) - Non-terminal symbol the rule corresponding to a node produces. This value is checked by parent
        nodes to make sure the children produce symbols of the expected type.
    """

    # Enum for symbols produced by a node
    ROOT = 0
    MAIN_FUNCTION = 1
    STATEMENT = 2
    DECLARATION = 3
    EXPRESSION = 4

    bin_match = False

    def __eq__(self, other):
        """Check whether all children of this node are equal."""
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return False

    @staticmethod
    def assert_symbol(node, symbol_name):
        """Check whether the provided node is of the given symbol. Useful for enforcing tree structure. Raises an
        exception if the node represents a rule that does not produce the expected symbol.
        """
        if node.symbol != symbol_name:
            raise ValueError("malformed tree: expected symbol '" + str(symbol_name) + "' but got '" +
                             str(node.symbol) + "'")

    @staticmethod
    def assert_symbols(node, symbol_names):
        """Check whether the provided node is one of the given symbols. Useful for enforcing tree structure. Raises an
        exception if the node represents a rule that produces none of the symbols in symbol_names.
        """
        if node.symbol not in symbol_names:
            raise ValueError("malformed tree: unexpected symbol '" + str(node.symbol) + "'")

    @staticmethod
    def assert_kind(token, kind):
        """Check whether the provided token is of the given token kind. Useful for enforcing tree structure. Raises an
        exception if the token does not have the given kind.
        """
        if token.kind != kind:
            raise ValueError("malformed tree: expected token_kind '" + str(kind) + "' but got '" +
                             str(token.kind) + "'")

    def make_code(self, il_code, symbol_table):
        """Make code for this node. Add IL code for this node to the given il_code object."""
        raise NotImplementedError

    def make_code_global(self, il_code, symbol_table):
        """Make code for this node when it is used at global scope. By default, this function just calls make_code.
        However, because global declarations behave differently than local declarations, declaration nodes have override
        the implementation of make_code_global.
        """
        return self.make_code(il_code, symbol_table)


class ExpressionNode(Node):
    """General class for representing an expression node in the AST. Subclasses should implement the make_code_raw
    function.
    """

    symbol = Node.EXPRESSION

    def make_code(self, il_code, symbol_table):
        """Make code for this node and return decayed version of result."""

        lvalue = self.lvalue(il_code, symbol_table)
        if lvalue and lvalue.ctype().is_array():
            addr = lvalue.addr(il_code)
            return set_type(addr, PointerCType(lvalue.ctype().elem), il_code)
        else:
            return self.make_code_raw(il_code, symbol_table)

    def lvalue(self, il_code, symbol_table):
        """Return an LValue object corresponding to this, or None."""
        return None

    def make_code_raw(self, il_code, symbol_table):
        """Generate code for the given node. Return the undecayed result. That is, do not decay function or array types
        into their pointer equivalents. Note that because the expr_ctype function inserts a dummy ILCode object, this
        function should generally not reference any information stored in the ILCode object when generating code.
        """
        raise NotImplementedError


class RootNode(Node):
    """General rule for the root node of the entire compilation unit.
        nodes (List(Node)) - list of nodes for which to make code
    """

    symbol = Node.ROOT

    def __init__(self, nodes):
        """Initialize node."""
        super().__init__()

        self.nodes = nodes

    def __repr__(self):
        return str(self.nodes)

    def make_code(self, il_code, symbol_table):
        """Make code for the root."""
        for node in self.nodes:
            try:
                node.make_code_global(il_code, symbol_table)
            except CompilerError as e:
                error_collector.add(e)


class MainNode(Node):
    """General rule for the main function. This node will be removed once function definition is supported.
        block_items (List[statement, declaration]) - List of the statements and declarations in the main function.
    """

    symbol = Node.MAIN_FUNCTION

    def __init__(self, body):
        """Initialize node."""
        super().__init__()

        # Specifically, we expect 'body' to be a compound statement.
        self.assert_symbol(body, Node.STATEMENT)

        self.body = body

    def __repr__(self):
        return 'AST -> Main Function {{\n{}\n}}'.format(self.body)

    def make_code(self, il_code, symbol_table):
        """Make IL code for the function body. At the end, this function adds code for an artificial return call for if
        the provided function body completes without returning.
        """
        self.body.make_code(il_code, symbol_table)

        return_node = ReturnNode(NumberNode(Token(token_kinds.number, "0")), None)
        return_node.make_code(il_code, symbol_table)


class CompoundNode(Node):
    """Rule for a compound node. A compound node is a statement that consists of several statements/declarations
    enclosed in braces.
    """

    symbol = Node.STATEMENT

    def __init__(self, block_items):
        """Initialize node."""
        super().__init__()

        for item in block_items:
            self.assert_symbols(item, [self.STATEMENT, self.DECLARATION])
        self.block_items = block_items

    def __repr__(self):
        return '\tStatements/Declaration: {{{}\n\t}}'.format(" ".join([str(item) for item in self.block_items]))

    def make_code(self, il_code, symbol_table):
        """Make IL code for every block item, in order."""
        symbol_table.new_scope()
        for block_item in self.block_items:
            try:
                block_item.make_code(il_code, symbol_table)
            except CompilerError as e:
                error_collector.add(e)
        symbol_table.end_scope()


class ReturnNode(Node):
    """Rule for the return statement.
        return_value (expression) - Value to return.
    """

    symbol = Node.STATEMENT

    def __init__(self, return_value, return_kw):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(return_value, self.EXPRESSION)

        self.return_value = return_value
        self.return_kw = return_kw

    def __repr__(self):
        return "\n\n\t\t\tReturn value: {}".format(self.return_value)

    def make_code(self, il_code, symbol_table):
        """Make IL code for returning this value."""
        il_value = self.return_value.make_code(il_code, symbol_table)

        check_cast(il_value, ctypes.integer, self.return_kw)
        il_code.add(il_commands.Return(set_type(il_value, ctypes.integer, il_code)))


class NumberNode(ExpressionNode):
    """Expression that is just a single number.
        number (Token(Number)) - Number this expression represents.
    """

    def __init__(self, number):
        """Initialize node."""
        super().__init__()

        self.number = number

    def __repr__(self):
        return str(self.number)

    def make_code_raw(self, il_code, symbol_table):
        """Make code for a literal number. This function does not actually make any code in the IL, it just returns a
        LiteralILValue that can be used in IL code by the caller.
        """

        if match(r'[01]+B', str(self.number)):
            Node.bin_match = True
            v = int('0b' + str(self.number)[:-1], 2)
        else:
            v = int(str(self.number))

        if ctypes.int_min <= v <= ctypes.int_max:
            il_value = ILValue(ctypes.integer)
        elif ctypes.long_min <= v <= ctypes.long_max:
            il_value = ILValue(ctypes.longint)
        else:
            descr = ("integer literal too large to be represented by any " + "integer type")
            raise CompilerError(descr, self.number.r)

        # if bin_match: il_code.register_literal_var(il_value, str(bin(v))[2:]+'B')
        il_code.register_literal_var(il_value, v)

        # Literal integer 0 is a null pointer constant
        if v == 0:
            il_value.null_ptr_const = True
        return il_value


class StringNode(ExpressionNode):
    """Expression that is a string.
        chars (List(integer)) - String this expression represents, as a null-terminated list of the ASCII
        representations of each character.
    """

    def __init__(self, chars_tok):
        """Initialize node."""
        super().__init__()
        self.chars = chars_tok.content[:]

        # Cache the lvalue.
        self._cache_lvalue = None

    def __repr__(self):
        return str(self.chars)

    def make_code_raw(self, il_code, symbol_table):
        """Make code for a string. This function adds the provided string to the IL data section and returns the ILValue
        representing the string in its array form.
        """
        lvalue = self.lvalue(il_code, symbol_table)
        return lvalue.il_value

    def lvalue(self, il_code, symbol_table):
        """Return LValue form of the string."""

        if not self._cache_lvalue:
            il_value = ILValue(ArrayCType(ctypes.char, len(self.chars)))
            il_code.register_string_literal(il_value, self.chars)
            self._cache_lvalue = LValue(LValue.DIRECT, il_value)

        return self._cache_lvalue


class IdentifierNode(ExpressionNode):
    """Expression that is a single identifier.
        identifier (Token(Identifier)) - Identifier this expression represents.
    """

    def __init__(self, identifier):
        """Initialize node."""
        super().__init__()

        self.assert_kind(identifier, token_kinds.identifier)

        self.identifier = identifier

    def __repr__(self):
        return str(self.identifier)

    def make_code_raw(self, il_code, symbol_table):
        """Make code for an identifier. This function performs a lookup in the symbol table, and returns the
        corresponding ILValue.
        """
        return symbol_table.lookup_tok(self.identifier)

    def lvalue(self, il_code, symbol_table):
        """Return the LValue form of this identifier, or None."""
        var = symbol_table.lookup_tok(self.identifier)
        return LValue(LValue.DIRECT, var)


class ExprStatementNode(Node):
    """Statement that contains just an expression."""

    symbol = Node.STATEMENT

    def __init__(self, expr):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(expr, self.EXPRESSION)

        self.expr = expr

    def __repr__(self):
        return '\n\n\t\tStatement:{}'.format(self.expr)

    def make_code(self, il_code, symbol_table):
        """Make code for the expression. An ILValue is returned, but we ignore it."""
        self.expr.make_code(il_code, symbol_table)


class ParenExprNode(ExpressionNode):
    """Expression in parentheses."""

    def __init__(self, expr):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(expr, self.EXPRESSION)

        self.expr = expr

    def __repr__(self):
        return '(' + str(self.expr) + ')'

    def make_code_raw(self, il_code, symbol_table):
        """Make code for the expression in the parentheses."""
        return self.expr.make_code(il_code, symbol_table)

    def lvalue(self, il_code, symbol_table):
        """Return the LValue form of this identifier, or None."""
        return self.expr.lvalue(il_code, symbol_table)


class IfStatementNode(Node):
    """If/else statement.
        conditional - Condition expression of the if statement.

        statement - Statement to be executed by the if statement. Note this is very often a compound-statement blocked
        out with curly braces.

        else_statement - Statement to be executed in the else block, or None if there is no else block.
    """

    symbol = Node.STATEMENT

    def __init__(self, conditional, statement, else_statement):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(conditional, Node.EXPRESSION)
        self.assert_symbol(statement, Node.STATEMENT)

        self.conditional = conditional
        self.statement = statement
        self.else_statement = else_statement

    def make_code(self, il_code, symbol_table):
        """Make code for this node."""
        try:
            else_label = il_code.get_label()
            condition = self.conditional.make_code(il_code, symbol_table)
            il_code.add(il_commands.JumpZero(condition, else_label))
            self.statement.make_code(il_code, symbol_table)

            if self.else_statement:
                end_label = il_code.get_label()
                il_code.add(il_commands.Jump(end_label))
            else:
                end_label = None

            il_code.add(il_commands.Label(else_label))

            if self.else_statement:
                self.else_statement.make_code(il_code, symbol_table)
                il_code.add(il_commands.Label(end_label))

        except CompilerError as e:
            error_collector.add(e)


class BinaryOperatorNode(ExpressionNode):
    """Expression that is a sum/difference/xor/etc of two expressions.
        left_expr (expression) - Expression on left side.
        operator (Token) - Token representing this operator.
        right_expr (expression) - Expression on right side.
    """

    def __init__(self, left_expr, operator, right_expr):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(left_expr, self.EXPRESSION)
        self.assert_symbol(right_expr, self.EXPRESSION)

        self.left_expr = left_expr
        self.operator = operator
        self.right_expr = right_expr

    def __repr__(self):
        return "\n\t\t\tLeft Expression: '{}';\n\t\t\tOperator:'{}';\n\t\t\tRight Expression: '{}';".format(
            self.left_expr, self.operator, self.right_expr)

    def make_code_raw(self, il_code, symbol_table):
        """Make code for this node."""

        # If = operator
        if self.operator.kind == token_kinds.equals:
            return self.make_equals_code(il_code, symbol_table)

        # If boolean && operator
        elif self.operator.kind == token_kinds.bool_and:
            return self.make_bool_andor_code(True, il_code, symbol_table)

        # If boolean || operator
        elif self.operator.kind == token_kinds.bool_or:
            return self.make_bool_andor_code(False, il_code, symbol_table)

        # Make code for both operands
        left = self.left_expr.make_code(il_code, symbol_table)
        right = self.right_expr.make_code(il_code, symbol_table)

        # If arithmetic type
        if left.ctype.is_arith() and right.ctype.is_arith():
            return self.make_integer_code(right, left, il_code)

        # If operator is == or !=
        elif (self.operator.kind == token_kinds.twoequals or
              self.operator.kind == token_kinds.notequal):
            return self.make_equality_code(left, right, il_code)

        # If operator is addition
        elif self.operator.kind == token_kinds.plus:
            return self.make_plus_code(left, right, il_code)

        # If operator is &
        elif self.operator.kind == token_kinds.amp:
            return self.make_bitwise_and_code(left, right, il_code)

        elif self.operator.kind == token_kinds.minus:
            return self.make_minus_code(left, right, il_code)

        # If operator is multiplication or division
        elif self.operator.kind in {token_kinds.star, token_kinds.slash}:
            if self.operator.kind == token_kinds.star:
                descr = "invalid operand types for binary multiplication"
            else:  # self.operator.kind == token_kinds.slash
                descr = "invalid operand types for binary division"

            raise CompilerError(descr, self.operator.r)

        else:
            raise NotImplementedError("Unsupported operands")

    @staticmethod
    def promo_type(type1, type2):
        """Return the type these both should be promoted to for computation."""

        # If an int can represent all values of the original type, the value is converted to an int; otherwise, it is
        # converted to an unsigned int. These are called the integer promotions.

        # All types of size < 4 can fit in int, so we promote directly to int
        type1_promo = ctypes.integer if type1.size < 4 else type1
        type2_promo = ctypes.integer if type2.size < 4 else type2

        # If both operands have the same type, then no further conversion is needed.
        if type1_promo == type2_promo:
            return type1_promo

        # Otherwise, if both operands have signed integer types or both have unsigned integer types, the operand with
        # the type of lesser integer conversion rank is converted to the type of the operand with greater rank.
        elif type1_promo.signed == type2_promo.signed:
            return max([type1_promo, type2_promo], key=lambda t: t.size)

        # Otherwise, if the operand that has unsigned integer type has rank greater or equal to the rank of the type of
        # the other operand, then the operand with signed integer type is converted to the type of the operand with
        # unsigned integer type.
        elif not type1_promo.signed and type1_promo.size >= type2_promo.size:
            return type1_promo
        elif not type2_promo.signed and type2_promo.size >= type1_promo.size:
            return type2_promo

        # Otherwise, if the type of the operand with signed integer type can represent all of the values of the type of
        # the operand with unsigned integer type, then the operand with unsigned integer type is converted to the type
        # of the operand with signed integer type.
        elif type1_promo.signed and type1_promo.size > type2_promo.size:
            return type1_promo
        elif type2_promo.signed and type2_promo.size > type1_promo.size:
            return type2_promo

        # Otherwise, both operands are converted to the unsigned integer type corresponding to the type of the operand
        # with signed integer type.
        elif type1_promo.signed:
            return ctypes.to_unsigned(type1_promo)
        elif type2_promo.signed:
            return ctypes.to_unsigned(type2_promo)

    def make_integer_code(self, right, left, il_code):
        """Make code with given arithmetic operands.
            right - Expression on right side of operator.
            left - Expression on left side of operator.
            il_code - ILCode object to add code to.
        """
        # Cast both operands to a common type if necessary.
        new_type = self.promo_type(left.ctype, right.ctype)
        left_cast = set_type(left, new_type, il_code)
        right_cast = set_type(right, new_type, il_code)

        # Mapping from a token_kind to the ILCommand it corresponds to.
        cmd_map = {token_kinds.plus: il_commands.Add,
                   token_kinds.minus: il_commands.Sub,
                   token_kinds.star: il_commands.Mult,
                   token_kinds.slash: il_commands.Div,
                   token_kinds.amp: il_commands.BitwiseAnd,
                   token_kinds.twoequals: il_commands.EqualCmp,
                   token_kinds.notequal: il_commands.NotEqualCmp}

        # Commands that output an ILValue of integer type rather than of the input type.
        cmp_cmds = {il_commands.EqualCmp, il_commands.NotEqualCmp}
        if cmd_map[self.operator.kind] in cmp_cmds:
            output = ILValue(ctypes.integer)
        else:
            output = ILValue(new_type)
        il_code.add(cmd_map[self.operator.kind](output, left_cast, right_cast))
        return output

    def make_equals_code(self, il_code, symbol_table):
        """Make code if this is a = node."""
        right = self.right_expr.make_code(il_code, symbol_table)
        lvalue = self.left_expr.lvalue(il_code, symbol_table)

        if lvalue and lvalue.modable():
            return lvalue.set_to(right, il_code, self.operator)
        else:
            descr = "expression on left of '=' is not assignable"
            raise CompilerError(descr, self.operator.r)

    def make_bool_andor_code(self, andop, il_code, symbol_table):
        """Make code if this operation is boolean && or ||."""

        # ILValue for storing the output of this boolean operation
        out = ILValue(ctypes.integer)

        # ILValue for zero.
        zero = ILValue(ctypes.integer)
        il_code.register_literal_var(zero, "0")

        # ILValue for one.
        one = ILValue(ctypes.integer)
        il_code.register_literal_var(one, "1")

        # Label which immediately precedes the line which sets out to 0 or 1.
        set_out = il_code.get_label()

        # Label which skips the line which sets out to 0 or 1.
        end = il_code.get_label()

        if andop:
            jump_command = il_commands.JumpZero
        else:
            jump_command = il_commands.JumpNotZero

        left = self.left_expr.make_code(il_code, symbol_table)
        il_code.add(il_commands.Set(out, one if andop else zero))
        il_code.add(jump_command(left, set_out))
        right = self.right_expr.make_code(il_code, symbol_table)
        il_code.add(jump_command(right, set_out))
        il_code.add(il_commands.Jump(end))
        il_code.add(il_commands.Label(set_out))
        il_code.add(il_commands.Set(out, zero if andop else one))
        il_code.add(il_commands.Label(end))
        return out

    def make_bitwise_and_code(self, left, right, il_code):
        """Make code for & operator for non-arithmetic operands."""

        # One operand should be pointer to complete object type, and the other should be any integer type.
        if left.ctype.is_pointer() and right.ctype.is_integral():
            arith_op, pointer_op = right, left
        elif right.ctype.is_pointer() == left.ctype.is_integral():
            arith_op, pointer_op = left, right
        else:
            descr = "invalid operand types for binary addition"
            raise CompilerError(descr, self.operator.r)

        # Cast the integer operand to a long for multiplication.
        l_arith_op = set_type(arith_op, ctypes.unsign_longint, il_code)

        # Amount to shift the pointer by
        shift = ILValue(ctypes.unsign_longint)

        # ILValue for the output pointer
        out = ILValue(pointer_op.ctype)

        # Size of pointed-to object as a literal IL value
        size = ILValue(ctypes.unsign_longint)
        il_code.register_literal_var(size, str(pointer_op.ctype.arg.size))

        il_code.add(il_commands.Mult(shift, l_arith_op, size))
        il_code.add(il_commands.BitwiseAnd(out, pointer_op, shift))
        return out

    def make_plus_code(self, left, right, il_code):
        """Make code for + operator for non-arithmetic operands."""

        # One operand should be pointer to complete object type, and the other should be any integer type.
        if left.ctype.is_pointer() and right.ctype.is_integral():
            arith_op, pointer_op = right, left
        elif right.ctype.is_pointer() == left.ctype.is_integral():
            arith_op, pointer_op = left, right
        else:
            descr = "invalid operand types for binary addition"
            raise CompilerError(descr, self.operator.r)

        # Cast the integer operand to a long for multiplication.
        l_arith_op = set_type(arith_op, ctypes.unsign_longint, il_code)

        # Amount to shift the pointer by
        shift = ILValue(ctypes.unsign_longint)

        # ILValue for the output pointer
        out = ILValue(pointer_op.ctype)

        # Size of pointed-to object as a literal IL value
        size = ILValue(ctypes.unsign_longint)
        il_code.register_literal_var(size, str(pointer_op.ctype.arg.size))

        il_code.add(il_commands.Mult(shift, l_arith_op, size))
        il_code.add(il_commands.Add(out, pointer_op, shift))
        return out

    def make_minus_code(self, left, right, il_code):
        """Make code for - operator for non-arithmetic operands."""

        # Both operands are pointers to compatible object types
        if (left.ctype.is_pointer() and right.ctype.is_pointer()
                and left.ctype.compatible(right.ctype)):

            # Get raw difference in pointer values
            raw = ILValue(ctypes.longint)
            il_code.add(il_commands.Sub(raw, left, right))

            # Divide by size of object
            out = ILValue(ctypes.longint)
            size = ILValue(ctypes.longint)
            il_code.register_literal_var(size, str(left.ctype.arg.size))
            il_code.add(il_commands.Div(out, raw, size))

            return out

        # Left operand is pointer to complete object type, and right operand is integer.
        elif left.ctype.is_pointer() and right.ctype.is_integral():

            out = ILValue(left.ctype)
            raw = set_type(right, ctypes.longint, il_code)

            # Multiply by size of objects
            shift = ILValue(ctypes.longint)
            size = ILValue(ctypes.longint)
            il_code.register_literal_var(size, str(left.ctype.arg.size))
            il_code.add(il_commands.Mult(shift, raw, size))

            il_code.add(il_commands.Sub(out, left, shift))
            return out

        else:
            descr = "invalid operand types for binary subtraction"
            raise CompilerError(descr, self.operator.r)

    def make_equality_code(self, left, right, il_code):
        """Make code for == and != operators for non-arithmetic operands."""

        # If either operand is a null pointer constant, cast it to the other's pointer type.
        if left.ctype.is_pointer() and right.null_ptr_const:
            right = set_type(right, left.ctype, il_code)
        elif right.ctype.is_pointer() and left.null_ptr_const:
            left = set_type(left, right.ctype, il_code)

        # If both operands are not pointer types, warn!
        if not left.ctype.is_pointer() or not right.ctype.is_pointer():
            descr = "comparison between incomparable types"
            error_collector.add(CompilerError(descr, self.operator.r, True))

        # If one side is pointer to void, cast the other to same.
        elif left.ctype.arg.is_void():
            check_cast(right, left.ctype, self.operator)
            right = set_type(right, left.ctype, il_code)
        elif right.ctype.arg.is_void():
            check_cast(left, right.ctype, self.operator)
            left = set_type(left, right.ctype, il_code)

        # If both types are still incompatible, warn!
        elif not left.ctype.compatible(right.ctype):
            descr = "comparison between distinct pointer types"
            error_collector.add(CompilerError(descr, self.operator.r, True))

        # Now, we can do comparison
        output = ILValue(ctypes.integer)
        if self.operator.kind == token_kinds.twoequals:
            cmd = il_commands.EqualCmp
        else:
            cmd = il_commands.NotEqualCmp
        il_code.add(cmd(output, left, right))
        return output


class IncrDecr(ExpressionNode, ABC):
    """General helper class for increment and decrement nodes."""

    def _make_code(self, expr, incr, pre, tok, il_code, symbol_table):
        """Make code for this post/pre-fix incr/decrement node.
            expr - Node containing the argument expression.
            incr (bool) - True if this is an increment node, False if it is a decrement node.
            pre (bool) - True if this is a prefix operator, False if it is a postfix operator.
        """
        command = il_commands.Add if incr else il_commands.Sub

        val = expr.make_code(il_code, symbol_table)
        lval = expr.lvalue(il_code, symbol_table)

        if not lval or not lval.modable():
            descr = "operand of increment operator not a modifiable lvalue"
            raise CompilerError(descr, tok.r)

        one = ILValue(val.ctype)
        if val.ctype.is_arith():
            il_code.register_literal_var(one, "1")
        elif val.ctype.is_pointer():
            il_code.register_literal_var(one, str(val.ctype.arg.size))
        else:
            raise NotImplementedError("Unsupported operands")

        new_val = ILValue(val.ctype)

        if pre:
            il_code.add(command(new_val, val, one))
            lval.set_to(new_val, il_code, tok)
            return new_val
        else:
            old_val = ILValue(val.ctype)
            il_code.add(il_commands.Set(old_val, val))
            il_code.add(command(new_val, val, one))
            lval.set_to(new_val, il_code, tok)
            return old_val


class PreIncrNode(IncrDecr):
    """A prefix increment node, like `++a`."""

    def __init__(self, expr, tok):
        """Initialize node."""
        self.expr = expr
        self.tok = tok

        super().__init__()

    def make_code_raw(self, il_code, symbol_table):
        """Make code for this node."""
        return self._make_code(self.expr, True, True, self.tok, il_code, symbol_table)


class PreDecrNode(IncrDecr):
    """A prefix decrement node, like `a--`."""

    def __init__(self, expr, tok):
        """Initialize node."""
        self.expr = expr
        self.tok = tok

        super().__init__()

    def make_code_raw(self, il_code, symbol_table):
        """Make code for this node."""
        return self._make_code(self.expr, False, True, self.tok, il_code, symbol_table)


class PostIncrNode(IncrDecr):
    """A postfix increment node, like `a++`."""

    def __init__(self, expr, tok):
        """Initialize node."""
        self.expr = expr
        self.tok = tok

        super().__init__()

    def make_code_raw(self, il_code, symbol_table):
        """Make code for this node."""
        return self._make_code(self.expr, True, False, self.tok, il_code, symbol_table)


class PostDecrNode(IncrDecr):
    """A postfix decrement node, like `a--`."""

    def __init__(self, expr, tok):
        """Initialize node."""
        self.expr = expr
        self.tok = tok

        super().__init__()

    def make_code_raw(self, il_code, symbol_table):
        """Make code for this node."""
        return self._make_code(self.expr, False, False, self.tok, il_code, symbol_table)


class BoolNotNode(ExpressionNode):
    """Expression like `!a`."""

    def __init__(self, expr, op):
        """Initialize node."""
        super().__init__()

        self.expr = expr
        self.op = op

    def make_code_raw(self, il_code, symbol_table):
        """Make code for this node."""

        # ILValue for storing the output
        out = ILValue(ctypes.integer)

        # ILValue for zero.
        zero = ILValue(ctypes.integer)
        il_code.register_literal_var(zero, "0")

        # ILValue for one.
        one = ILValue(ctypes.integer)
        il_code.register_literal_var(one, "1")

        # Label which skips the line which sets out to 0.
        end = il_code.get_label()

        expr = self.expr.make_code(il_code, symbol_table)
        il_code.add(il_commands.Set(out, one))
        il_code.add(il_commands.JumpZero(expr, end))
        il_code.add(il_commands.Set(out, zero))
        il_code.add(il_commands.Label(end))

        return out


class AddrOfNode(ExpressionNode):
    """Expression produced by getting the address of a variable.
        expr (expression) - lvalue for which to get the address.
        op (Token) - Token representing this operator. Used for error reporting.
    """

    def __init__(self, expr, op):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(expr, Node.EXPRESSION)
        self.expr = expr
        self.op = op

    def make_code_raw(self, il_code, symbol_table):
        """Make code for getting the address."""
        lvalue = self.expr.lvalue(il_code, symbol_table)
        if lvalue:
            return lvalue.addr(il_code)
        else:
            descr = "lvalue required as unary '&' operand"
            raise CompilerError(descr, self.op.r)


class DerefNode(ExpressionNode):
    """Expression produced by dereferencing a pointer.
        expr (expression) - pointer to dereference.
    """

    def __init__(self, expr, op):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(expr, Node.EXPRESSION)
        self.expr = expr
        self.op = op

        # Cache the expression IL value, so calls to make_code_raw or lvalue only calculate the expression once.
        # This is important in expressions like
        #
        #     *func() += 1;
        #
        # where evaluating the expression multiple times can produce additional side effects.
        self._cache_lvalue = None

    def make_code_raw(self, il_code, symbol_table):
        """Make code for getting the value at the address."""
        lvalue = self.lvalue(il_code, symbol_table)

        out = ILValue(lvalue.il_value.ctype.arg)
        il_code.add(il_commands.ReadAt(out, lvalue.il_value))
        return out

    def lvalue(self, il_code, symbol_table):
        """Return the LValue form of this identifier, or None."""
        if not self._cache_lvalue:
            addr = self.expr.make_code(il_code, symbol_table)

            if not addr.ctype.is_pointer():
                descr = "operand of unary '*' must have pointer type"
                raise CompilerError(descr, self.op.r)

            self._cache_lvalue = LValue(LValue.INDIRECT, addr)

        return self._cache_lvalue


class ArraySubscriptNode(ExpressionNode):
    """Expression produced by array subscripting.
            arr[n]
        head (expression) - expression in position `arr` above
        arg (expression) - expression in position `n` above
        op (Token) - the first open square bracket token
    """

    def __init__(self, head, arg, op):
        """Initialize node."""
        super().__init__()

        self.assert_symbol(head, Node.EXPRESSION)
        self.assert_symbol(arg, Node.EXPRESSION)

        self.head = head
        self.arg = arg
        self.op = op

        # Cache the expression IL value. Explained further in DerefNode constructor.
        self._cache_lvalue = None

    def make_code_raw(self, il_code, symbol_table):
        """Make code for this node."""
        lvalue = self.lvalue(il_code, symbol_table)

        out = ILValue(lvalue.il_value.ctype.arg)
        il_code.add(il_commands.ReadAt(out, lvalue.il_value))
        return out

    def lvalue(self, il_code, symbol_table):
        """Return the LValue form of this node."""

        # One operand should be pointer to complete object type, and the other should be any integer type.

        # Return a cached value if one exists
        if self._cache_lvalue:
            return self._cache_lvalue

        head_val = self.head.make_code(il_code, symbol_table)
        arg_val = self.arg.make_code(il_code, symbol_table)

        # Otherwise, compute the lvalue
        if head_val.ctype.is_pointer() and arg_val.ctype.is_integral():
            arith, point = arg_val, head_val

        elif head_val.ctype.is_integral() and arg_val.ctype.is_pointer():
            arith, point = head_val, arg_val

        else:
            descr = "invalid operand types for array subscriping"
            raise CompilerError(descr, self.op.r)

        # Cast the integer operand to a long for multiplication.
        l_arith = set_type(arith, ctypes.unsign_longint, il_code)

        # Amount to shift the pointer by
        shift = ILValue(ctypes.unsign_longint)

        # ILValue for the output pointer
        out = ILValue(point.ctype)

        # Size of pointed-to object as a literal IL value
        size = ILValue(ctypes.unsign_longint)
        il_code.register_literal_var(size, str(point.ctype.arg.size))

        il_code.add(il_commands.Mult(shift, l_arith, size))
        il_code.add(il_commands.Add(out, point, shift))

        self._cache_lvalue = LValue(LValue.INDIRECT, out)
        return self._cache_lvalue


class DeclarationNode(Node):
    """Line of a general variable declaration(s).
        decls (List(decl_tree.Node)) - list of declaration trees.
        inits (List(ExpressionNode)) - list of initializer expressions, or None if a variable is not initialized.
    """

    symbol = Node.DECLARATION

    def __init__(self, decls, inits):
        """Initialize node."""
        super().__init__()
        self.decls = decls
        self.inits = inits

    def __repr__(self):
        return "\n\t\tVariable name: '{}' -> type'{}' -> value'{}';".format(self.decls, self.decls, self.inits)

    # Storage class specifiers for declarations
    AUTO = 0
    STATIC = 1
    EXTERN = 2

    def _make_code(self, il_code, symbol_table, global_level):
        """Make code for this declaration.
            global_level (Bool) - Whether this is a global declaration or local declaration. If this is a global
            declaration, expects initialization to be a compile-time constant. Also, adds the global variable to the
            ILCode object.
        """
        for decl, init in zip(self.decls, self.inits):
            try:
                ctype, identifier, storage = self.make_ctype(decl)
                if not identifier:
                    descr = "missing identifier name in declaration"
                    raise CompilerError(descr, decl.specs[0].r)

                if ctype == ctypes.void:
                    descr = "variable of void type declared"
                    raise CompilerError(descr, identifier.r)

                var = symbol_table.add(identifier, ctype)

                # Variables declared to be EXTERN
                if storage == self.EXTERN:
                    il_code.register_extern_var(var, identifier.content)

                    # Extern variable should not have initializer
                    if init:
                        descr = "extern variable has initializer"
                        raise CompilerError(descr, identifier.r)

                # Variables declared to be static
                elif storage == self.STATIC:
                    # These should be in .data section, but not global
                    raise NotImplementedError("static variables unsupported")

                # Global variables
                elif global_level:
                    # These should be common if uninitialized, or data if initialized
                    raise NotImplementedError("non-extern global variables unsupported")

                # Local variables
                else:
                    il_code.register_local_var(var)

                # Initialize variable if needed
                if init:
                    init_val = init.make_code(il_code, symbol_table)
                    lval = LValue(LValue.DIRECT, var)
                    if lval.modable():
                        lval.set_to(init_val, il_code, identifier)
                    else:
                        descr = "declared variable is not of assignable type"
                        raise CompilerError(descr, identifier.r)

            except CompilerError as e:
                error_collector.add(e)
                continue

    def make_code(self, il_code, symbol_table):
        """Make code for this declaration.
        This function does not generate any IL code; it just adds the declared variable(s) to the symbol table.
        """
        return self._make_code(il_code, symbol_table, False)

    def make_code_global(self, il_code, symbol_table):
        """Make code for this declaration if it is global.
        This function adds the declared variable(s) to the symbol table and registers them with the ILCode object.
        """
        return self._make_code(il_code, symbol_table, True)

    def make_ctype(self, decl, prev_ctype=None, storage=0):
        """Generate a ctype from the given declaration. Return a `ctype, identifier token, storage class` triple.
            decl - Node of decl_tree to parse. See decl_tree.py for explanation about decl_trees.
            prev_ctype - The ctype formed from all parts of the tree above the current one.
            storage - The storage class of this declaration.
        """
        if isinstance(decl, decl_tree.Root):
            ctype, storage = self.make_specs_ctype(decl.specs)
            return self.make_ctype(decl.child, ctype, storage)
        elif isinstance(decl, decl_tree.Pointer):
            return self.make_ctype(decl.child, PointerCType(prev_ctype), storage)
        elif isinstance(decl, decl_tree.Array):
            return self.make_ctype(decl.child, ArrayCType(prev_ctype, decl.n), storage)
        elif isinstance(decl, decl_tree.Identifier):
            return prev_ctype, decl.identifier, storage

    def make_specs_ctype(self, specs):
        """Make a ctype out of the provided list of declaration specifiers.
        Return a `ctype, storage class` pair, where storage class is one of the above values.
        """
        spec_kinds = [spec.kind for spec in specs]
        base_type_list = list(set(ctypes.simple_types.keys()) &
                              set(spec_kinds))
        if len(base_type_list) == 0:
            base_type = ctypes.integer
        elif len(base_type_list) == 1:
            base_type = ctypes.simple_types[base_type_list[0]]
        else:
            descr = "two or more data types in declaration specifiers"
            raise CompilerError(descr, specs[0].r)

        signed_list = list({token_kinds.signed_kw, token_kinds.unsigned_kw} & set(spec_kinds))

        if len(signed_list) == 1 and signed_list[0] == token_kinds.unsigned_kw:
            base_type = ctypes.to_unsigned(base_type)
        elif len(signed_list) > 1:
            descr = "both signed and unsigned in declaration specifiers"
            raise CompilerError(descr, specs[0].r)

        # Create set of storage class specifiers that are present
        storage_class_set = {token_kinds.auto_kw, token_kinds.static_kw, token_kinds.extern_kw}
        storage_class_single = storage_class_set & set(spec_kinds)

        if len(storage_class_single) == 0:
            storage = self.AUTO
        elif len(storage_class_single) == 1:
            if token_kinds.static_kw in storage_class_single:
                storage = self.STATIC
            elif token_kinds.extern_kw in storage_class_single:
                storage = self.EXTERN
            else:  # must be `auto` kw
                storage = self.AUTO
        else:
            descr = "two or more storage classes in declaration specifiers"
            raise CompilerError(descr, specs[0].r)

        return base_type, storage
