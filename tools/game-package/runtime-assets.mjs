/** Publish production sources into the stable standalone-game layout. */
import {readFile, writeFile, mkdir, lstat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const frontend = ['index.html','app.mjs','app.css','dialogue.mjs','session.mjs',
  'investigation-view.mjs','slice-continuation.mjs','navigation.mjs','walkmesh.mjs','interaction.mjs','cinematic-view.mjs',
  'scene3d-view.mjs','scene-preparation.mjs','scene3d-runtime.js','scene3d-navigation.mjs','scene3d-bridge.mjs'];
const plugins = ['plugins.mjs','investigation.mjs','coverage.mjs','gameplay-catalog.mjs'];
const engine = ['actions.mjs','context.mjs','errors.mjs','generated-schemas.mjs',
  'rules.mjs','runtime.mjs','validation.mjs'];

export const runtimeAssets = Object.freeze([
  ...frontend.map(name => ({source:`frontend/game/${name}`,destination:name})),
  ...plugins.map(name => ({source:`gameplay/plugins/${name}`,destination:name})),
  {source:'gameplay/gameplay.mjs',destination:'gameplay.mjs'},
  {source:'tools/game-package/serve3d.mjs',destination:'serve3d.mjs'},
  ...engine.map(name => ({source:`src/pastport/player/${name}`,destination:`engine/${name}`})),
].map(asset => Object.freeze(asset)));

/** Sources have one owner; output copies retain the existing browser import layout. */
export class GameAssetPublisher {
  constructor(root = new URL('../../', import.meta.url)) {
    this.root = root;
    this.destinations = new Map(runtimeAssets.map(asset =>
      [new URL(asset.source, root).href, asset.destination]));
  }
  rebaseImports(source, asset) {
    // The server appends this script inside each world viewer; its imports are world-relative.
    if (asset.destination === 'scene3d-runtime.js' || asset.destination.startsWith('engine/')) return source;
    const origin = new URL(asset.source, this.root);
    return source.replace(/^(\s*(?:import|export)\b[^\r\n]*?\bfrom\s*|\s*import\s*)(['"])(\.[^'"\n]+)\2/gm,
      (match, prefix, quote, specifier) => {
        const dependency = new URL(specifier, origin);
        const suffix = dependency.search + dependency.hash;
        dependency.search = ''; dependency.hash = '';
        const destination = this.destinations.get(dependency.href);
        if (!destination) throw new Error(`Unregistered game dependency: ${asset.source}: ${specifier}`);
        let relative = path.posix.relative(path.posix.dirname(asset.destination), destination);
        if (!relative.startsWith('.')) relative = './' + relative;
        return prefix + quote + relative + suffix + quote;
      });
  }
  async publish(directory) {
    for (const asset of runtimeAssets) {
      const source = new URL(asset.source, this.root);
      const info = await lstat(fileURLToPath(source));
      if (!info.isFile() || info.isSymbolicLink()) throw new Error('Game source must be a regular file');
      const bytes = await readFile(source);
      const contents = /\.(?:mjs|js)$/.test(asset.source)
        ? this.rebaseImports(bytes.toString('utf8'), asset) : bytes;
      const destination = path.join(directory, asset.destination);
      await mkdir(path.dirname(destination), {recursive:true});
      await writeFile(destination, contents, {flag:'wx'});
    }
  }
}
