import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, access} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {GameAssetPublisher, runtimeAssets} from '../../tools/game-package/runtime-assets.mjs';

test('standalone publication uses canonical engine and keeps browser imports local', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'pastport-assets-'));
  try {
    await new GameAssetPublisher().publish(directory);
    for (const asset of runtimeAssets) {
      await access(path.join(directory, asset.destination));
      if (asset.destination.startsWith('engine/')) {
        assert.deepEqual(await readFile(path.join(directory, asset.destination)),
          await readFile(new URL('../../' + asset.source, import.meta.url)));
      }
    }
    const session = await readFile(path.join(directory, 'session.mjs'), 'utf8');
    assert.match(session, /from '\.\/engine\/runtime.mjs'/);
    assert.match(session, /from '\.\/plugins.mjs'/);
    assert.doesNotMatch(session, /src\/pastport|prototype|\.\.\/gameplay/);
    const injection = await readFile(path.join(directory, 'scene3d-runtime.js'), 'utf8');
    assert.match(injection, /from '\.\.\/navigation_boundary.js\?v=plane-3'/);
    await assert.rejects(new GameAssetPublisher().publish(directory), {code:'EEXIST'});
  } finally { await rm(directory, {recursive:true, force:true}); }
});

test('unregistered build dependencies fail instead of escaping the standalone bundle', () => {
  const publisher = new GameAssetPublisher();
  assert.throws(() => publisher.rebaseImports("import x from '../../../private.mjs';",
    runtimeAssets.find(asset => asset.destination === 'app.mjs')), /Unregistered game dependency/);
});
