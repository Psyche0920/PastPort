import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {preparedStoryInput} from '../gameplay/prepared-game.mjs';
const [draftFile,planFile,environmentFile,museumDirectory,outputFile]=process.argv.slice(2);
if(!outputFile)throw new Error('Expected draft, plan, canonical environment, museum and output');
const read=async file=>JSON.parse(await readFile(file,'utf8'));
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../gameplay/plugins');
const digest=createHash('sha256');
for(const name of ['plugins.mjs','investigation.mjs','coverage.mjs','gameplay-catalog.mjs']){digest.update(name+'\0');digest.update(await readFile(path.join(root,name)));digest.update('\0');}
const museum={...await read(path.join(museumDirectory,'data/presentation.json')),runtimeCapabilities:(await read(path.join(museumDirectory,'data/runtime.json'))).runtime_compatibility};
const raw=await readFile(environmentFile);
const result=await preparedStoryInput(await read(draftFile),await read(planFile),JSON.parse(raw),museum,digest.digest('hex'),createHash('sha256').update(raw).digest('hex'));
await writeFile(outputFile,JSON.stringify(result,null,2)+'\n',{flag:'wx'});
