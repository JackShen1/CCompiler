"""Tests for the parser phase of the compiler."""

import tree
import token_kinds
from decl_tree import Root, Pointer, Array, Identifier
from errors import error_collector
from myparser import Parser
from tokens import Token
from tests.test_utils import TestUtils


class ParserTestUtil(TestUtils):
    """Utilities for parser tests."""

    def setUp(self):
        """Clear the error collector before each new test."""
        error_collector.clear()

    def tearDown(self):
        """Assert there are no remaining errors."""
        self.assertNoIssues()

    def assertParsesTo(self, tokens, nodes):
        """Assert the given tokens parse to the given tree nodes.
        This method adds the 'int main() { }' so no need to include those
        tokens in the input list. Similarly, nodes need not include the
        tree.MainNode, just a list of the nodes within.
        """
        ast_root = Parser(self._token_wrap_main(tokens)).parse()
        self.assertEqual(ast_root,
                         tree.RootNode([
                             tree.MainNode(tree.CompoundNode(nodes))
                         ]))

    def assertParserError(self, tokens, descrip):
        """Assert the given tokens create a compiler error.
        As above, no need to include 'int main() { }' in the tokens.
        """
        Parser(self._token_wrap_main(tokens)).parse()
        self.assertIssues([descrip])

    def _token_wrap_main(self, tokens):
        """Prefix the `tokens` list with 'int main() {' and suffix with '}'."""
        start_main = [Token(token_kinds.int_kw), Token(token_kinds.main),
                      Token(token_kinds.open_paren),
                      Token(token_kinds.close_paren),
                      Token(token_kinds.open_brack)]
        return start_main + tokens + [Token(token_kinds.close_brack)]


