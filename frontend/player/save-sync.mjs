/** Coalesced, ordered writes with explicit retry and optimistic concurrency. */
export class SaveSynchronizer {
  constructor({revision, persist, status}) {
    this.revision=revision; this.persist=persist; this.status=status;
    this.pending=new Map(); this.batch=null; this.running=null; this.failure=null; this.timer=null;
  }
  queue(key,value) {
    this.pending.set(key,value);
    if (!this.failure) this.status('pending');
    clearTimeout(this.timer);
    if (!this.failure) this.timer=setTimeout(()=>{void this.flush().catch(()=>{});},250);
  }
  async flush() {
    clearTimeout(this.timer);
    if (this.running) {await this.running; return this.flush();}
    if (this.failure) throw this.failure;
    this.running=this.drain();
    try {await this.running;} finally {this.running=null;}
  }
  async drain() {
    while (this.batch || this.pending.size) {
      if (!this.batch) {
        this.batch={revision:this.revision,operation:crypto.randomUUID(),changes:Object.fromEntries(this.pending)};
        this.pending.clear();
      }
      this.status('saving');
      try {
        const saved=await this.persist(this.batch);
        this.revision=saved.revision;this.batch=null;
      } catch(error) {this.failure=error;this.status('failed',error);throw error;}
    }
    this.status('saved');
  }
  retry() {this.failure=null;return this.flush();}
  get dirty() {return !!(this.batch || this.pending.size || this.running);}
}
