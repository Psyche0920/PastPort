/** Account/site/release scoped snapshots; the game engine still validates gameplay. */
export class SaveConflict extends Error {}
export class InvalidSave extends Error {}
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const maxBytes = 512 * 1024;
export class PlayerSaveRepository {
  constructor(database) {
    this.database = database;
    database.exec(`CREATE TABLE IF NOT EXISTS game_save (
      player TEXT NOT NULL REFERENCES player(id), site TEXT NOT NULL, version TEXT NOT NULL,
      payload TEXT NOT NULL, revision INTEGER NOT NULL, updated TEXT NOT NULL,
      operation TEXT NOT NULL, PRIMARY KEY(player,site,version));`);
  }
  read(player, site, version) {
    const row = this.database.prepare('SELECT payload,revision,updated FROM game_save WHERE player=? AND site=? AND version=?').get(player,site,version);
    return row ? {entries:JSON.parse(row.payload),revision:row.revision,updated:row.updated} : {entries:{},revision:0,updated:null};
  }
  write(player, site, version, input, allowedKeys) {
    if (!Number.isSafeInteger(input.revision) || input.revision < 0 ||
        typeof input.operation !== 'string' || !/^[a-f0-9-]{32,64}$/.test(input.operation) ||
        !object(input.changes) || !Object.keys(input.changes).length || Object.keys(input.changes).length > 8) throw new InvalidSave('Invalid save envelope');
    for (const [key,raw] of Object.entries(input.changes)) {
      if (!allowedKeys.includes(key)) throw new InvalidSave('Unknown game save key');
      if (raw === null) continue;
      if (typeof raw !== 'string' || Buffer.byteLength(raw) > 300000) throw new InvalidSave('Invalid snapshot size');
      let snapshot;
      try { snapshot=JSON.parse(raw); } catch { throw new InvalidSave('Snapshot is not JSON'); }
      if (!object(snapshot) || snapshot.version !== 2 || typeof snapshot.identity !== 'string' ||
          !/^[a-f0-9]{64}$/.test(snapshot.identity) || !Number.isSafeInteger(snapshot.sequence) ||
          snapshot.sequence < 0 || snapshot.sequence >= 1000000 || !object(snapshot.engine) ||
          !object(snapshot.local) || !Array.isArray(snapshot.notebook) || !object(snapshot.positions)) throw new InvalidSave('Invalid game snapshot');
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
