#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "parsimonious",
#   "pygls",
# ]
# ///

import bisect
import contextlib
from dataclasses import dataclass
from itertools import accumulate, chain
from typing import Iterable, Sequence

import lsprotocol.types as L
from parsimonious.exceptions import ParsimoniousError
from parsimonious.grammar import rule_grammar
from parsimonious.nodes import Node, NodeVisitor
from pygls.lsp.server import LanguageServer

type Maybe[U] = tuple[U] | tuple[()]


def maybe[U](v: U | None) -> Maybe[U]:
    """Turns an optional value into an for-loop friendly `Iterable`."""
    return () if v is None else (v,)


# NOTE: The `Point` and `Span` classes are needed because the PyGLS `Position` and
# `Range` classes are non-hashable, while Parsimony needs `Span`s as dictionary keys.


@dataclass(frozen=True, order=True)
class Point:
    line: int
    character: int

    @staticmethod
    def from_lsp(pos: L.Position):
        return Point(pos.line, pos.character)

    @property
    def lsp(self):
        return L.Position(self.line, self.character)


@dataclass(frozen=True)
class Span:
    start: Point
    end: Point

    def contains(self, point: Point) -> bool:
        return self.start <= point <= self.end

    @property
    def lsp(self) -> L.Range:
        return L.Range(self.start.lsp, self.end.lsp)


@dataclass
class Token:
    start: Point
    length: int
    type: L.SemanticTokenTypes


TOKEN_TYPE_INDEX = {type: index for index, type in enumerate(L.SemanticTokenTypes)}


class SemanticTokensEncoder:
    def __init__(self) -> None:
        self.tokens: list[Token] = []
        self.encoded: list[int] = []

    def emit(self, token: Token):
        self.tokens.append(token)

    def encode(self):
        self.tokens.sort(key=lambda token: token.start)
        self.encoded = []

        last_start_line = 0
        last_start_char = 0

        for token in self.tokens:
            delta_start_line = token.start.line - last_start_line

            # `delta_start_char` must be absolute if the current token is on a different
            # line than the last token.
            delta_start_char = (
                token.start.character
                if delta_start_line != 0
                else token.start.character - last_start_char
            )

            self.encoded.append(delta_start_line)
            self.encoded.append(delta_start_char)
            self.encoded.append(token.length)
            self.encoded.append(TOKEN_TYPE_INDEX[token.type])
            # Token modifiers, not used, always 0
            self.encoded.append(0)

            last_start_line = token.start.line
            last_start_char = token.start.character


Symbol = tuple[str, Span]


