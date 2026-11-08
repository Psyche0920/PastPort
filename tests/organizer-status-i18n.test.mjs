import test from 'node:test';
import assert from 'node:assert/strict';
import {translate} from '../frontend/organizer/i18n.mjs';

const statuses = [
  '任务条件已变化，请先处理：此资料来源尚无已校验的旧故事。',
  '环境资料已交接：9个候选，9个已定位；全部候选已有定位。历史关联与空间位置仍待审核。 尚未调用Story或组包。',
  '环境资料已交接：12个候选，11个已定位；未定位编号：24。历史关联与空间位置仍待审核。 尚未调用Story或组包。',
  '环境资料已交接：15个候选，6个已定位；未定位编号：3、4、7、8、9、10、13、14、15。历史关联与空间位置仍待审核。 尚未调用Story或组包。',
  '无法读取PDF资料：展签 PP-001 的描述无法定位到原文。',
  '已保存的 3D 审核版，30 个候选落点。可打开预览或继续准备故事。',
  '照片识别第 1 批覆盖不足，此前已处理 0 批。已保留模型回执。',
  '原生SDK步骤未完成，原始结果和用量记录已保留。',
  '3D挂载未完成，原始结果和用量记录已保留。',
  '上传材料已准备为环境；请选择故事，尚未调用Story或组包。',
  '身份复核版：20 项识别记录，7 号和 12 号待复核，3 项史料候选，8 号已定位。',
  '导入记录（版本管理启用前）',
];
for (const locale of ['en','tr']) {
  test(`${locale}: actual backend notifications contain no untranslated Chinese`,()=>{
    for (const message of statuses) {
      const translated=translate(message,locale);
      assert.doesNotMatch(translated,/\p{Script=Han}/u,message);
      assert.doesNotMatch(translated,/None法|Yok法|尚None|尚Yok/u);
    }
    assert.match(translate(statuses[3],locale),/3, 4, 7, 8, 9, 10, 13, 14, 15/);
  });
  test(`${locale}: review labels translate without changing source names or task IDs`,()=>{
    for (const label of ['位置 0–67：IDML原文单元的 Unicode 字符偏移，非排版页码或屏幕坐标。','待确认候选（3 项）','全部识别物件（30 项）',' · 待复核','IDML 来源对象 · historical:abc123','IDML原文单元（不是PDF页码）。','IDML包中的来源图片；语义关联待审核。','暂无对应历史对象 · 无已确认实物照','选区：null。同页照片与段落不自动视为对应。','类别：现代替代物；父对象：无；出现 2 次。坐标为左上原点的归一化选区。','IDML原文单元（不是PDF页码）。下方展开文字页上下文，图片页可能不同。','编辑判断：候选·待独立验收。这是中文改述，原文保留在下方；不是用户批准。']) {
      assert.doesNotMatch(translate(label,locale,true),/\p{Script=Han}/u,label);
    }
    const name='原始中文物件名称_无';
    assert.ok(translate(name+' · 实物配图候选',locale,true).startsWith(name+' · '));
    const task='task_原文_无';
    assert.ok(translate('任务 '+task+'：所用物件 12 已缺失。',locale,true).includes(task));
    assert.ok(translate('IDML 来源对象 · historical:abc123',locale,true).endsWith('historical:abc123'));
  });
  test(`${locale}: unknown source prose is preserved rather than replacing individual characters`,()=>{
    const prose='无名物件的原始介绍，无法据此确认用途。';
    assert.equal(translate(prose,locale,true),prose);
    assert.equal(translate('无法从未登记的原文推断身份。',locale),'无法从未登记的原文推断身份。');
    assert.equal(translate('无',locale),locale==='en'?'None':'Yok');
  });
}

for(const locale of ['en','tr'])test(`${locale}: persisted candidate status and review preview link are localized`,()=>{
  for(const text of ['candidate_unreviewed','打开 3D 审核预览 ↗']){
    assert.notEqual(translate(text,locale,true),text);
    assert.doesNotMatch(translate(text,locale,true),/\p{Script=Han}/u);
  }
});
