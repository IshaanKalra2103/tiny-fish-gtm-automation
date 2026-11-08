// Slim the installed `paperclipai` npm tree for the GTM harness.
//
//   node slim.mjs /usr/local/lib/node_modules/paperclipai
//
// Keeps: server core (API, issues/kanban, routing/wakes, approvals, budgets, secrets,
// skills, AI connections), adapters process/http/claude_local/codex_local (other
// adapter packages are tiny and wired into the registry, so they stay but get
// disabled via the API), the imessage-photon chat channel, and the AgentMail channel.
//
// Removes heavy integrations we don't use, then puts a generated stub package in
// their place. Every binding the remaining code imports from a removed package
// still resolves (so the server boots), and throws only if that feature is used:
//   - Discord / Slack / Teams / Telegram / GitHub chat adapters and their SDKs
//   - Cursor SDK (cursor adapters), AWS SDK (S3 storage / AWS secrets),
//     Vercel Connect, three.js (avatar renderer)
//   - native binaries for other CPU architectures
// It also strips source maps, type declarations, tests and READMEs.
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.argv[2] ?? "/usr/local/lib/node_modules/paperclipai");
const REMOVE = [
  /^@chat-adapter\/(discord|slack|teams|telegram|github)$/,
  /^discord\.js$/, /^discord-api-types$/, /^@discordjs\//, /^@sapphire\//, /^@vladfrangu\//,
  /^@microsoft\/teams\./, /^@azure\/msal-/, /^@slack\//, /^@octokit\//,
  /^@cursor\//,
  /^@aws-sdk\//, /^@aws-crypto\//, /^@smithy\//,
  /^@vercel\//,
  /^three$/,
];
const ARCH = process.arch === "arm64" ? "arm64" : "x64";
const OTHER_ARCH = ARCH === "arm64" ? /(^|[-_])(x64|x86_64|amd64|ia32)([-_]|$)/ : /(^|[-_])(arm64|aarch64)([-_]|$)/;
const OTHER_OS = /(^|[-_])(darwin|win32|windows|freebsd|android|sunos|aix|openbsd)([-_]|$)/;
// Native-binary package families where the platform is encoded in the package name.
const NATIVE_FAMILIES = /^(@esbuild|@img|@embedded-postgres|@openai|@anthropic-ai|@rollup|@swc|@next|@heif2jpeg|@cursor|@parcel|@biomejs)\//;

const du = (p) => {
  let n = 0;
  const st = fs.lstatSync(p, { throwIfNoEntry: false });
  if (!st) return 0;
  if (st.isDirectory()) for (const e of fs.readdirSync(p)) n += du(path.join(p, e));
  else n += st.size;
  return n;
};
const mb = (b) => `${(b / 1048576).toFixed(1)}MB`;

// ── 1. find every package dir in the tree ────────────────────────────────
function* packageDirs(nodeModules) {
  if (!fs.existsSync(nodeModules)) return;
  for (const e of fs.readdirSync(nodeModules)) {
    if (e.startsWith(".")) continue;
    const p = path.join(nodeModules, e);
    if (e.startsWith("@")) {
      for (const s of fs.readdirSync(p)) yield [`${e}/${s}`, path.join(p, s)];
    } else yield [e, p];
  }
}
function* allPackages(dir) {
  for (const [name, p] of packageDirs(path.join(dir, "node_modules"))) {
    yield [name, p];
    yield* allPackages(p);
  }
}

const removedNames = new Set();
let removedBytes = 0;
for (const [name, p] of [...allPackages(ROOT)]) {
  const bare = name.split("/").pop();
  const wrongPlatform = NATIVE_FAMILIES.test(name) && (OTHER_ARCH.test(bare) || OTHER_OS.test(bare));
  if (REMOVE.some((re) => re.test(name)) || wrongPlatform) {
    if (!fs.existsSync(p)) continue;
    const b = du(p);
    fs.rmSync(p, { recursive: true, force: true });
    removedBytes += b;
    if (!wrongPlatform) removedNames.add(name);
    console.log(`[slim] removed ${name} (${mb(b)})${wrongPlatform ? " [other platform]" : ""}`);
  }
}

// ── 2. strip non-runtime files ───────────────────────────────────────────
let strippedBytes = 0;
const STRIP_FILE = /(\.map|\.d\.ts|\.d\.mts|\.d\.cts|\.test\.[cm]?js|\.spec\.[cm]?js|\.tsbuildinfo)$/i;
const STRIP_DOC = /^(readme|changelog|history)(\.(md|markdown|txt))?$/i;
const STRIP_DIR = /^(__tests__|__mocks__|\.github)$/;
const KEEP_DOCS_IN = /[\/](skills|skills-catalog|teams-catalog|catalog|templates)[\/]/;  // runtime content
function strip(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (STRIP_DIR.test(e.name)) { strippedBytes += du(p); fs.rmSync(p, { recursive: true, force: true }); continue; }
      strip(p);
    } else if (e.isFile() && (STRIP_FILE.test(e.name) || (STRIP_DOC.test(e.name) && !KEEP_DOCS_IN.test(p)))) {
      strippedBytes += fs.statSync(p).size;
      fs.rmSync(p);
    }
  }
}
strip(ROOT);

