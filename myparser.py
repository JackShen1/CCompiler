"""Objects for the parsing phase of the compiler. This parser is written entirely by hand."""

import token_kinds
import decl_tree
import ctypes
import tree

from errors import CompilerError, ParserError, error_collector
from collections import namedtuple
from tokens import Token


class Parser:
    """Logic for converting a list of tokens into an AST.

    Each internal function parse_* corresponds to a unique non-terminal symbol in the C grammar. It parses self.tokens
    beginning at the given index to try to match a grammar rule that generates the desired symbol. If a match is found,
    it returns a tuple (Node, index) where Node is an AST node for that match and index is one more than that of the
    last token consumed in that parse. If no match is not found, raises an appropriate ParserError.

    Whenever a call to a parse_* function raises a ParserError, the calling function must either catch the exception and
    log it (using self._log_error), or pass the exception on to the caller. A function takes the first approach if there
    are other possible parse paths to consider, and the second approach if the function cannot parse the entity from the
    tokens.

        tokens (List(Token)) - The list of tokens to be parsed.
        best_error (ParserError) - The "best error" encountered so far. That is, out of all the errors encountered
        so far, this is the one that occurred after successfully parsing the most tokens.
    """

    def __init__(self, tokens):
        """Initialize parser."""
        self.tokens = tokens
        self.best_error = None

    def parse(self):
        """Parse the provided list of tokens into an abstract syntax tree (AST).
            returns (Node) - Root node of the generated AST.
        """
        try:
            node, index = self.parse_root(0)
        except ParserError as e:
            self.log_error(e)
            error_collector.add(self.best_error)
            return None

        return node

    def parse_root(self, index):
        """Parse the entire compilation unit."""
        nodes = []
        while True:
            try:
                node, index = self.parse_main(index)
                nodes.append(node)
            except ParserError as e:
                self.log_error(e)
            else:
                continue

            try:
                node, index = self.parse_declaration(index)
                nodes.append(node)
            except ParserError as e:
                self.log_error(e)
            else:
                continue

            # If neither parse attempt above worked, break
            break

        # If there are tokens that remain unparsed, complain
        if not self.tokens[index:]:
            return tree.RootNode(nodes), index
        else:
            descrip = "unexpected token"
            raise ParserError(descrip, index, self.tokens, ParserError.AT)

    def parse_main(self, index):
        """Parse a main function containing block items.
            Ex: int main() { return 4; }
        """
        err = "expected main function starting"
        index = self.match_token(index, token_kinds.int_kw, err, ParserError.AT)
        index = self.match_token(index, token_kinds.main, err, ParserError.AT)
        index = self.match_token(index, token_kinds.open_paren, err, ParserError.AT)
        index = self.match_token(index, token_kinds.close_paren, err, ParserError.AT)

        node, index = self.parse_compound_statement(index)
        return tree.MainNode(node), index

    def parse_statement(self, index):
        """Parse a statement. Try each possible type of statement, catching/logging exceptions upon parse failures.
        On the last try, raise the exception on to the caller.
        """
        try:
            return self.parse_compound_statement(index)
        except ParserError as e:
            self.log_error(e)

        try:
            return self.parse_return(index)
        except ParserError as e:
            self.log_error(e)

        try:
            return self.parse_if_statement(index)
        except ParserError as e:
            self.log_error(e)

        return self.parse_expr_statement(index)

    def parse_compound_statement(self, index):
        """Parse a compound statement.
        A compound statement is a collection of several statements/declarations, enclosed in braces.
        """
        index = self.match_token(index, token_kinds.open_brack, "expected '{'", ParserError.GOT)

        # Read block items (statements/declarations) until there are no more.
        nodes = []
        while True:
            try:
                node, index = self.parse_statement(index)
                nodes.append(node)
                continue
            except ParserError as e:
                self.log_error(e)

            try:
                node, index = self.parse_declaration(index)
                nodes.append(node)
                continue
            except ParserError as e:
                self.log_error(e)
                # When both of our parsing attempts fail, break out of the loop
                break

        index = self.match_token(index, token_kinds.close_brack, "expected '}'", ParserError.GOT)

        return tree.CompoundNode(nodes), index

    def parse_return(self, index):
        """Parse a return statement.
            Ex: return 5;
        """
        index = self.match_token(index, token_kinds.return_kw, "expected keyword 'return'", ParserError.GOT)
        return_kw = self.tokens[index - 1]
        node, index = self.parse_expression(index)
        index = self.expect_semicolon(index)
        return tree.ReturnNode(node, return_kw), index

    def parse_if_statement(self, index):
        """Parse an if statement."""

        descrip = "expected keyword '{}'".format(token_kinds.if_kw.text_repr),
        index = self.match_token(index, token_kinds.if_kw, descrip, ParserError.GOT)
        index = self.match_token(index, token_kinds.open_paren, "expected '('", ParserError.AFTER)
        conditional, index = self.parse_expression(index)
        index = self.match_token(index, token_kinds.close_paren, "expected ')'", ParserError.AFTER)
        statement, index = self.parse_statement(index)

        # If there is an else that follows, parse that too.
        is_else = self.next_token_is(index, token_kinds.else_kw)
        if not is_else:
            else_statement = None
        else:
            descrip = "expected keyword '{}'".format(token_kinds.else_kw.text_repr)
            index = self.match_token(index, token_kinds.else_kw, descrip, ParserError.GOT)
            else_statement, index = self.parse_statement(index)

        return tree.IfStatementNode(conditional, statement, else_statement), index

    def parse_expr_statement(self, index):
        """Parse a statement that is an expression.
            Ex: a = 3 + 4
        """
        node, index = self.parse_expression(index)

        # We print a special diagnostic here, rather than standard "missing semicolon". Often, a malformed expression
        # causes parsing to stop prematurely due to the current expression parsing algorithm. So, if the token which
        # follows the expression is not a semicolon, it is often the result of a malformed expression rather than a
        # missing semicolon.
        descrip = "missing semicolon or malformed expression"
        index = self.match_token(index, token_kinds.semicolon, descrip, ParserError.AFTER)
        return tree.ExprStatementNode(node), index

    def parse_expression(self, index):
        """Parse an expression. The index returned is of the first token that could not be parsed into the expression.
        If none could be parsed, an exception is raised as usual.
        """
        return ExpressionParser(self.tokens).parse(index)

    def parse_declaration(self, index):
        """Parse a declaration.
            Example: int *a, (*b)[], c
        """
        specs, index = self.parse_decl_specifiers(index)

        # If declaration specifiers are followed directly by semicolon
        if self.next_token_is(index, token_kinds.semicolon):
            return tree.DeclarationNode([], []), index + 1

        decls = []
        inits = []
        while True:
            end = self.find_decl_end(index)
            t = decl_tree.Root(specs, self.parse_declarator(index, end))
            decls.append(t)

            index = end
            if self.next_token_is(index, token_kinds.equals):
                # Parse initializer expression. Currently, only simple initializers are supported.
                expr, index = self.parse_expression(index + 1)
                inits.append(expr)
            else:
                inits.append(None)

            # Expect a comma, break if there isn't one
            if self.next_token_is(index, token_kinds.comma):
                index += 1
            else:
                break

        self.expect_semicolon(index)
        return tree.DeclarationNode(decls, inits), index + 1

    def parse_decl_specifiers(self, index):
        """Parse a declaration specifier.
            Examples: int; const char; typedef int
        """
        decl_specifiers = (list(ctypes.simple_types.keys()) + [token_kinds.signed_kw, token_kinds.unsigned_kw,
                                                               token_kinds.auto_kw, token_kinds.static_kw,
                                                               token_kinds.extern_kw])

        specs = []
        while True:
            for spec in decl_specifiers:
                if self.next_token_is(index, spec):
                    specs.append(self.tokens[index])
                    index += 1
                    break
            else:
                # If the for loop did not break, quit the while loop
                break

        if specs:
            return specs, index
        else:
            raise ParserError("expected declaration specifier", index, self.tokens, ParserError.AT)

    def find_pair_forward(self, index, open_=token_kinds.open_paren, close_=token_kinds.close_paren,
                          mess="mismatched parentheses in declaration"):
        """Find the closing parenthesis for the opening at given index.
            index - position to start search, should be of kind `open`.
            open - token kind representing the open parenthesis.
            close - token kind representing the close parenthesis.
            mess - message for error on mismatch.
        """
        depth = 0
        for i in range(index, len(self.tokens)):
            if self.tokens[i].kind == open_:
                depth += 1
            elif self.tokens[i].kind == close_:
                depth -= 1

            if depth == 0:
                break
        else:
            # if loop did not break, no close paren was found
            raise ParserError(mess, index, self.tokens, ParserError.AT)
        return i

    def find_pair_backward(self, index, open_=token_kinds.open_paren, close_=token_kinds.close_paren,
                           mess="mismatched parentheses in declaration"):
        """Find the opening parenthesis for the closing at given index. Same parameters as _find_pair_forward above."""
        depth = 0
        for i in range(index, -1, -1):
            if self.tokens[i].kind == close_:
                depth += 1
            elif self.tokens[i].kind == open_:
                depth -= 1

            if depth == 0:
                break
        else:
            # if loop did not break, no open paren was found
            raise ParserError(mess, index, self.tokens, ParserError.AT)
        return i

    def find_decl_end(self, index):
        """Find the end of the declarator that starts at given index. If a valid declarator starts at the given index,
        this function is guaranteed to return the correct end point. Returns an index one greater than the last index in
        this declarator.
        """
        if self.next_token_is(index, token_kinds.star) or self.next_token_is(index, token_kinds.identifier):
            return self.find_decl_end(index + 1)
        elif self.next_token_is(index, token_kinds.open_paren):
            close = self.find_pair_forward(index)
            return self.find_decl_end(close + 1)
        elif self.next_token_is(index, token_kinds.open_sq_brack):
            mess = "mismatched square brackets in declaration"
            close = self.find_pair_forward(index, token_kinds.open_sq_brack, token_kinds.close_sq_brack, mess)
            return self.find_decl_end(close + 1)
        else:
            # Unknown token. If this declaration is correctly formatted, then this must be the end of the declaration.
            return index

    def parse_declarator(self, start, end):
        """Parse the given tokens that comprises a declarator.
        This function parses both declarator and abstract-declarators. For an abstract declarator, the Identifier node
        at the leaf of the generated tree has the identifier None. Expects the declarator to start at start and end at
        end-1 inclusive. Returns a decl_tree.Node.
        """
        if start == end:
            return decl_tree.Identifier(None)
        elif start + 1 == end and self.tokens[start].kind == token_kinds.identifier:
            return decl_tree.Identifier(self.tokens[start])

        # First and last elements make a parenthesis pair
        elif self.tokens[start].kind == token_kinds.open_paren and self.find_pair_forward(start) == end - 1:
            return self.parse_declarator(start + 1, end - 1)

        elif self.tokens[start].kind == token_kinds.star:
            return decl_tree.Pointer(self.parse_declarator(start + 1, end))

        # Last element indicates an array type
        elif self.tokens[end - 1].kind == token_kinds.close_sq_brack:
            first = self.tokens[end - 3].kind == token_kinds.open_sq_brack
            number = self.tokens[end - 2].kind == token_kinds.number
            if first and number:
                return decl_tree.Array(int(self.tokens[end - 2].content), self.parse_declarator(start, end - 3))

        raise ParserError("faulty declaration syntax", start, self.tokens, ParserError.AT)

    def expect_semicolon(self, index):
        """Expect a semicolon at self.tokens[index].
        If one is found, return index+1. Otherwise, raise an appropriate ParserError.
        """
        return self.match_token(index, token_kinds.semicolon, "expected semicolon", ParserError.AFTER)

    def next_token_is(self, index, kind):
        """Return true iff the next token is of the given kind."""
        return len(self.tokens) > index and self.tokens[index].kind == kind

    def match_token(self, index, kind, message, message_type):
        """Raise ParserError if tokens[index] is not of the expected kind.
        If tokens[index] is of the expected kind, returns index + 1. Otherwise, raises a ParserError with the given
        message and message_type.
        """
        if len(self.tokens) > index and self.tokens[index].kind == kind:
            return index + 1
        else:
            raise ParserError(message, index, self.tokens, message_type)

    def log_error(self, error):
        """Log the error in the parser to be used for error reporting. The value of error.amount_parsed is used to
        determine the amount successfully parsed before encountering the error.
            error (ParserError) - Error encountered.
        """
        if not self.best_error or error.amount_parsed >= self.best_error.amount_parsed:
            self.best_error = error


