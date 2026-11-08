import {randomUUID} from 'node:crypto';
/** Account/site/release scoped snapshots; the game engine still validates gameplay. */
export class SaveConflict extends Error {}
export class InvalidSave extends Error {}
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const maxBytes = 512 * 1024;
/** Structural checks per runtime; each game's own engine still validates and replays on restore. */
const formats = {
  'gamesession-v2': snapshot => object(snapshot) && snapshot.version === 2 && typeof snapshot.identity === 'string' &&
    /^[a-f0-9]{64}$/.test(snapshot.identity) && Number.isSafeInteger(snapshot.sequence) &&
    snapshot.sequence >= 0 && snapshot.sequence < 1000000 && object(snapshot.engine) &&
    object(snapshot.local) && Array.isArray(snapshot.notebook) && object(snapshot.positions),
  // Legacy UI Trial: world/chapter identity plus the replayable action log and positions.
  'authored-adventure-v1': snapshot => object(snapshot) &&
    ['string','number'].includes(typeof snapshot.version) && ['string','number'].includes(typeof snapshot.chapter_version) &&
    typeof snapshot.chapter_id === 'string' && snapshot.chapter_id.length <= 200 && typeof snapshot.started === 'boolean' &&
    Array.isArray(snapshot.events) && snapshot.events.length <= 1500 &&
    snapshot.events.every(event => object(event) && typeof event.kind === 'string' && event.kind.length <= 40 &&
      Array.isArray(event.args) && event.args.length <= 2 && event.args.every(arg => typeof arg === 'string' && arg.length <= 200)) &&
    (snapshot.positions === undefined || object(snapshot.positions)),
};
export const saveFormats = Object.freeze(Object.keys(formats));
export class PlayerSaveRepository {
  constructor(database) {
    this.database = database;
    database.exec(`CREATE TABLE IF NOT EXISTS game_save (
      player TEXT NOT NULL REFERENCES player(id), site TEXT NOT NULL, version TEXT NOT NULL,
      payload TEXT NOT NULL, revision INTEGER NOT NULL, updated TEXT NOT NULL,
      operation TEXT NOT NULL, PRIMARY KEY(player,site,version));
    CREATE TABLE IF NOT EXISTS game_save_archive (
      player TEXT NOT NULL REFERENCES player(id), site TEXT NOT NULL, version TEXT NOT NULL,
      payload TEXT NOT NULL, revision INTEGER NOT NULL, updated TEXT NOT NULL,
      operation TEXT NOT NULL, archived TEXT NOT NULL, PRIMARY KEY(player,site,version,revision));`);
  }
  read(player, site, version) {
    const row = this.database.prepare('SELECT payload,revision,updated FROM game_save WHERE player=? AND site=? AND version=?').get(player,site,version);
    return row ? {entries:JSON.parse(row.payload),revision:row.revision,updated:row.updated} : {entries:{},revision:0,updated:null};
  }
  list(player, site) {
    return this.database.prepare('SELECT version,revision,updated FROM game_save WHERE player=? AND site=? AND revision>0 ORDER BY updated DESC, version').all(player,site);
  }
  /** Preserve the prior attempt and advance CAS so old tabs cannot overwrite the fresh game. */
  archiveAndReset(player, site, version, expectedRevision) {
    this.database.exec('BEGIN IMMEDIATE');
    try {
      const previous=this.database.prepare('SELECT payload,revision,updated,operation FROM game_save WHERE player=? AND site=? AND version=?').get(player,site,version);
      if(!previous || previous.revision!==expectedRevision)throw new SaveConflict('A newer save exists');
      const updated=new Date().toISOString();
      this.database.prepare('INSERT INTO game_save_archive VALUES (?,?,?,?,?,?,?,?)')
        .run(player,site,version,previous.payload,previous.revision,previous.updated,previous.operation,updated);
      this.database.prepare('UPDATE game_save SET payload=?,revision=?,updated=?,operation=? WHERE player=? AND site=? AND version=?')
        .run('{}',previous.revision+1,updated,randomUUID(),player,site,version);
      this.database.exec('COMMIT');
      return {entries:{},revision:previous.revision+1,updated};
    } catch(error) {
      this.database.exec('ROLLBACK');
      throw error;
    }
  }
  write(player, site, version, input, allowedKeys, format = 'gamesession-v2') {
    const valid = formats[format];
    if (!valid) throw new InvalidSave('Unsupported save format');
    if (!Number.isSafeInteger(input.revision) || input.revision < 0 ||
        typeof input.operation !== 'string' || !/^[a-f0-9-]{32,64}$/.test(input.operation) ||
        !object(input.changes) || !Object.keys(input.changes).length || Object.keys(input.changes).length > 8) throw new InvalidSave('Invalid save envelope');
    for (const [key,raw] of Object.entries(input.changes)) {
      if (!allowedKeys.includes(key)) throw new InvalidSave('Unknown game save key');
      if (raw === null) continue;
      if (typeof raw !== 'string' || Buffer.byteLength(raw) > 300000) throw new InvalidSave('Invalid snapshot size');
      let snapshot;
      try { snapshot=JSON.parse(raw); } catch { throw new InvalidSave('Snapshot is not JSON'); }
      if (!valid(snapshot)) throw new InvalidSave('Invalid game snapshot');
    }
    // Synchronous short transaction: no model/network work while holding the write lock.
    this.database.exec('BEGIN IMMEDIATE');
    try {
      const previous = this.database.prepare('SELECT operation FROM game_save WHERE player=? AND site=? AND version=?').get(player,site,version);
      const saved = this.read(player,site,version);
      if (previous?.operation === input.operation) {
        this.database.exec('COMMIT');
        return saved;
      }
      if (saved.revision !== input.revision) throw new SaveConflict('A newer save exists');
      const entries = {...saved.entries};
      for (const [key,value] of Object.entries(input.changes)) {
        if (value === null) delete entries[key]; else entries[key] = value;
      }
      const payload = JSON.stringify(entries);
      if (Buffer.byteLength(payload) > maxBytes) throw new InvalidSave('Save exceeds storage limit');
      const next = {entries,revision:saved.revision+1,updated:new Date().toISOString()};
      this.database.prepare(`INSERT INTO game_save VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(player,site,version) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated=excluded.updated,operation=excluded.operation`)
        .run(player,site,version,payload,next.revision,next.updated,input.operation);
      this.database.exec('COMMIT');
      return next;
    } catch (error) {
      this.database.exec('ROLLBACK');
      throw error;
    }
  }
}