// ── 3. find what remaining code still imports from removed packages ──────
const removedRe = [...removedNames].map((n) => n.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")).join("|");
const SPEC = new RegExp(`^(${removedRe})(/.*)?$`);
const IMPORT = /\bimport\s+([\w$*{}\s,]+?)\s+from\s*["']([^"']+)["']/g;
const EXPORT_FROM = /\bexport\s+(\*(?:\s+as\s+[\w$]+)?|\{[^}]*\})\s+from\s*["']([^"']+)["']/g;
const BARE = /\b(?:import\s*\(|require\s*\(|import\s+)\s*["']([^"']+)["']/g;
const need = new Map(); // pkg -> {names:Set, subpaths:Set}
const want = (spec) => {
  const m = SPEC.exec(spec);
  if (!m) return null;
  if (!need.has(m[1])) need.set(m[1], { names: new Set(), subpaths: new Set() });
  const entry = need.get(m[1]);
  if (m[2]) entry.subpaths.add(m[2]);
  return entry;
};
const addNamed = (entry, clause) => {
  const brace = clause.match(/\{([^}]*)\}/);
  if (!brace) return;
  for (let part of brace[1].split(",")) {
    part = part.trim().replace(/^type\s+/, "");
    if (!part) continue;
    const orig = part.split(/\s+as\s+/)[0].trim();
    if (/^[A-Za-z_$][\w$]*$/.test(orig) && orig !== "default") entry.names.add(orig);
  }
};
function scan(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { scan(p); continue; }
    if (!/\.(c|m)?js$/.test(e.name)) continue;
    const src = fs.readFileSync(p, "utf8");
    if (!SPEC.source || !removedNames.size) continue;
    for (const re of [IMPORT, EXPORT_FROM]) {
      re.lastIndex = 0;
      for (let m; (m = re.exec(src));) { const ent = want(m[2]); if (ent) addNamed(ent, m[1]); }
    }
    BARE.lastIndex = 0;
    for (let m; (m = BARE.exec(src));) want(m[1]);
  }
}
if (removedNames.size) scan(ROOT);

// ── 4. write stub packages for anything still referenced ─────────────────
const CORE = `// Inert stand-in: resolves every import, survives load-time use (new X(), X.y, calls),
// and warns once per symbol the first time something actually uses it.
const warned = new Set();
const warn = (what) => {
  if (warned.has(what)) return;
  warned.add(what);
  console.warn("[gtm-harness slim build] " + what + " is not included in this image (inert stub)");
};
export function stub(what) {
  const target = function () {};
  return new Proxy(target, {
    get(t, prop) {
      if (prop === "prototype") return t.prototype;
      if (prop === "then") return undefined;
      if (prop === Symbol.toPrimitive) return () => "[removed " + what + "]";
      if (prop === Symbol.iterator || prop === Symbol.asyncIterator) return undefined;
      if (prop === "__esModule") return true;
      if (prop === "toJSON") return () => null;
      return stub(what + "." + String(prop));
    },
    apply() { warn(what); return stub(what + "()"); },
    construct() { warn(what); return stub("new " + what); },
  });
}
`;
const ident = /^[A-Za-z_$][\w$]*$/;
for (const [pkg, { names, subpaths }] of need) {
  const dir = path.join(ROOT, "node_modules", ...pkg.split("/"));
  fs.mkdirSync(dir, { recursive: true });
  const exportsMap = { ".": { import: "./index.mjs", require: "./index.cjs", default: "./index.mjs" } };
  for (const sp of subpaths) exportsMap[`.${sp}`] = exportsMap["."];
  fs.writeFileSync(path.join(dir, "package.json"), JSON.stringify({
    name: pkg, version: "0.0.0-gtm-slim", description: "Stub: removed from the GTM harness slim build",
    main: "./index.cjs", module: "./index.mjs", exports: exportsMap,
  }, null, 2));
  fs.writeFileSync(path.join(dir, "core.mjs"), CORE);
  const named = [...names].filter((n) => ident.test(n));
  fs.writeFileSync(path.join(dir, "index.mjs"),
    `import { stub } from "./core.mjs";\nexport default stub(${JSON.stringify(pkg)});\n` +
    named.map((n) => `export const ${n} = stub(${JSON.stringify(`${pkg}.${n}`)});`).join("\n") + "\n");
  fs.writeFileSync(path.join(dir, "index.cjs"),
    `const stub = (w) => new Proxy(function () {}, { get: (t, p) => p === "prototype" ? t.prototype : p === "then" ? undefined : p === "__esModule" ? true : stub(w + "." + String(p)), apply: () => stub(w + "()"), construct: () => stub("new " + w) });\n` +
    `module.exports = stub(${JSON.stringify(pkg)});\n`);
  console.log(`[slim] stubbed ${pkg} (${named.length} named exports, ${subpaths.size} subpaths)`);
}

console.log(`[slim] removed ${removedNames.size} packages: ${mb(removedBytes)}; stripped ${mb(strippedBytes)}; stubs ${need.size}`);
console.log(`[slim] remaining tree: ${mb(du(ROOT))}`);
