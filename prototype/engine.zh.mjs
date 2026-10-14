/** Deterministic chapter state; narrative content never mutates evidence truth. */
export class StoryEngine {
  constructor(chapter, saved = null) {
    this.chapter = chapter;
    this.state = saved || {version: chapter.version, scene: 0, elapsed: 0, observed: {}, completed: [], decisions: {}, inventory: [], assignments: {}, caseboard: [], ending: null};
    if (this.state.version !== chapter.version) throw new Error('存档版本与章节不一致');
  }
  get scene() { return this.chapter.scenes[this.state.scene]; }
  get remaining() { return this.chapter.initial_minutes - this.state.elapsed; }
  get friend() { return !this.state.decisions.friend ? 'pending' : this.state.decisions.friend === 'vouch' ? 'with_you' : 'detained'; }
  get hasWitness() { return this.state.decisions.witness === 'help'; }
  addEvidence(id) {
    if (!this.chapter.evidence.some(item => item.id === id)) throw new Error('Unknown evidence');
    if (!this.state.inventory.includes(id)) this.state.inventory.push(id);
  }
  inspect(id) {
    if (!this.scene.task.hotspots?.some(spot => spot.id === id)) throw new Error('Unknown observation');
    const seen = this.state.observed[this.scene.id] ||= [];
    if (!seen.includes(id)) seen.push(id);
    if (this.scene.task.required.every(item => seen.includes(item))) {
      if (this.scene.id === 'courtyard') this.addEvidence('loading-slip');
      if (this.scene.id === 'imaret') this.addEvidence('kitchen-slip');
      if (this.scene.task.kind === 'inspect') this.complete();
    }
  }
  openTally() {
    if (this.scene.task.kind !== 'document') throw new Error('Not a document scene');
    this.addEvidence('tally'); this.complete();
  }
  assign(cardId, destination) {
    if (!this.canSort()) throw new Error('Inspect the delivery landmark first');
    if (!this.scene.sorting.cards.some(card => card.id === cardId) || !this.scene.sorting.destinations.some(item => item.id === destination)) throw new Error('Unknown sorting item');
    this.state.assignments[cardId] = destination;
  }
  canSort() { return this.scene.task.kind === 'inspect-sort' && this.scene.task.required.every(id => (this.state.observed[this.scene.id] || []).includes(id)); }
  checkSorting() {
    if (!this.canSort()) throw new Error('Sorting is locked');
    const valid = this.scene.sorting.cards.every(card => this.state.assignments[card.id] === card.destination);
    if (valid) { this.addEvidence('reconciliation'); this.complete(); }
    return valid;
  }
  toggleBoard(id) {
    if (this.scene.task.kind !== 'caseboard' || !this.state.inventory.includes(id)) throw new Error('Evidence not available');
    if (this.state.completed.includes(this.scene.id)) return;
    const selected = this.state.caseboard;
    this.state.caseboard = selected.includes(id) ? selected.filter(item => item !== id) : [...selected, id];
  }
  checkBoard() {
    if (this.scene.task.kind !== 'caseboard') throw new Error('Not a case board');
    const valid = this.state.caseboard.length === this.scene.task.required.length && this.scene.task.required.every(id => this.state.caseboard.includes(id));
    if (valid) this.complete();
    return valid;
  }
  complete() {
    if (!this.state.completed.includes(this.scene.id)) {
      this.state.completed.push(this.scene.id);
      this.state.elapsed += this.scene.cost || 0;
    }
  }
  choose(optionId) {
    if (!this.state.completed.includes(this.scene.id)) throw new Error('Finish the scene task first');
    const decision = this.scene.decision;
    if (!decision) throw new Error('No decision in this scene');
    if (this.state.decisions[decision.id]) throw new Error('Decision already committed');
    const option = decision.options.find(item => item.id === optionId);
    if (!option) throw new Error('Unknown decision');
    this.state.decisions[decision.id] = option.id;
    this.state.elapsed += option.cost;
    if (decision.id === 'witness' && option.id === 'help') this.addEvidence('witness');
    if (decision.id === 'final') this.state.ending = this.resolveEnding(optionId);
  }
  canAdvance() { return this.state.completed.includes(this.scene.id) && (!this.scene.decision || Boolean(this.state.decisions[this.scene.decision.id])); }
  advance() {
    if (!this.canAdvance() || !this.scene.next) throw new Error('Next scene is locked');
    const nextIndex = this.chapter.scenes.findIndex(item => item.id === this.scene.next);
    if (nextIndex <= this.state.scene) throw new Error('Invalid scene transition');
    this.state.scene = nextIndex;
  }
  resolveEnding(choice) {
    const late = this.state.elapsed > this.chapter.initial_minutes;
    if (choice === 'erase') return {id:'clean-page', title:'一页干净的账，一双没松开的手', career:'管事接受新账，你的职位暂时保住。', friend:this.friend === 'with_you' ? '你亲手替杰姆担保，却抽走了能解释错误的原账。他的保证人如今成了另一个需要被追问的人。' : '杰姆仍被扣留。没有原账，没人知道嫌疑是怎样落在他身上的。', service:'物资恢复发放；对学徒的追问还会继续。', growth:'你知道真相，却把成长的机会留在了被抽走的那一页。', late};
    if (choice === 'accuse') return {id:'other-signature', title:'你留下了位置，饭却停了', career:'你把责任推给厨房。管事决定冻结相关发放，核查工作人员。', friend:this.hasWitness ? '哈丽梅拒绝在你的报告上签名：她的证词说的是货物到达，不是厨房有错。' : '杰姆没有被证明无辜，只是多了一群被怀疑的人。', service:'这一次虚构的供餐暂停。账里有粮，桌上却没有饭。', growth:'你又把一个总数写成了另一个人的过错。', late};
    return {id: this.hasWitness ? 'signed-truth' : 'unfinished-truth', title: this.hasWitness ? '名字留下，嫌疑撤回' : '你承认了错误，仍欠一份证词', career:'你保留原账，补记货物分类并具名。管事暂停你的独立签账资格，安排重新核验。', friend:this.hasWitness ? (this.friend === 'with_you' ? '杰姆始终站在你身边。厨房收料单与哈丽梅的证词相互核对，他的嫌疑被撤回。' : '物资与搬运者都已核对。杰姆获释，但你让看守带走他的那一刻，不会从他的记忆里消失。') : '物资差异已经解释，但收料单没有搬运者姓名。杰姆的正式核验留到下一轮；你承诺补齐证词，不再用猜测定责。', service:late ? '你交账时已超过约定时限。这一餐延后发放；你亲自去向等待的人解释。' : '核账在时限内完成，这一餐按时发放。', growth:'从今天起，你的名字既代表签收，也代表愿意承担更正。', late};
  }
  snapshot() { return JSON.parse(JSON.stringify(this.state)); }
}