class GeneralTests(ParserTestUtil):
    """General tests of the parser."""

    def test_main_function(self):  # noqa: D400, D403
        """int main() { return 15; }"""
        tokens = [Token(token_kinds.return_kw),
                  Token(token_kinds.number, "15"),
                  Token(token_kinds.semicolon)]

        self.assertParsesTo(tokens, [
            tree.ReturnNode(tree.NumberNode(Token(token_kinds.number, "15")),
                            Token(token_kinds.return_kw))
        ])  # yapf: disable

    def test_multiple_returns_in_main_function(self):  # noqa: D400, D403
        """int main() { return 15; return 10; }"""
        tokens = [
            Token(token_kinds.return_kw), Token(token_kinds.number, "15"),
            Token(token_kinds.semicolon), Token(token_kinds.return_kw),
            Token(token_kinds.number, "10"), Token(token_kinds.semicolon)
        ]

        self.assertParsesTo(tokens, [
            tree.ReturnNode(tree.NumberNode(Token(token_kinds.number, "15")),
                            Token(token_kinds.return_kw)),
            tree.ReturnNode(tree.NumberNode(Token(token_kinds.number, "10")),
                            Token(token_kinds.return_kw))
        ])  # yapf: disable

    def test_extra_tokens_at_end_after_main_function(self):  # noqa: D400, D403
        """int main() { return 15; } a"""
        tokens = [
            Token(token_kinds.int_kw), Token(token_kinds.main),
            Token(token_kinds.open_paren), Token(token_kinds.close_paren),
            Token(token_kinds.open_brack), Token(token_kinds.return_kw),
            Token(token_kinds.number, "15"), Token(token_kinds.semicolon),
            Token(token_kinds.close_brack), Token(token_kinds.identifier, "a")
        ]

        Parser(tokens).parse()
        self.assertIssues(["unexpected token at 'a'"])

    def test_missing_semicolon_and_end_brace(self):  # noqa: D400, D403
        """int main() { return 15"""
        tokens = [Token(token_kinds.int_kw), Token(token_kinds.main),
                  Token(token_kinds.open_paren),
                  Token(token_kinds.close_paren),
                  Token(token_kinds.open_brack), Token(token_kinds.return_kw),
                  Token(token_kinds.number, "15")]

        Parser(tokens).parse()
        self.assertIssues(["expected semicolon after '15'"])

    def test_missing_semicolon_after_number(self):  # noqa: D400, D403
        """int main() { return 15 }"""
        tokens = [
            Token(token_kinds.return_kw), Token(token_kinds.number, "15")
        ]

        self.assertParserError(tokens, "expected semicolon after '15'")

    def test_missing_final_brace_main(self):  # noqa: D400, D403
        """int main() { return 15;"""
        tokens = [
            Token(token_kinds.int_kw), Token(token_kinds.main),
            Token(token_kinds.open_paren), Token(token_kinds.close_paren),
            Token(token_kinds.open_brack), Token(token_kinds.return_kw),
            Token(token_kinds.number, "15"), Token(token_kinds.semicolon)
        ]

        Parser(tokens).parse()
        self.assertIssues(["expected '}' after ';'"])

    def test_declaration_before_and_after_main(self):  # noqa: D400, D403
        """int a; int main() { int b; } int c;"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "a"),
                  Token(token_kinds.semicolon),

                  Token(token_kinds.int_kw),
                  Token(token_kinds.main),
                  Token(token_kinds.open_paren),
                  Token(token_kinds.close_paren),
                  Token(token_kinds.open_brack),

                  Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "b"),
                  Token(token_kinds.semicolon),

                  Token(token_kinds.close_brack),

                  Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "c"),
                  Token(token_kinds.semicolon)]

        a_tok = Token(token_kinds.identifier, "a")
        b_tok = Token(token_kinds.identifier, "b")
        c_tok = Token(token_kinds.identifier, "c")

        ast_root = Parser(tokens).parse()
        self.assertEqual(ast_root,
                         tree.RootNode([

                             tree.DeclarationNode(
                                 [Root([Token(token_kinds.int_kw)],
                                  Identifier(a_tok))],
                                 [None]),

                             tree.MainNode(
                                 tree.CompoundNode([tree.DeclarationNode(
                                     [Root([Token(token_kinds.int_kw)],
                                      Identifier(b_tok))],
                                     [None])]
                                 )),

                             tree.DeclarationNode(
                                 [Root([Token(token_kinds.int_kw)],
                                       Identifier(c_tok))],
                                 [None]),
                         ]))


    def test_declaration_in_main(self):  # noqa: D400, D403
        """int main() { int var; }"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.semicolon)]
        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                 Identifier(Token(token_kinds.identifier, "var")))],
                [None])
        ])

    def test_equals_in_main(self):  # noqa: D400, D403
        """int main() { a = 10; }"""
        # This wouldn't compile, but it should still parse.
        tokens = [
            Token(token_kinds.identifier, "a"), Token(token_kinds.equals),
            Token(token_kinds.number, "10"), Token(token_kinds.semicolon)
        ]

        self.assertParsesTo(tokens, [
            tree.ExprStatementNode(
                tree.BinaryOperatorNode(
                    tree.IdentifierNode(Token(token_kinds.identifier, "a")),
                    Token(token_kinds.equals),
                    tree.NumberNode(Token(token_kinds.number, "10"))
                ))])  # yapf: disable

    def test_compound_statement(self):  # noqa: D400, D403
        """int main() { { return 15; return 20; } return 25; }"""
        tokens = [
            Token(token_kinds.open_brack), Token(token_kinds.return_kw),
            Token(token_kinds.number, "15"), Token(token_kinds.semicolon),
            Token(token_kinds.return_kw), Token(token_kinds.number, "20"),
            Token(token_kinds.semicolon), Token(token_kinds.close_brack),
            Token(token_kinds.return_kw), Token(token_kinds.number, "25"),
            Token(token_kinds.semicolon)
        ]

        self.assertParsesTo(tokens, [
            tree.CompoundNode([
                tree.ReturnNode(tree.NumberNode(
                    Token(token_kinds.number, "15")),
                    Token(token_kinds.return_kw)),
                tree.ReturnNode(tree.NumberNode(
                    Token(token_kinds.number, "20")),
                    Token(token_kinds.return_kw))
            ]),
            tree.ReturnNode(tree.NumberNode(Token(token_kinds.number, "25")),
                            Token(token_kinds.return_kw))
        ])  # yapf: disable

    def test_one_line_if_statement(self):  # noqa: D400, D403
        """int main() { if(a) return 10; return 5; }"""
        tokens = [
            Token(token_kinds.if_kw), Token(token_kinds.open_paren),
            Token(token_kinds.identifier, "a"), Token(token_kinds.close_paren),
            Token(token_kinds.return_kw), Token(token_kinds.number, "10"),
            Token(token_kinds.semicolon), Token(token_kinds.return_kw),
            Token(token_kinds.number, "5"), Token(token_kinds.semicolon)
        ]

        self.assertParsesTo(tokens, [
            tree.IfStatementNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "a")),
                tree.ReturnNode(tree.NumberNode(
                    Token(token_kinds.number, "10")),
                    Token(token_kinds.return_kw)), None),
            tree.ReturnNode(
                tree.NumberNode(Token(token_kinds.number, "5")),
                Token(token_kinds.return_kw))
        ])  # yapf: disable

    def test_if_else_statement(self):  # noqa: D400, D403'
        """if(a) return 10; else return 2;"""
        tokens = [
            Token(token_kinds.if_kw), Token(token_kinds.open_paren),
            Token(token_kinds.identifier, "a"), Token(token_kinds.close_paren),
            Token(token_kinds.return_kw), Token(token_kinds.number, "10"),
            Token(token_kinds.semicolon),

            Token(token_kinds.else_kw), Token(token_kinds.return_kw),
            Token(token_kinds.number, "2"), Token(token_kinds.semicolon)
        ]

        self.assertParsesTo(tokens, [
            tree.IfStatementNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "a")),
                tree.ReturnNode(tree.NumberNode(
                    Token(token_kinds.number, "10")),
                    Token(token_kinds.return_kw)),
                tree.ReturnNode(tree.NumberNode(
                    Token(token_kinds.number, "2")),
                    Token(token_kinds.return_kw)))
        ])  # yapf: disable

    def test_compound_if_statement(self):  # noqa: D400, D403
        """int main() { if(a) {return 15; return 20;} return 25; }"""
        tokens = [
            Token(token_kinds.if_kw), Token(token_kinds.open_paren),
            Token(token_kinds.identifier, "a"), Token(token_kinds.close_paren),
            Token(token_kinds.open_brack), Token(token_kinds.return_kw),
            Token(token_kinds.number, "15"), Token(token_kinds.semicolon),
            Token(token_kinds.return_kw), Token(token_kinds.number, "20"),
            Token(token_kinds.semicolon), Token(token_kinds.close_brack),
            Token(token_kinds.return_kw), Token(token_kinds.number, "25"),
            Token(token_kinds.semicolon)
        ]

        self.assertParsesTo(tokens, [
            tree.IfStatementNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "a")),
                tree.CompoundNode([
                    tree.ReturnNode(tree.NumberNode(
                        Token(token_kinds.number, "15")),
                        Token(token_kinds.return_kw)),
                    tree.ReturnNode(tree.NumberNode(
                        Token(token_kinds.number, "20")),
                        Token(token_kinds.return_kw))
                ]), None),
            tree.ReturnNode(
                tree.NumberNode(Token(token_kinds.number, "25")),
                Token(token_kinds.return_kw))
        ])  # yapf: disable

    def test_missing_if_statement_open_paren(self):  # noqa: D400, D403
        """int main() { if a) {return 15;} }"""
        tokens = [
            Token(token_kinds.if_kw), Token(token_kinds.identifier, "a"),
            Token(token_kinds.close_paren), Token(token_kinds.return_kw),
            Token(token_kinds.number, "15"), Token(token_kinds.semicolon)
        ]

        self.assertParserError(tokens, "expected '(' after 'if'")

    def test_missing_if_statement_conditional(self):  # noqa: D400, D403
        """int main() { if () {return 15;} }"""
        tokens = [
            Token(token_kinds.if_kw), Token(token_kinds.open_paren),
            Token(token_kinds.close_paren), Token(token_kinds.return_kw),
            Token(token_kinds.number, "15"), Token(token_kinds.semicolon)
        ]

        self.assertParserError(tokens, "expected expression, got ')'")

    def test_missing_if_statement_close_paren(self):  # noqa: D400, D403
        """int main() { if (a {return 15;} }"""
        tokens = [
            Token(token_kinds.if_kw), Token(token_kinds.open_paren),
            Token(token_kinds.identifier, "a"), Token(token_kinds.return_kw),
            Token(token_kinds.number, "15"), Token(token_kinds.semicolon)
        ]

        self.assertParserError(tokens, "expected ')' after 'a'")

    def test_end_binop(self):  # noqa: D400, D403
        """int main() { a + b"""
        tokens = [
            Token(token_kinds.int_kw), Token(token_kinds.main),
            Token(token_kinds.open_paren), Token(token_kinds.close_paren),
            Token(token_kinds.open_brack),
            Token(token_kinds.identifier, "a"),
            Token(token_kinds.plus),
            Token(token_kinds.identifier, "b")]

        Parser(tokens).parse()
        self.assertIssues(
            ["missing semicolon or malformed expression after 'b'"])


