import test from 'node:test';
import assert from 'node:assert/strict';
import {mountLocalization,setLanguage} from '../frontend/organizer/i18n.mjs';

test('review prose switches languages and preserves original identity without editing fields',()=>{
  const attrs=new Map();
  const node={textContent:'白色书柜',title:'',getAttribute:key=>attrs.get(key)??null,hasAttribute:key=>attrs.has(key),setAttribute:(key,value)=>attrs.set(key,value)};
  const editor={value:'原始审核记录'};
  const doc={documentElement:{},body:{},defaultView:{MutationObserver:class{observe(){} disconnect(){}}},
    querySelectorAll:selector=>selector==='[data-review-display]'?[node]:[],
    createTreeWalker:()=>({nextNode:()=>false}),getElementById:()=>null};
  setLanguage('en');
  const unmount=mountLocalization(doc,{contentTranslations:[{original:'白色书柜',en:'White bookcase',tr:'Beyaz kitaplık'}]});
  assert.equal(node.textContent,'White bookcase');assert.equal(node.title,'白色书柜');
  setLanguage('tr');assert.equal(node.textContent,'Beyaz kitaplık');
  setLanguage('zh');assert.equal(node.textContent,'白色书柜');
  assert.equal(editor.value,'原始审核记录');
  unmount();
});
