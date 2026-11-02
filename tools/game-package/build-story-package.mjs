import {readFile,writeFile,mkdir,readdir,lstat,realpath,copyFile,mkdtemp,rename,rm,access} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {StoryPackageCompiler,museumSnapshotHash} from './story-package.mjs';
import {openingLines} from '../../frontend/game/dialogue.mjs';
import {generatedStoryInput} from './generated-story.mjs';
import {preparedStoryInput} from '../../gameplay/prepared-game.mjs';
import {GameAssetPublisher} from './runtime-assets.mjs';

const sourceRoot=path.dirname(fileURLToPath(import.meta.url));
const json=value=>JSON.stringify(value,null,2)+'\n';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
async function pluginHash(){const digest=createHash('sha256');for(const name of ['plugins.mjs','coverage.mjs','gameplay-catalog.mjs']){digest.update(name+'\0');digest.update(await readFile(path.resolve(sourceRoot,'../../gameplay/plugins',name)));digest.update('\0');}return digest.digest('hex');}
const requireValue=(value,message)=>{if(!value)throw new Error(message);};

async function readJson(filename) {
  const info=await lstat(filename);
  requireValue(info.isFile()&&!info.isSymbolicLink()&&info.size<=8*1024*1024,'Input must be a regular JSON file smaller than 8 MiB');
  return JSON.parse(await readFile(filename,'utf8'));
}

async function childFile(base,relative) {
  requireValue(typeof relative==='string'&&!path.isAbsolute(relative)&&!relative.split(/[\\/]/).includes('..'),'Asset path must stay inside its source directory');
  const parent=await realpath(base),filename=await realpath(path.resolve(parent,relative));
  requireValue(filename.startsWith(parent+path.sep),'Asset path escapes its source directory');
  requireValue((await lstat(filename)).isFile(),'Asset must be a regular file');
  return filename;
}

async function copyTree(source,destination) {
  requireValue((await lstat(source)).isDirectory(),'Dependency directory is missing');
  await mkdir(destination,{recursive:true});
  for(const item of await readdir(source,{withFileTypes:true})) {
    const from=path.join(source,item.name),to=path.join(destination,item.name);
    requireValue(!item.isSymbolicLink(),'Symlink dependencies are not supported in a standalone game');
    if(item.isDirectory())await copyTree(from,to);
    else {requireValue(item.isFile(),'Only regular dependency files can be packaged');await copyFile(from,to);}
  }
}

async function loadMuseum(directory) {
  const runtime=await readJson(path.join(directory,'data/runtime.json'));
  const presentation=await readJson(path.join(directory,'data/presentation.json'));
  return {...presentation,runtimeCapabilities:runtime.runtime_compatibility};
}

/** Migrate an existing accepted local story into the explicit bridge input once. */
async function exportExisting(directory,output) {
  const museum=await loadMuseum(directory);
  const runtime=await readJson(path.join(directory,'data/runtime.json'));
  const input={schema_version:'story-3d-input-0.1.0',story:{kind:'runtime-package',payload:runtime},
    museum:{tour_id:museum.tourId,snapshot_sha256:await museumSnapshotHash(museum)},
    tasks:museum.chapters.map(chapter=>{
      const scene=runtime.game.scenes.find(scene=>scene.scene_id===chapter.id);
      requireValue(scene?.tasks.length===1,'Existing story needs one task per scene');
      const task=scene.tasks[0],media=runtime.media_manifest.find(item=>item.asset_id===task.asset_id);
      const source=museum.objects.find(item=>item.media_path===media?.relative_path&&item.media_sha256===media.sha256);
      requireValue(source,'Existing task asset is not a museum object');
      return {task_id:task.task_id,scene_id:scene.scene_id,chapter:chapter.chapter,objects:chapter.objects,required_sources:chapter.requiredSources,target_number:museum.stageTargets[chapter.id],asset_object_number:source.number,plugin:chapter.plugin,automatic_decision:Boolean(chapter.automaticDecision)};
    }),
    presentation:{title:{zh:'一捆柴',en:'One Bundle of Firewood'},intro:museum.intro,openingLines:museum.openingLines??openingLines,guideLines:museum.guideLines??[],castFrames:museum.castFrames,castRows:museum.castRows,sourceTitle:{zh:'II. Murat Külliyesi',en:'II. Murat Külliyesi'}}};
  await new StoryPackageCompiler().compile(input,museum);
  await writeFile(output,json(input),{flag:'wx'});
  console.log(JSON.stringify({status:'exported',task_count:input.tasks.length,output}));
}

async function fileManifest(directory,prefix='') {
  const files=[];
  for(const item of await readdir(path.join(directory,prefix),{withFileTypes:true})) {
    const relative=path.posix.join(prefix,item.name);
    if(item.isDirectory())files.push(...await fileManifest(directory,relative));
    else {const bytes=await readFile(path.join(directory,relative));files.push({path:relative,sha256:hash(bytes),size_bytes:bytes.length});}
  }
  return files.sort((left,right)=>left.path.localeCompare(right.path));
}

