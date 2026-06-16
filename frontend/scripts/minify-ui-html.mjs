import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { transform as transformCss } from "lightningcss";
import { transform as transformJs } from "esbuild";

const uiDistDir = resolve(process.cwd(), "dist", "ui");

const INLINE_STYLE_REGEX = /<style\b([^>]*)>([\s\S]*?)<\/style>/gi;
const INLINE_SCRIPT_REGEX = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
const HTML_COMMENT_REGEX = /<!--[\s\S]*?-->/g;

function isConditionalComment(comment) {
  return /^\s*<!--\s*\[if[\s\S]*?<!\s*\[endif\s*\]\s*-->\s*$/i.test(comment);
}

function compactHtml(html) {
  return html
    .replace(HTML_COMMENT_REGEX, (comment) => (isConditionalComment(comment) ? comment : ""))
    .replace(/>\s+</g, "><")
    .trim();
}

function minifyInlineCss(css, filename) {
  try {
    const result = transformCss({
      filename,
      code: Buffer.from(css),
      minify: true,
    });
    return result.code.toString();
  } catch {
    return css.trim();
  }
}

async function minifyInlineJs(js) {
  try {
    const result = await transformJs(js, {
      loader: "js",
      minify: true,
      legalComments: "none",
      target: "es2020",
    });
    return result.code.trim();
  } catch {
    return js.trim();
  }
}

async function minifyUiHtmlFiles() {
  let entries;
  try {
    entries = await readdir(uiDistDir, { withFileTypes: true });
  } catch (error) {
    if (error && error.code === "ENOENT") {
      console.log("[minify-ui-html] dist/ui not found, skipping");
      return;
    }
    throw error;
  }
  const htmlFiles = entries
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".html"))
    .map((entry) => join(uiDistDir, entry.name));

  if (htmlFiles.length === 0) {
    console.log("[minify-ui-html] No HTML files found in dist/ui");
    return;
  }

  await Promise.all(
    htmlFiles.map(async (filePath) => {
      const html = await readFile(filePath, "utf8");
      let transformed = html.replace(INLINE_STYLE_REGEX, (fullMatch, attrs, css) => {
        const minifiedCss = minifyInlineCss(css, `${filePath}#inline-style`);
        return `<style${attrs}>${minifiedCss}</style>`;
      });

      const scriptMatches = [...transformed.matchAll(INLINE_SCRIPT_REGEX)];
      for (const match of scriptMatches) {
        const [fullMatch, attrs, scriptBody] = match;
        const minifiedScript = await minifyInlineJs(scriptBody);
        transformed = transformed.replace(fullMatch, `<script${attrs}>${minifiedScript}</script>`);
      }

      const minifiedHtml = compactHtml(transformed);
      await writeFile(filePath, `${minifiedHtml}\n`, "utf8");
    }),
  );

  console.log(`[minify-ui-html] Minified ${htmlFiles.length} UI HTML files`);
}

minifyUiHtmlFiles().catch((error) => {
  console.error("[minify-ui-html] Failed:", error);
  process.exitCode = 1;
});