class ExpressionParser:
    """Class for parsing expressions. The Parser class above dispatches to this ExpressionParser class for parsing
    expressions. The ExpressionParser implements a shift-reduce parser.
    """

    # Dictionary of key-value pairs {TokenKind: precedence} where higher precedence is higher.
    binary_operators = {token_kinds.plus: 11, token_kinds.minus: 11, token_kinds.star: 12, token_kinds.slash: 12,
                        token_kinds.twoequals: 8, token_kinds.notequal: 8, token_kinds.equals: 1,
                        token_kinds.amp: 7, token_kinds.bool_and: 4, token_kinds.bool_or: 3}

    # Dictionary of unary prefix operators {TokenKind: tree.Node}
    unary_prefix_operators = {token_kinds.amp: tree.AddrOfNode, token_kinds.star: tree.DerefNode,
                              token_kinds.incr: tree.PreIncrNode, token_kinds.decr: tree.PreDecrNode,
                              token_kinds.bool_not: tree.BoolNotNode}

    # Dictionary of unary postfix operators {TokenKind: tree.Node}
    unary_postfix_operators = {token_kinds.incr: tree.PostIncrNode, token_kinds.decr: tree.PostDecrNode}

    # The set of tokens that indicate that a postfix operator follows. For example, the open parenthesis indicates a
    # function call follows, and open square bracket indicates an array subscript follows. These have highest priority.
    posfix_operator_begin = {token_kinds.open_paren, token_kinds.open_sq_brack, token_kinds.incr, token_kinds.decr}

    # The set of assignment_tokens (because these are right-associative)
    assignment_operators = {token_kinds.equals}

    # The set of all token kinds that can be in an expression but are not in binary_operators or unary_prefix_operators.
    # Used to determine when parsing can stop.
    valid_tokens = {token_kinds.number, token_kinds.identifier, token_kinds.string, token_kinds.char_string,
                    token_kinds.open_paren, token_kinds.close_paren, token_kinds.open_sq_brack,
                    token_kinds.close_sq_brack, token_kinds.comma}

    # An item in the parsing stack. The item is either a Node or Token, where the node must generate an expression, and
    # the length is the number of tokens consumed in generating this node.
    StackItem = namedtuple("StackItem", ['item', 'length'])

    def __init__(self, tokens):
        """Initialize parser."""
        self.tokens = tokens
        self.s = []

    def parse(self, index):
        """Parse an expression from the given tokens.
        We parse expressions using a shift-reduce parser. We try to comprehend as much as possible of self.tokens past
        the index as being an expression, and the index returned is the first token that could not be parsed into the
        expression. If literally none of it could be parsed as an expression, raises an exception like usual.
        """
        i = index
        while True:
            # Try all of the possible matches
            if not (self.try_match_number() or
                    self.try_match_string() or
                    self.try_match_identifier() or
                    self.try_match_bin_op(self.tokens[i:]) or
                    self.try_match_unary_prefix(self.tokens[i:]) or
                    self.try_match_unary_postfix() or
                    self.try_match_array_subsc() or
                    self.try_match_paren_expr()):

                # None of the known patterns match!

                # If we're at the end of the token list, or we've reached a
                # token that can never appear in an expression, stop reading.
                if i == len(self.tokens):
                    break
                elif (self.tokens[i].kind not in self.valid_tokens and
                      self.tokens[i].kind not in self.binary_operators and
                      self.tokens[i].kind not in self.unary_prefix_operators):
                    break

                # Shift one more token onto the stack
                self.s.append(self.StackItem(self.tokens[i], 1))
                i += 1

        if self.s and isinstance(self.s[0].item, tree.Node):
            return self.s[0].item, index + self.s[0].length
        else:
            err = "expected expression"
            raise ParserError(err, index, self.tokens, ParserError.GOT)

    def try_match_number(self):
        """Try matching the top of the stack to a number node. Return True on successful match, False otherwise. """
        if self.match_kind(-1, token_kinds.number):
            self.reduce(tree.NumberNode(self.s[-1].item), 1)
            return True
        return False

    def try_match_string(self):
        """Try matching the top of the stack to a string or char node. Return 1 on successful match, 0 otherwise."""
        if self.match_kind(-1, token_kinds.string):
            self.reduce(tree.StringNode(self.s[-1].item), 1)
            return True
        elif self.match_kind(-1, token_kinds.char_string):
            chars = self.s[-1].item.content
            if len(chars) == 0:
                descrip = "empty character constant"
                error_collector.add(CompilerError(descrip, self.s[-1].item.r))
                self.reduce(tree.NumberNode(None), 1)

            elif len(chars) > 1:
                descrip = "multiple characters in character constant"
                error_collector.add(CompilerError(descrip, self.s[-1].item.r))
                self.reduce(tree.NumberNode(None), 1)

            else:
                self.reduce(tree.NumberNode(chars[0]), 1)

            return True

        return False

    def try_match_identifier(self):
        """Try matching the top of the stack to an identifier node. Return True on successful match, False otherwise."""
        if self.match_kind(-1, token_kinds.identifier):
            self.reduce(tree.IdentifierNode(self.s[-1].item), 1)
            return True
        return False

    def try_match_bin_op(self, buffer):
        """Try matching the top of the stack to a binary operator node. If the next token indicates a higher-precedence
        operator, do not match the bin op in this function.
        """
        # Ensure last three nodes match to permit precedence calculations.
        if not (self.match_node(-1) and self.match_kind_in(-2, self.binary_operators) and self.match_node(-3)):
            return False

        if not buffer:
            higher_prec_bin = False
            higher_prec_post = False
            another_assignment = False
        else:
            next_ = buffer[0]

            # is next token a higher precedence binary operator?
            higher_prec_bin = (next_.kind in self.binary_operators and
                               (self.binary_operators[next_.kind] > self.binary_operators[self.s[-2].item.kind]))

            # is next token a high-precedence postfix operator?
            higher_prec_post = next_.kind in self.posfix_operator_begin

            # is both this token and next token an assignment operator, because assignment operators right associative?
            another_assignment = ((self.s[-2].item.kind in self.assignment_operators) and
                                  (next_.kind in self.assignment_operators))

        if not (higher_prec_bin or higher_prec_post or another_assignment):
            node = tree.BinaryOperatorNode(self.s[-3].item, self.s[-2].item, self.s[-1].item)
            self.reduce(node, 3)
            return True

        return False

    def try_match_unary_prefix(self, buffer):
        """Try matching the top of the stack to prefix unary operator node."""

        if not (self.match_node(-1) and self.match_kind_in(-2, self.unary_prefix_operators)):
            return False

        # Make sure next token is not a postfix operator.
        if not buffer or buffer[0].kind not in self.posfix_operator_begin:
            node = self.unary_prefix_operators[self.s[-2].item.kind]
            self.reduce(node(self.s[-1].item, self.s[-2].item), 2)
            return True

        return False

    def try_match_unary_postfix(self):
        """Try matching the top of the stack to postfix unary operator node."""

        if not (self.match_node(-2) and self.match_kind_in(-1, self.unary_postfix_operators)):
            return False

        node = self.unary_postfix_operators[self.s[-1].item.kind]
        self.reduce(node(self.s[-2].item, self.s[-1].item), 2)
        return True

    def try_match_array_subsc(self):
        """Try matching an array subscript postfix operator."""
        if (self.match_kind(-1, token_kinds.close_sq_brack) and self.match_node(-2) and
                self.match_kind(-3, token_kinds.open_sq_brack) and self.match_node(-4)):

            node = tree.ArraySubscriptNode(self.s[-4].item, self.s[-2].item, self.s[-3].item)
            self.reduce(node, 4)
            return True

        return False

    def try_match_paren_expr(self):
        """Try matching a parenthesized expression."""

        if (self.match_kind(-3, token_kinds.open_paren) and self.match_node(-2) and
                self.match_kind(-1, token_kinds.close_paren)):
            node = tree.ParenExprNode(self.s[-2].item)
            self.reduce(node, 3)
            return True

        return False

    def match_kind(self, index, kind):
        """Check whether the index-th element in the stack is of given kind."""
        try:
            item = self.s[index].item
            return isinstance(item, Token) and item.kind == kind
        except IndexError:
            return False

    def match_kind_in(self, index, kinds):
        """Check whether index-th element in stack is of one of given kinds."""
        try:
            item = self.s[index].item
            return isinstance(item, Token) and item.kind in kinds
        except IndexError:
            return False

    def match_node(self, index):
        """Check whether the index-th element in the stack is a Node."""
        try:
            return isinstance(self.s[index].item, tree.Node)
        except IndexError:
            return False

    def reduce(self, node, num):
        """Perform a reduce operation on the stack.
            node (Node) - Node to reduce into.
            num (int) - Number of elements to reduce and replace with new Node.
        """
        length = sum(i.length for i in self.s[-num:])

        del self.s[-num:]
        self.s.append(self.StackItem(node, length))
