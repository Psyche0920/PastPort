import { StoryEngine } from './engine.zh.mjs';
import { ObservationMatch } from './observation-match.mjs';

const SAVE_KEY = 'pastport:chapter-record-and-service:adventure:v1';

/** Replays approved engine actions so a save cannot grant unearned evidence. */
export class GameSession {
  constructor(chapter, worldVersion, storage) {
    this.storage = storage;
    this.chapter = chapter;
    this.worldVersion = worldVersion;
    this.engine = new StoryEngine(chapter);
    this.events = [];
    this.positions = {};
    this.started = false;
    this.storageWarning = false;
  }

  restore() {
    let raw;
    try { raw = this.storage.getItem(SAVE_KEY); }
    catch (error) { this.storageWarning = true; console.warn('Adventure storage read failed', error.name); return; }
    if (!raw) return;
    let saved;
    try { saved = JSON.parse(raw); }
    catch { throw new Error('存档无法读取。原存档已保留，可选择重新开始。'); }
    if (saved.version !== this.worldVersion || saved.chapter_version !== this.chapter.version ||
        saved.chapter_id !== this.chapter.chapter_id || !Array.isArray(saved.events) || saved.events.length > 1500 ||
        typeof saved.started !== 'boolean') throw new Error('存档与当前版本不兼容。原存档已保留。');
    const replay = new StoryEngine(this.chapter);
    try { for (const event of saved.events) this.apply(replay, event); }
    catch { throw new Error('存档中的调查步骤无法重放。原存档已保留。'); }
    this.engine = replay;
    this.events = saved.events;
    this.started = saved.started;
    if (saved.positions && typeof saved.positions === 'object' && !Array.isArray(saved.positions)) this.positions = saved.positions;
  }

  apply(engine, event) {
    if (!event || !Array.isArray(event.args) || event.args.length > 2 || event.args.some(value => typeof value !== 'string')) throw new Error('无效的调查动作');
    const counts = {inspect:1, openTally:0, assign:2, checkSorting:0, toggleBoard:1, checkBoard:0, choose:1, advance:0};
    if (!Object.hasOwn(counts, event.kind) || event.args.length !== counts[event.kind]) throw new Error('未知的调查动作');
    return engine[event.kind](...event.args);
  }

  dispatch(kind, ...args) {
    const event = {kind, args};
    const result = this.apply(this.engine, event);
    this.events.push(event);
    this.persist();
    return result;
  }

  submitObservationMatch(puzzle) {
    const spots = this.engine.scene.task.hotspots;
    if (!(puzzle instanceof ObservationMatch) || !spots || spots.length !== puzzle.options.length ||
        spots.some(spot => !puzzle.options.some(option => option.id === spot.id && option.x === spot.x && option.y === spot.y))) throw new Error('配对题与当前场景不一致');
    if (!puzzle.check().complete) return false;
    for (const spot of spots) this.dispatch('inspect',spot.id);
    return true;
  }

  persist() {
    try {
      this.storage.setItem(SAVE_KEY, JSON.stringify({version:this.worldVersion, chapter_version:this.chapter.version,
        chapter_id:this.chapter.chapter_id, started:this.started, events:this.events, positions:this.positions}));
    } catch (error) { this.storageWarning = true; console.warn('Adventure storage write failed', error.name); }
  }

  reset() { this.engine = new StoryEngine(this.chapter); this.events = []; this.positions = {}; this.started = false; this.persist(); }
}