class ExpressionTests(ParserTestUtil):
    """Tests expression parsing."""

    def assertExprParsesTo(self, tokens, node):
        """Assert the given tokens are an expression that parses to node.
        The given tokens should be just the expression; no semicolon or
        whatnot.
        """
        tokens += [Token(token_kinds.semicolon)]
        node = tree.ExprStatementNode(node)
        self.assertParsesTo(tokens, [node])

    def test_sum_associative(self):  # noqa: D400, D403
        """15 + 10 + 5"""
        tokens = [Token(token_kinds.number, "1"), Token(token_kinds.plus),
                  Token(token_kinds.number, "2"), Token(token_kinds.plus),
                  Token(token_kinds.number, "3")]
        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.BinaryOperatorNode(
                tree.NumberNode(Token(token_kinds.number, "1")),
                Token(token_kinds.plus),
                tree.NumberNode(Token(token_kinds.number, "2")), ),
            Token(token_kinds.plus),
            tree.NumberNode(Token(token_kinds.number, "3"))))  # disable: yapf

    def test_product_associative(self):  # noqa: D400, D403
        """1 * 2 * 3"""
        tokens = [Token(token_kinds.number, "1"), Token(token_kinds.star),
                  Token(token_kinds.number, "2"), Token(token_kinds.star),
                  Token(token_kinds.number, "3")]
        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.BinaryOperatorNode(
                tree.NumberNode(Token(token_kinds.number, "1")),
                Token(token_kinds.star),
                tree.NumberNode(Token(token_kinds.number, "2")), ),
            Token(token_kinds.star),
            tree.NumberNode(Token(token_kinds.number, "3"))))  # disable: yapf

    def test_product_sum_order_of_operations(self):  # noqa: D400, D403
        """15 * 10 + 5 * 0"""
        tokens = [Token(token_kinds.number, "15"), Token(token_kinds.star),
                  Token(token_kinds.number, "10"), Token(token_kinds.plus),
                  Token(token_kinds.number, "5"), Token(token_kinds.star),
                  Token(token_kinds.number, "0")]

        # yapf: disable
        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.BinaryOperatorNode(
                tree.NumberNode(Token(token_kinds.number, "15")),
                Token(token_kinds.star),
                tree.NumberNode(Token(token_kinds.number, "10"))),
            Token(token_kinds.plus),
            tree.BinaryOperatorNode(
                tree.NumberNode(Token(token_kinds.number, "5")),
                Token(token_kinds.star),
                tree.NumberNode(Token(token_kinds.number, "0")))))
        # yapf: enable

    def test_div_sum_order_of_operations(self):  # noqa: D400, D403
        """15 / 10 + 5 / 1"""
        tokens = [Token(token_kinds.number, "15"), Token(token_kinds.slash),
                  Token(token_kinds.number, "10"), Token(token_kinds.plus),
                  Token(token_kinds.number, "5"), Token(token_kinds.slash),
                  Token(token_kinds.number, "1")]

        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.BinaryOperatorNode(
                tree.NumberNode(Token(token_kinds.number, "15")),
                Token(token_kinds.slash),
                tree.NumberNode(Token(token_kinds.number, "10"))),
            Token(token_kinds.plus),
            tree.BinaryOperatorNode(
                tree.NumberNode(Token(token_kinds.number, "5")),
                Token(token_kinds.slash),
                tree.NumberNode(Token(token_kinds.number, "1")))))

    def test_equals_right_associative(self):  # noqa: D400, D403
        """a = b = 10"""
        tokens = [Token(token_kinds.identifier, "a"),
                  Token(token_kinds.equals),
                  Token(token_kinds.identifier, "b"),
                  Token(token_kinds.equals), Token(token_kinds.number, "10")]

        # yapf: disable
        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.IdentifierNode(Token(token_kinds.identifier, "a")),
            Token(token_kinds.equals),
            tree.BinaryOperatorNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "b")),
                Token(token_kinds.equals),
                tree.NumberNode(Token(token_kinds.number, "10")))))
        # yapf: enable

    def test_equals_precedence_with_plus(self):  # noqa: D400, D403
        """a = b + 10"""
        tokens = [Token(token_kinds.identifier, "a"),
                  Token(token_kinds.equals),
                  Token(token_kinds.identifier, "b"), Token(token_kinds.plus),
                  Token(token_kinds.number, "10")]

        # yapf: disable
        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.IdentifierNode(Token(token_kinds.identifier, "a")),
            Token(token_kinds.equals),
            tree.BinaryOperatorNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "b")),
                Token(token_kinds.plus),
                tree.NumberNode(Token(token_kinds.number, "10")))))
        # yapf: enable

    def test_parens(self):  # noqa: D400, D403
        """5 + (10 + 15) + 20"""
        tokens = [Token(token_kinds.number, "5"), Token(token_kinds.plus),
                  Token(token_kinds.open_paren),
                  Token(token_kinds.number, "10"), Token(token_kinds.plus),
                  Token(token_kinds.number, "15"),
                  Token(token_kinds.close_paren), Token(token_kinds.plus),
                  Token(token_kinds.number, "20")]

        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.BinaryOperatorNode(
                tree.NumberNode(Token(token_kinds.number, "5")),
                Token(token_kinds.plus),
                tree.ParenExprNode(
                    tree.BinaryOperatorNode(
                        tree.NumberNode(Token(token_kinds.number, "10")),
                        Token(token_kinds.plus),
                        tree.NumberNode(Token(token_kinds.number, "15"))))),
            Token(token_kinds.plus),
            tree.NumberNode(Token(token_kinds.number, "20"))))  # yapf: disable

    def test_two_equals(self):  # noqa: D400, D403
        """a == b + 10"""
        tokens = [Token(token_kinds.identifier, "a"),
                  Token(token_kinds.twoequals),
                  Token(token_kinds.identifier, "b"), Token(token_kinds.plus),
                  Token(token_kinds.number, "10")]

        self.assertExprParsesTo(tokens, tree.BinaryOperatorNode(
            tree.IdentifierNode(Token(token_kinds.identifier, "a")),
            Token(token_kinds.twoequals),
            tree.BinaryOperatorNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "b")),
                Token(token_kinds.plus),
                tree.NumberNode(Token(token_kinds.number, "10")))))

    def test_addr_of(self):  # noqa: D400, D403
        """a = &b"""
        tokens = [Token(token_kinds.identifier, "a"),
                  Token(token_kinds.equals),
                  Token(token_kinds.amp),
                  Token(token_kinds.identifier, "b")]

        t = tree.BinaryOperatorNode(
            tree.IdentifierNode(Token(token_kinds.identifier, "a")),
            Token(token_kinds.equals),
            tree.AddrOfNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "b")),
                Token(token_kinds.amp)))

        self.assertExprParsesTo(tokens, t)

    def test_deref(self):  # noqa: D400, D403
        """a = *b"""
        tokens = [Token(token_kinds.identifier, "a"),
                  Token(token_kinds.equals),
                  Token(token_kinds.star),
                  Token(token_kinds.identifier, "b")]

        t = tree.BinaryOperatorNode(
            tree.IdentifierNode(Token(token_kinds.identifier, "a")),
            Token(token_kinds.equals),
            tree.DerefNode(
                tree.IdentifierNode(Token(token_kinds.identifier, "b")),
                Token(token_kinds.star)))

        self.assertExprParsesTo(tokens, t)

    def test_array_subsc(self):  # noqa: D400, D403
        """a[b]"""
        tokens = [Token(token_kinds.identifier, "a"),
                  Token(token_kinds.open_sq_brack),
                  Token(token_kinds.identifier, "b"),
                  Token(token_kinds.close_sq_brack)]

        t = tree.ArraySubscriptNode(
            tree.IdentifierNode(Token(token_kinds.identifier, "a")),
            tree.IdentifierNode(Token(token_kinds.identifier, "b")),
            Token(token_kinds.open_sq_brack))

        self.assertExprParsesTo(tokens, t)


