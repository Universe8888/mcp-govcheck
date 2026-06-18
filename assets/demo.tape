# vhs tape — animated demo gif for mcp-govcheck
# Install vhs (https://github.com/charmbracelet/vhs), then:  vhs assets/demo.tape
# Produces assets/demo.gif. Run from the repo root.

Output assets/demo.gif

Set FontSize 16
Set Width 1100
Set Height 640
Set Theme "GitHub Dark"
Set Padding 18

Type "mcp-govcheck scan --server 'python examples/asset_store_server.py'"
Enter
Sleep 3s

Type "mcp-govcheck attest examples/sample_calls.jsonl"
Enter
Sleep 4s
