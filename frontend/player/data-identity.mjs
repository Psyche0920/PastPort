/** A known deployment records its player-store identity beside Organizer data; a missing store fails. */
import {randomBytes} from 'node:crypto';
import {access,mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const exists=path=>access(path).then(()=>true,()=>false);
export const MARKER='.pastport-data-id';
export async function verifyDataIdentity(data,organizerData) {
  const marker=join(data,MARKER);
  const record=join(organizerData,'player-data-identity.json');
  if (await exists(record)) {
    const expected=JSON.parse(await readFile(record,'utf8')).player;
    const actual=(await exists(marker)) ? (await readFile(marker,'utf8')).trim() : null;
    if (actual!==expected || !(await exists(join(data,'players.sqlite')))) {
      throw new Error(`Player data at ${data} is missing or is not this deployment's database (expected ${expected}). `+
        `No empty database was created. Restore the backup or set PLAYER_DATA to the original directory; `+
        `delete ${record} only if you intend to start over.`);
    }
    return expected;
  }
  let identity;
  if (await exists(marker)) identity=(await readFile(marker,'utf8')).trim();
  else {
    identity=randomBytes(16).toString('hex');
    await mkdir(data,{recursive:true,mode:0o700});
    await writeFile(marker,identity+'\n',{mode:0o600});
  }
  // Without an Organizer directory there is nothing to bind yet (player-only development).
  if (await exists(organizerData)) await writeFile(record,JSON.stringify({player:identity})+'\n',{mode:0o600});
  return identity;
}