class DeclarationTests(ParserTestUtil):
    """Tests declaration parsing."""

    def test_basic_int_declaration(self):  # noqa: D400, D403
        """int var;"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.semicolon)]
        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                 Identifier(Token(token_kinds.identifier, "var")))],
                [None]
            )
        ])

    def test_basic_char_declaration(self):  # noqa: D400, D403
        """char var;"""
        tokens = [Token(token_kinds.char_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.semicolon)]
        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.char_kw)],
                 Identifier(Token(token_kinds.identifier, "var")))],
                [None]
            )
        ])

    def test_int_declaration_with_init(self):  # noqa: D400, D403
        """int var = 3 + 4;"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.equals),
                  Token(token_kinds.number, "3"),
                  Token(token_kinds.plus),
                  Token(token_kinds.number, "4"),
                  Token(token_kinds.semicolon)]

        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                      Identifier(Token(token_kinds.identifier, "var")))],
                [tree.BinaryOperatorNode(
                    tree.NumberNode(Token(token_kinds.number, "3")),
                    Token(token_kinds.plus),
                    tree.NumberNode(Token(token_kinds.number, "4")),
                )]
            )
        ])

    def test_unsigned_int_declaration(self):  # noqa: D400, D403
        """unsigned int var;"""
        tokens = [Token(token_kinds.unsigned_kw),
                  Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.semicolon)]
        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.unsigned_kw),
                       Token(token_kinds.int_kw)],
                 Identifier(Token(token_kinds.identifier, "var")))],
                [None]
            )
        ])


    def test_pointer_declaration(self):  # noqa: D400, D403
        """int** a;"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.star),
                  Token(token_kinds.star),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.semicolon)]

        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                      Pointer(Pointer(
                          Identifier(Token(token_kinds.identifier, "var")))))],
                [None]
            )
        ])


    def test_array_declaration(self):  # noqa: D400, D403
        """int arr[3];"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.open_sq_brack),
                  Token(token_kinds.number, "3"),
                  Token(token_kinds.close_sq_brack),
                  Token(token_kinds.semicolon)]

        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                      Array(3,
                            Identifier(Token(token_kinds.identifier,
                                             "var"))))],
                [None]
            )
        ])

    def test_array_of_pointers_declaration(self):  # noqa: D400, D403
        """int *var[3];"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.star),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.open_sq_brack),
                  Token(token_kinds.number, "3"),
                  Token(token_kinds.close_sq_brack),
                  Token(token_kinds.semicolon)]

        tok = Token(token_kinds.identifier, "var")
        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                      Pointer(Array(3, Identifier(tok))))],
                [None]
            )
        ])

    def test_pointer_to_array_declaration(self):  # noqa: D400, D403
        """int (*var)[3];"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.open_paren),
                  Token(token_kinds.star),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.close_paren),
                  Token(token_kinds.open_sq_brack),
                  Token(token_kinds.number, "3"),
                  Token(token_kinds.close_sq_brack),
                  Token(token_kinds.semicolon)]

        tok = Token(token_kinds.identifier, "var")
        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                      Array(3, Pointer(Identifier(tok))))],
                [None]
            )
        ])

    def test_multiple_declarations(self):  # noqa: D400, D403
        """int (*var1)[3], *var2[3], var3;"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.open_paren),
                  Token(token_kinds.star),
                  Token(token_kinds.identifier, "var1"),
                  Token(token_kinds.close_paren),
                  Token(token_kinds.open_sq_brack),
                  Token(token_kinds.number, "3"),
                  Token(token_kinds.close_sq_brack),
                  Token(token_kinds.comma),

                  Token(token_kinds.star),
                  Token(token_kinds.identifier, "var2"),
                  Token(token_kinds.open_sq_brack),
                  Token(token_kinds.number, "3"),
                  Token(token_kinds.close_sq_brack),
                  Token(token_kinds.comma),

                  Token(token_kinds.identifier, "var3"),

                  Token(token_kinds.semicolon)]

        tok1 = Token(token_kinds.identifier, "var1")
        tok2 = Token(token_kinds.identifier, "var2")
        tok3 = Token(token_kinds.identifier, "var3")

        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.int_kw)],
                      Array(3, Pointer(Identifier(tok1)))),
                 Root([Token(token_kinds.int_kw)],
                      Pointer(Array(3, Identifier(tok2)))),
                 Root([Token(token_kinds.int_kw)], Identifier(tok3))],
                [None, None, None]
            )
        ])

    def test_static_int_declaration(self):  # noqa: D400, D403
        """static int var;"""
        tokens = [Token(token_kinds.static_kw),
                  Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.semicolon)]
        self.assertParsesTo(tokens, [
            tree.DeclarationNode(
                [Root([Token(token_kinds.static_kw),
                       Token(token_kinds.int_kw)],
                 Identifier(Token(token_kinds.identifier, "var")))],
                [None]
            )
        ])

    def test_mismatched_parens(self):  # noqa: D400, D403
        """int (var;"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.open_paren),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.semicolon)]

        self.assertParserError(
            tokens, "mismatched parentheses in declaration at '('")

    def test_missing_array_size(self):  # noqa: D400, D403
        """int var[];"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.identifier, "var"),
                  Token(token_kinds.open_sq_brack),
                  Token(token_kinds.close_sq_brack),
                  Token(token_kinds.semicolon)]

        self.assertParserError(
            tokens, "faulty declaration syntax at 'var'")

    def test_no_declaration(self):  # noqa: D400, D403
        """int;"""
        tokens = [Token(token_kinds.int_kw),
                  Token(token_kinds.semicolon)]

        self.assertParsesTo(tokens, [tree.DeclarationNode([], [])])
