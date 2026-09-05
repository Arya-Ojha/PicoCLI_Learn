# Extend pico for the sovereign workbench

pico was a CLI coding agent; the sovereign workbench needs the same session and tool core for industrial knowledge work. We decided to extend pico in place under one CONTEXT.md rather than fork a new product, so routing, cwd-jail, corpus, and trace reuse the existing session tree instead of rebuilding it.