async function build(inputFile,museumDirectory,output,preparationFile=null,environmentFile=null) {
  try {await access(output);throw new Error('Output exists; choose a new directory to preserve existing games');}
  catch(error) {if(error.code!=='ENOENT')throw error;}
  const generation=await readJson(inputFile);
  const preparation=preparationFile?await readJson(preparationFile):null;
  const museum=await loadMuseum(museumDirectory);
  const input=environmentFile?await preparedStoryInput(generation,preparation,await readJson(environmentFile),museum,await pluginHash(),hash(await readFile(environmentFile))):preparation?await generatedStoryInput(generation,preparation):generation;
  const narrativeSchema=await readJson(path.resolve(sourceRoot,'../../schemas/draft-result.schema.json'));
  const compiled=await new StoryPackageCompiler().compile(input,museum,{narrativeSchema});
  const worlds=await readJson(path.join(museumDirectory,'data/scene3d-input.json'));
  requireValue(Array.isArray(worlds.worlds)&&[1,2].includes(worlds.worlds.length),'Current 3D adapter requires one or two prepared worlds');
  await mkdir(path.dirname(output),{recursive:true});
  const staging=await mkdtemp(path.join(path.dirname(output),'.story-3d-build-'));
  try {
    await new GameAssetPublisher().publish(staging);
    await copyTree(path.join(museumDirectory,'assets'),path.join(staging,'assets'));
    for(const object of museum.objects) {
      const source=await childFile(museumDirectory,object.media_path),bytes=await readFile(source);
      requireValue(hash(bytes)===object.media_sha256,`Museum object ${object.number} media hash changed`);
      const destination=path.join(staging,object.media_path);
      await mkdir(path.dirname(destination),{recursive:true});await copyFile(source,destination);
    }
    for(const asset of compiled.runtime.media_manifest) {
      const object=museum.objects.find(object=>object.media_sha256===asset.sha256);
      requireValue(object,'Assembled runtime references media absent from this museum');
      requireValue(!path.isAbsolute(asset.relative_path)&&!asset.relative_path.split(/[\\/]/).includes('..'),'Assembled media path escapes the bundle');
      const destination=path.join(staging,asset.relative_path);
      await mkdir(path.dirname(destination),{recursive:true});await copyFile(await childFile(museumDirectory,object.media_path),destination);
    }
    for(const [index,world] of worlds.worlds.entries()) {
      const from=path.resolve(museumDirectory,world.root),relative=`worlds/${index+1}`;
      await copyTree(path.join(from,'scene3d'),path.join(staging,relative,'scene3d'));
      world.root=relative;
    }
    await mkdir(path.join(staging,'data'));
    for(const [filename,value] of Object.entries({'runtime.json':compiled.runtime,'reference.json':compiled.reference,'presentation.json':compiled.presentation,'gameplay-plan.json':compiled.gameplayPlan,'story-input.json':input,'story-build-report.json':compiled.report,'scene3d-input.json':worlds}))await writeFile(path.join(staging,'data',filename),json(value));
    if(preparation){await writeFile(path.join(staging,'data/generation-result.json'),json(generation));await writeFile(path.join(staging,'data/preparation-result.json'),json(preparation));}
    await writeFile(path.join(staging,'OPEN.txt'),'Run: node serve3d.mjs\nThen open http://127.0.0.1:18824/?scene=3d\nOptional: PASTPORT_PORT=18826 node serve3d.mjs\nAll scene resources are local. Model generation is not required to play.\n');
    const files=await fileManifest(staging);
    await writeFile(path.join(staging,'manifest.json'),json({format:'pastport-story-3d-bundle',version:1,runtime_sha256:compiled.reference.sha256,input_sha256:compiled.report.input_sha256,museum_snapshot_sha256:input.museum.snapshot_sha256,entry:'/?scene=3d',local_only:true,human_acceptance:'not_performed',files}));
    await rename(staging,output);
    console.log(JSON.stringify({status:'built',output,...compiled.report,file_count:files.length}));
  } catch(error) {await rm(staging,{recursive:true,force:true});throw error;}
}

const [command,...arguments_]=process.argv.slice(2),options=new Map();
for(let index=0;index<arguments_.length;index+=2){requireValue(arguments_[index].startsWith('--')&&arguments_[index+1],'Expected --option value');options.set(arguments_[index],path.resolve(arguments_[index+1]));}
requireValue(['export-existing','build','from-generated','from-gameplay'].includes(command)&&options.has('--museum')&&options.has('--output'),'Use export-existing, build, or from-generated with --museum DIRECTORY --output NEW_PATH');
if(command==='export-existing')await exportExisting(options.get('--museum'),options.get('--output'));
else {requireValue(options.has('--input'),'Missing --input');if(['from-generated','from-gameplay'].includes(command))requireValue(options.has('--preparation'),'Missing independent gameplay/presentation preparation output');if(command==='from-gameplay')requireValue(options.has('--environment'),'Missing pinned environment');await build(options.get('--input'),options.get('--museum'),options.get('--output'),['from-generated','from-gameplay'].includes(command)?options.get('--preparation'):null,command==='from-gameplay'?options.get('--environment'):null);}
