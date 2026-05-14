-- Associates the ".grammar" extension to the "parsimonious" file type.
vim.filetype.add({
	extension = {
		grammar = "parsimonious",
	},
})

vim.lsp.config["parsimonious"] = {
	cmd = {
		"uv",
		"run",
		"--script",
		-- NOTE: Please replace this URL with a local path for daily use.
		"https://raw.githubusercontent.com/liancheng/parsimony/refs/heads/master/parsimony.py",
	},
	filetypes = { "parsimonious" },
	root_dir = nil,
}

vim.lsp.enable("parsimonious")
