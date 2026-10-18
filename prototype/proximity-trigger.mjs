/** Entry-triggered interactions with hysteresis to prevent modal reopen loops. */
export class ProximityTriggers {
  constructor(radius = 78, releaseRadius = 130) {
    if (!(radius > 0) || !(releaseRadius > radius)) throw new Error('Invalid proximity radii');
    this.radius = radius;
    this.releaseRadius = releaseRadius;
    this.occupied = new Set();
  }

  distance(position, target) {
    return Math.hypot((position[0]-target.approach[0])*16,(position[1]-target.approach[1])*9);
  }

  /** Opening a dialog manually consumes all nearby entries, too. */
  suppress(position, targets) {
    for (const target of targets) if (this.distance(position,target) <= this.releaseRadius) this.occupied.add(target.id);
  }

  poll(position, targets, eligible = () => true) {
    const entries = [];
    for (const target of targets) {
      const distance = this.distance(position,target);
      if (distance > this.releaseRadius) this.occupied.delete(target.id);
      else if (distance <= this.radius && !this.occupied.has(target.id)) {
        this.occupied.add(target.id);
        if (eligible(target)) entries.push({target,distance});
      }
    }
    entries.sort((a,b)=>a.distance-b.distance);
    // Consume adjacent zones together: closing one interaction cannot open another.
    if (entries.length) this.suppress(position,targets);
    return entries[0]?.target || null;
  }
}
