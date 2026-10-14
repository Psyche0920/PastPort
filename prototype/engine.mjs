/** Deterministic chapter state; narrative content never mutates evidence truth. */
export class StoryEngine {
  constructor(chapter, saved = null) {
    this.chapter = chapter;
    this.state = saved || {version: chapter.version, scene: 0, elapsed: 0, observed: {}, completed: [], decisions: {}, inventory: [], assignments: {}, caseboard: [], ending: null};
    if (this.state.version !== chapter.version) throw new Error('Save version does not match this chapter');
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
    if (choice === 'erase') return {id:'clean-page', title:'A Clean Page, a Closed Hand', career:'The steward accepts the new ledger. Your job is safe for now.', friend:this.friend === 'with_you' ? 'You vouched for Cem, then removed the original record that could explain the error. Now the person who guaranteed him must answer questions too.' : 'Cem remains detained. Without the original ledger, no one can trace how suspicion fell on him.', service:'Supplies go out again, but the apprentice will still be questioned.', growth:'You learned the truth, then removed the page that could have helped you grow.', late};
    if (choice === 'accuse') return {id:'other-signature', title:'You Kept Your Place. The Meal Stopped.', career:'You blamed the kitchen. The steward freezes the supplies and investigates its staff.', friend:this.hasWitness ? 'Halime will not sign your report. Her statement proves the flour arrived, not that the kitchen was at fault.' : 'Cem has not been cleared. Now more people are under suspicion.', service:'This fictional meal service is paused. The grain is there, but no meal reaches the table.', growth:'You turned a number in your ledger into someone else’s fault.', late};
    return {id: this.hasWitness ? 'signed-truth' : 'unfinished-truth', title: this.hasWitness ? 'Your Name Stays. The Blame Is Lifted.' : 'You Own the Error, but One Statement Is Missing.', career:'You keep the original ledger, sign a correction, and lose independent signing privileges while the steward reviews your work.', friend:this.hasWitness ? (this.friend === 'with_you' ? 'Cem stays by your side. Halime’s statement and the kitchen receipt clear him.' : 'The goods and delivery are confirmed. Cem is released, but he will remember that you let the guard take him.' ) : 'The stock is accounted for, but the receipt does not name the carrier. You promise to get Cem’s statement checked before blaming anyone.', service:late ? 'The accounts are late. This meal is delayed, and you explain the delay to the people waiting.' : 'The accounts close on time, and the meal goes out as planned.', growth:'From now on, your name stands for both a delivery and the courage to correct the record.', late};
  }
  snapshot() { return JSON.parse(JSON.stringify(this.state)); }
}
