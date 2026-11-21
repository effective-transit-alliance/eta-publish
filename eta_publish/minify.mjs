// The `.min` copies of the stylesheets and the script, for `minify.py`.
//
// `lightningcss` for the stylesheets and `oxc` for the script,
// through their JavaScript APIs, since neither package has a command line.
// One run of `bun` for all three, since starting it is most of what this costs.
// Both are found in the repository's `node_modules/`, at the versions `bun.lock` pins,
// which is where an import from this file looks.
//
// Each gets a source map carrying the file as written, named as it sits beside the copy,
// so a browser's tools show it with its comments without the original being served.
//
// Usage: bun minify.mjs <directory> <file>...

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { transform } from "lightningcss";
import { minify } from "oxc-minify";

const [directory, ...files] = process.argv.slice(2);

for (const file of files) {
	const source = readFileSync(join(directory, file), "utf8");
	const out = file.replace(/\.(css|js)$/, ".min.$1");
	let code;
	let map;
	if (file.endsWith(".css")) {
		const result = transform({
			filename: file,
			code: Buffer.from(source),
			minify: true,
			sourceMap: true,
		});
		for (const warning of result.warnings) {
			console.error(`${file}: ${warning.message}`);
		}
		code = `${result.code}\n/*# sourceMappingURL=${out}.map */\n`;
		map = JSON.parse(result.map.toString());
	} else {
		const result = await minify(file, source, { sourcemap: true });
		if (result.errors.length) {
			throw new Error(
				`${file}: ${result.errors.map((e) => e.message).join("\n")}`,
			);
		}
		code = `${result.code}\n//# sourceMappingURL=${out}.map\n`;
		map = result.map;
	}
	map.sources = [file];
	map.sourcesContent = [source];
	writeFileSync(join(directory, out), code);
	writeFileSync(join(directory, `${out}.map`), JSON.stringify(map));
}
