# Parsimony

A minimal single-file language server for [Parsimonious][parsimonious] grammars, built on top of [PyGLS][pygls] and, of course, Parsimonious.

## Getting Started

Parsimony is a [PEP 723][pep-723] Python script that runs via [`uv`][uv]. For a quick try, [`init.lua`](./init.lua) provides a minimal [Neovim][neovim] config. Run it against [`parsimonious.grammar`](./parsimonious.grammar), the Parsimonious meta-grammar, and navigate with the [default Neovim LSP keymaps][lsp-keymaps]:

```bash
nvim --clean -u init.lua parsimonious.grammar
```

For daily use, download the `parsimony` script and replace the GitHub URL in `init.lua` with its local path.

## Features

- [`textDocument/definition`][lsp-definition]: Jump to a rule's definition.
- [`textDocument/references`][lsp-references]: List all references to a rule.
- [`textDocument/prepareRename`][lsp-prepareRename] and [`textDocument/rename`][lsp-rename]: Rename a rule.
- [`textDocument/completion`][lsp-completion]: Auto-complete rule labels.
- [`textDocument/documentSymbol`][lsp-documentSymbol]: Outline all rules in the document.
- [`textDocument/documentHighlight`][lsp-documentHighlight]: Highlight a rule's definition and references.
- [`textDocument/semanticTokens/full`][lsp-semanticTokens]: Semantic highlighting.
- [`textDocument/diagnostic`][lsp-diagnostic]: Flag undefined rule references.

[parsimonious]: https://github.com/erikrose/parsimonious
[pygls]: https://github.com/openlawlibrary/pygls
[pep-723]: https://peps.python.org/pep-0723/
[uv]: https://docs.astral.sh/uv/
[neovim]: https://neovim.io/
[lsp-definition]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_definition
[lsp-references]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_references
[lsp-prepareRename]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_prepareRename
[lsp-rename]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_rename
[lsp-completion]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_completion
[lsp-documentSymbol]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_documentSymbol
[lsp-documentHighlight]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_documentHighlight
[lsp-semanticTokens]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_semanticTokens
[lsp-diagnostic]: https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_diagnostic
[lsp-keymaps]: https://neovim.io/doc/user/lsp/#gra
