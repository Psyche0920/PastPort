import {Activity} from './plugins/plugins.mjs';
import {contentHash} from '../src/pastport/player/validation.mjs';

const definitions = new Map([
  ...['spot-difference','timeline','image-puzzle','scene-search'].map(kind=>[kind,{pluginId:'pastport.activity.'+kind,version:'1.0.0'}]),
  ['question', {pluginId:'pastport.activity.question', version:'1.0.0'}],
  ['routing', {pluginId:'pastport.activity.routing', version:'1.0.0'}],
  ['dialogue', {pluginId:'pastport.activity.dialogue', version:'1.0.0'}],
  ['tiling', {pluginId:'pastport.activity.tiling', version:'1.0.0'}],
  ['budget', {pluginId:'pastport.activity.budget', version:'1.0.0'}],
]);

/** Resolve authored task intent to a pinned local activity and exact task ID. */
export async function prepareGameplayPlan(pkg, presentation) {
  ensure(pkg?.game?.scenes && Array.isArray(pkg.game.scenes), 'Runtime game is required');
  ensure(Array.isArray(presentation?.chapters), 'Story chapters are required');
  const scenes = new Map(pkg.game.scenes.map(scene => [scene.scene_id, scene]));
  const chapters = new Map(presentation.chapters.map(chapter => [chapter.id, chapter]));
  ensure(scenes.size === pkg.game.scenes.length, 'Duplicate runtime scene ID');
  ensure(chapters.size === presentation.chapters.length, 'Duplicate presentation chapter ID');
  ensure(scenes.size === chapters.size && [...scenes.keys()].every(id => chapters.has(id)), 'Story/runtime scene identities differ');

  const bindings = [];
  const buildRequests = [];
  const taskIds = new Set();
  for (const scene of pkg.game.scenes) {
    ensure(scene.tasks.length === 1, 'Local demo host requires one task per scene');
    const task = scene.tasks[0];
    ensure(typeof task.task_id === 'string' && !taskIds.has(task.task_id), 'Missing or duplicate task ID');
    taskIds.add(task.task_id);
    const chapter = chapters.get(scene.scene_id);
    const config = chapter.plugin;
    ensure(config && typeof config.kind === 'string', 'Task mechanic request is missing');
    const definition = definitions.get(config.kind);
    if (!definition) {
      buildRequests.push({task_id:task.task_id, scene_id:scene.scene_id, requested_mechanic:config.kind, reason:'No registered plugin supports this mechanic.'});
      continue;
    }
    // The constructor performs the mechanic-specific config validation before binding.
    new Activity(config);
    bindings.push({task_id:task.task_id, scene_id:scene.scene_id, plugin_id:definition.pluginId, plugin_version:definition.version, mechanic:config.kind, config, config_sha256:await contentHash(config)});
  }
  return Object.freeze({schema_version:'gameplay-plan-0.1.0', status:buildRequests.length?'blocked':'ready', runtime_package_hash:await contentHash(pkg), bindings:Object.freeze(bindings), build_requests:Object.freeze(buildRequests)});
}

function ensure(condition, message) { if (!condition) throw new TypeError(message); }
