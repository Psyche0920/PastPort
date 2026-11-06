import test from 'node:test';
import assert from 'node:assert/strict';
import {messages,translate,setLanguage,getLanguage} from '../frontend/organizer/i18n.mjs';

test('manual locale selection is explicit and rejects unsupported values',()=>{
  setLanguage('en'); assert.equal(getLanguage(),'en');
  assert.throws(()=>setLanguage('de'),RangeError);
  setLanguage('zh'); assert.equal(translate('制作游戏'),'制作游戏');
});
test('dynamic status values and local paths retain their original identity',()=>{
  assert.equal(translate('本次新增模型调用：3','en'),'New model calls in this run:3');
  assert.equal(translate('/Users/test/project/game-3d','en'),'/Users/test/project/game-3d');
  assert.equal(translate('未知诊断内容','en'),'未知诊断内容');
});
test('embedded review translates exact interface labels without rewriting source prose',()=>{
  assert.equal(translate('在3D中查看','en',true),'View in 3D');
  const source='原始文献中的故事与任务描述';
  assert.equal(translate(source,'en',true),source);
});
test('catalog covers static shell and critical human consent actions',()=>{
  for(const key of ['管理员登录','制作游戏','资料与审核','制作进度与交付','我已核对，沿用旧故事','保存介绍（同步全景与3D）']) {
    assert.ok(messages[key]); assert.notEqual(translate(key,'en'),key);
    assert.equal(translate(key,'zh'),key);
  }
});

test('delivery sections and actions translate without changing package names',()=>{
  assert.equal(translate('wcheung · 当前第 2 版','en'),'wcheung · current version 2');
  assert.equal(translate('第 2 版（当前）','en'),'Version 2 (current)');
  assert.equal(translate('发布版本','en'),'Publication version');
  assert.equal(translate('解除发布','en'),'Unpublish');
  assert.equal(translate('已解除发布；列表刷新暂不可用，请稍后刷新。','en'),
    'Unpublished. The list could not refresh; try refreshing later.');
});
