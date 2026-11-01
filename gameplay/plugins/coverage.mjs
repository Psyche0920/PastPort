import {gameplayCatalog} from './gameplay-catalog.mjs';

/** Bounded constructive preflight, using the same placements the Activity validates. */
export function solveCoverage(config){
  const capability=gameplayCatalog.profiles.find(item=>item.kind==='tiling');
  if(!capability||config.width!==capability.board_width||config.height!==capability.board_height||!Array.isArray(config.pieces)||config.pieces.length<capability.minimum_pieces||config.pieces.length>capability.maximum_pieces||config.pieces.some(piece=>!Array.isArray(piece)||piece.length!==2||piece.some(value=>!Number.isSafeInteger(value)||value<1||value>capability.maximum_piece_dimension))||config.pieces.reduce((sum,[w,h])=>sum+w*h,0)!==config.width*config.height)throw new TypeError('Coverage problem is outside the registered capability');
  const all=(1n<<BigInt(config.width*config.height))-1n;
  const memo=new Set();let nodes=0;
  function search(mask,remaining){
    if(++nodes>capability.solver_node_limit)throw new RangeError('Coverage solver budget exhausted');
    if(!remaining.length)return mask===all?[]:null;
    const key=mask+':'+remaining.map(id=>config.pieces[id].join('x')).sort().join(',');
    if(memo.has(key))return null;memo.add(key);
    let cell=0;while(mask&(1n<<BigInt(cell)))cell++;
    const x=cell%config.width,y=Math.floor(cell/config.width),shapes=new Set();
    for(const id of remaining){
      const [w,h]=config.pieces[id],shape=[w,h].join('x');if(shapes.has(shape))continue;shapes.add(shape);
      for(const rotated of config.rotation_allowed===false||w===h?[false]:[false,true]){
        const [width,height]=rotated?[h,w]:[w,h];if(x+width>config.width||y+height>config.height)continue;
        let bits=0n;for(let dy=0;dy<height;dy++)for(let dx=0;dx<width;dx++)bits|=1n<<BigInt((y+dy)*config.width+x+dx);
        if(mask&bits)continue;
        const tail=search(mask|bits,remaining.filter(other=>other!==id));
        if(tail!==null)return [{id,x,y,rotated},...tail];
      }
    }
    return null;
  }
  const solution=search(0n,config.pieces.map((_,id)=>id));
  if(solution===null)throw new TypeError('Coverage problem has no solution');
  return solution;
}
