// The `.min` copies of the stylesheets and the script, for `minify.py`.
//
// `lightningcss` for the stylesheets and `oxc` for the script,
// through their Node APIs: `oxc` has no command line,
// and `lightningcss`'s is a placeholder until an install script `mise` does not run replaces it.
// One run of Node for all three, since starting it is most of what this costs.
//
// Each gets a source map carrying the file as written, named as it sits beside the copy,
// so a browser's tools show it with its comments without the original being served.
//
// Usage: node minify.mjs <lightningcss install> <oxc-minify install> <directory> <file>...
// where an install is what `mise where` says, holding `node_modules/<package>`.

import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [lightningcssDir, oxcDir, directory, ...files] = process.argv.slice(2);

const { transform } = createRequire(join(lightningcssDir, "package.json"))(
	"lightningcss",
);
const oxc = createRequire(join(oxcDir, "package.json")).resolve("oxc-minify");
const { minify } = await import(pathToFileURL(oxc).href);

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