class Analyzer(NodeVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.reset()

    def reset(self):
        self.labels: dict[str, Span] = {}
        self.refs: dict[Span, str] = {}
        self.analyzed = False
        self.tokens = SemanticTokensEncoder()
        return self

    def analyze(self, node: Node):
        # Computes the character offset of the first character in each line, used for
        # converting 1D offsets to 2D points.
        lines = (node.full_text + "\0").splitlines(keepends=True)
        self.line_offsets: list[int] = list(accumulate(chain([0], map(len, lines))))

        self.visit(node)
        self.analyzed = True

    def find_symbol(self, point: Point) -> Symbol | None:
        labels = self.labels.items()
        refs = ((name, span) for span, name in self.refs.items())
        symbols = chain(labels, refs)
        return next(
            ((name, span) for name, span in symbols if span.contains(point)), None
        )

    def find_label(self, point: Point) -> Symbol | None:
        maybe_label = (
            (name, span)
            for name, _ in maybe(self.find_symbol(point))
            for span in maybe(self.labels.get(name))
        )
        return next(maybe_label, None)

    def find_refs(self, point: Point) -> Iterable[Symbol]:
        return (
            (name, span)
            for name, _ in maybe(self.find_symbol(point))
            for span, ref_name in self.refs.items()
            if ref_name == name
        )

    def ref_spans_of(self, name: str) -> Iterable[Span]:
        return (span for span, ref_name in self.refs.items() if ref_name == name)

    def definition(self, uri: str, pos: L.Position) -> Sequence[L.Location]:
        point = Point.from_lsp(pos)
        return [L.Location(uri, span.lsp) for _, span in maybe(self.find_label(point))]

    def references(self, uri: str, pos: L.Position) -> Sequence[L.Location]:
        point = Point.from_lsp(pos)
        return [L.Location(uri, span.lsp) for _, span in self.find_refs(point)]

    def document_symbol(self) -> Sequence[L.DocumentSymbol]:
        return [
            L.DocumentSymbol(
                name=name,
                kind=L.SymbolKind.Constructor,
                range=span.lsp,
                selection_range=span.lsp,
            )
            for name, span in self.labels.items()
        ]

    def document_highlight(self, pos: L.Position) -> Sequence[L.DocumentHighlight]:
        def highlights():
            for name, span in maybe(self.find_label(Point.from_lsp(pos))):
                # Highlights the definition site.
                yield L.DocumentHighlight(span.lsp, L.DocumentHighlightKind.Write)
                # Highlights all reference sites.
                yield from (
                    L.DocumentHighlight(ref_span.lsp, L.DocumentHighlightKind.Read)
                    for ref_span in self.ref_spans_of(name)
                )

        return list(highlights())

    def semantic_tokens(self) -> L.SemanticTokens:
        self.tokens.encode()
        return L.SemanticTokens(data=self.tokens.encoded)

    def prepare_rename(self, pos: L.Position) -> L.PrepareRenamePlaceholder | None:
        for name, span in maybe(self.find_symbol(Point.from_lsp(pos))):
            return L.PrepareRenamePlaceholder(span.lsp, name)

    def rename(self, uri: str, pos: L.Position, new_name: str) -> L.WorkspaceEdit:
        def text_edits():
            for name, span in maybe(self.find_label(Point.from_lsp(pos))):
                # Renames the definition site.
                yield L.TextEdit(span.lsp, new_name)
                # Renames all reference sites.
                yield from (
                    L.TextEdit(ref_span.lsp, new_name)
                    for ref_span in self.ref_spans_of(name)
                )

        return L.WorkspaceEdit(changes={uri: list(text_edits())})

    def diagnostic(self) -> L.DocumentDiagnosticReport:
        return L.RelatedFullDocumentDiagnosticReport(
            [
                L.Diagnostic(span.lsp, f'Label undefined: "{name}"')
                for span, name in self.refs.items()
                if name not in self.labels.keys()
            ]
        )

    def point_of(self, offset: int) -> Point:
        line = bisect.bisect_right(self.line_offsets, offset) - 1
        column = offset - self.line_offsets[line]
        return Point(line=line, character=column)

    def span_of(self, node: Node) -> Span:
        return Span(self.point_of(node.start), self.point_of(node.end))

    def emit_token(self, node: Node, type: L.SemanticTokenTypes):
        self.tokens.emit(Token(self.point_of(node.start), len(node.text), type))

    def generic_visit(self, node: Node, visited_children: Sequence[Node]):
        del visited_children
        return node

    def visit_comment(self, node: Node, _: Sequence[Node]):
        self.emit_token(node, L.SemanticTokenTypes.Comment)
        return node

    def _emit_operator_token(self, node: Node, visited_children: Sequence[Node]):
        op, *_ = visited_children
        self.emit_token(op, L.SemanticTokenTypes.Operator)
        return node

    visit_equals = _emit_operator_token
    visit_lookahead = _emit_operator_token
    visit_not_term = _emit_operator_token
    visit_or_term = _emit_operator_token
    visit_quantifier = _emit_operator_token

    def visit_label(self, node: Node, visited_children: Sequence[Node]):
        del node
        label, *_ = visited_children
        return label

    def visit_parenthesized(self, node: Node, visited_children: Sequence[Node]):
        lparen, _, _, rparen, *_ = visited_children
        self.emit_token(lparen, L.SemanticTokenTypes.Operator)
        self.emit_token(rparen, L.SemanticTokenTypes.Operator)
        return node

    def visit_reference(self, node: Node, visited_children: Sequence[Node]):
        label, *_ = visited_children
        self.emit_token(label, L.SemanticTokenTypes.Variable)
        self.refs[self.span_of(label)] = label.text
        return node

    def visit_regex(self, node: Node, visited_children: Sequence[Node]):
        op, literal, flags, *_ = visited_children
        self.emit_token(op, L.SemanticTokenTypes.Operator)
        self.emit_token(literal, L.SemanticTokenTypes.Regexp)
        self.emit_token(flags, L.SemanticTokenTypes.Operator)
        return node

    def visit_rule(self, node: Node, visited_children: Sequence[Node]):
        label, _, _ = visited_children
        self.emit_token(label, L.SemanticTokenTypes.Function)
        self.labels[label.text] = self.span_of(label)
        return node

    def visit_literal(self, node: Node, visited_children: Sequence[Node]):
        literal, *_ = visited_children
        self.emit_token(literal, L.SemanticTokenTypes.String)
        return node


class ParsimonyServer(LanguageServer):
    analyzer: Analyzer = Analyzer()

    @property
    def ready(self):
        return self.analyzer.analyzed


server = ParsimonyServer(
    name="parsimony",
    version="v0.1",
    text_document_sync_kind=L.TextDocumentSyncKind.Full,
)


@server.feature(L.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: ParsimonyServer, params: L.DidOpenTextDocumentParams):
    with contextlib.suppress(ParsimoniousError):
        ls.analyzer.reset().analyze(rule_grammar.parse(params.text_document.text))


@server.feature(L.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: ParsimonyServer, params: L.DidChangeTextDocumentParams):
    doc = ls.workspace.get_text_document(params.text_document.uri)
    with contextlib.suppress(ParsimoniousError):
        ls.analyzer.reset().analyze(rule_grammar.parse(doc.source))


@server.feature(L.TEXT_DOCUMENT_DEFINITION)
def definition(ls: ParsimonyServer, params: L.DefinitionParams):
    uri = params.text_document.uri
    return ls.analyzer.definition(uri, params.position) if ls.ready else []


@server.feature(L.TEXT_DOCUMENT_REFERENCES)
def references(ls: ParsimonyServer, params: L.ReferenceParams):
    uri = params.text_document.uri
    return ls.analyzer.references(uri, params.position) if ls.ready else []


@server.feature(L.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls: ParsimonyServer, _: L.DocumentSymbolParams):
    return ls.analyzer.document_symbol() if ls.ready else []


@server.feature(L.TEXT_DOCUMENT_DOCUMENT_HIGHLIGHT)
def document_highlight(ls: ParsimonyServer, params: L.DocumentHighlightParams):
    return ls.analyzer.document_highlight(params.position) if ls.ready else []


@server.feature(L.TEXT_DOCUMENT_PREPARE_RENAME)
def prepare_rename(ls: ParsimonyServer, params: L.PrepareRenameParams):
    return ls.analyzer.prepare_rename(params.position) if ls.ready else None


@server.feature(L.TEXT_DOCUMENT_RENAME)
def rename(ls: ParsimonyServer, params: L.RenameParams):
    uri = params.text_document.uri
    return ls.analyzer.rename(uri, params.position, params.new_name)


@server.feature(
    L.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    L.SemanticTokensLegend(token_types=list(L.SemanticTokenTypes), token_modifiers=[]),
)
def semantic_tokens_full(ls: ParsimonyServer, _: L.SemanticTokensParams):
    return ls.analyzer.semantic_tokens() if ls.ready else None


@server.feature(L.TEXT_DOCUMENT_DIAGNOSTIC)
def diagnostic(ls: ParsimonyServer, _: L.DocumentDiagnosticParams):
    return ls.analyzer.diagnostic() if ls.ready else None


@server.feature(L.TEXT_DOCUMENT_COMPLETION)
def completion(ls: ParsimonyServer, _: L.CompletionParams):
    names = set(ls.analyzer.labels) | set(ls.analyzer.refs.values())
    return [
        L.CompletionItem(label=name, kind=L.CompletionItemKind.Constructor)
        for name in names
    ]


if __name__ == "__main__":
    server.start_io()
