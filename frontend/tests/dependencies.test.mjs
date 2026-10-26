import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const root = new URL("../", import.meta.url);
const manifest = JSON.parse(await readFile(new URL("package.json", root), "utf8"));
const lock = JSON.parse(await readFile(new URL("package-lock.json", root), "utf8"));
const nextRequire = createRequire(require.resolve("next/package.json"));

function atLeast(actual, minimum) {
  assert.match(actual, /^\d+\.\d+\.\d+$/, "Expected a stable dependency version");
  const current = actual.split(".").map(Number);
  const floor = minimum.split(".").map(Number);
  for (let i = 0; i < floor.length; i += 1) {
    if (current[i] !== floor[i]) return current[i] > floor[i];
  }
  return true;
}

test("the lockfile does not retain vulnerable copies of patched dependencies", () => {
  const minimums = {
    next: "15.5.28",
    react: "19.1.10",
    "react-dom": "19.1.10",
    sharp: "0.35.5",
    postcss: "8.5.32",
    nanoid: "3.3.18",
    "source-map-js": "1.2.2",
    browserslist: "4.28.7",
    "baseline-browser-mapping": "2.11.0",
    "postcss-selector-parser": "6.1.5",
  };
  for (const [name, minimum] of Object.entries(minimums)) {
    const copies = Object.entries(lock.packages).filter(([path]) => path.endsWith(`/node_modules/${name}`) || path === `node_modules/${name}`);
    assert.ok(copies.length, `${name} must be present in the lockfile`);
    for (const [path, entry] of copies) {
      assert.ok(atLeast(entry.version, minimum), `${path}@${entry.version} must be at least ${minimum}`);
    }
  }
});

test("Next resolves the patched PostCSS override and processes Tailwind CSS", async () => {
  // Next 15 pins an older PostCSS. Keep the scoped override until upstream
  // supplies a patched version; updating only our direct dev dependency is insufficient.
  assert.equal(nextRequire("postcss/package.json").version, manifest.devDependencies.postcss);
  const postcss = nextRequire("postcss");
  const tailwindcss = require("tailwindcss");
  const autoprefixer = require("autoprefixer");
  const result = await postcss([
    tailwindcss({ content: [{ raw: '<div class="flex select-none"></div>' }] }),
    autoprefixer({ overrideBrowserslist: ["Safari 9"] }),
  ]).process("@tailwind utilities;", { from: undefined });
  assert.match(result.css, /display:\s*flex/);
  assert.match(result.css, /-webkit-user-select:\s*none/);
});

test("Next resolves patched Sharp and can optimize the checked-in brand image", async () => {
  const sharp = nextRequire("sharp");
  assert.ok(atLeast(sharp.versions.sharp, "0.35.5"));
  const input = await readFile(new URL("public/brand/raven-square-logo.png", root));
  const { data, info } = await sharp(input).resize({ width: 64 }).webp().toBuffer({ resolveWithObject: true });
  assert.equal(info.width, 64);
  assert.equal(info.format, "webp");
  assert.ok(data.length > 0);
});
