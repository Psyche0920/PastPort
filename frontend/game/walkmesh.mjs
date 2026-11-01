/** Screen-independent walkability, path finding and character locomotion. */
export class WalkMesh {
  constructor(boundary, obstacles = [], step = 2) {
    this.boundary = boundary;
    this.obstacles = obstacles;
    this.step = step;
  }

  static inside(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const a = polygon[i], b = polygon[j];
      if ((a[1] > point[1]) !== (b[1] > point[1]) &&
          point[0] < (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  }

  allows(point) {
    return WalkMesh.inside(point, this.boundary) && !this.obstacles.some(polygon => WalkMesh.inside(point, polygon));
  }

  clear(from, to) {
    const count = Math.ceil(Math.hypot(to[0] - from[0], to[1] - from[1]) / .4);
    for (let i = 0; i <= count; i++) {
      const ratio = count ? i / count : 0;
      if (!this.allows([from[0] + (to[0] - from[0]) * ratio, from[1] + (to[1] - from[1]) * ratio])) return false;
    }
    return true;
  }

  /** Reject unreachable targets rather than teleporting or crossing obstacles. */
  path(from, to) {
    if (!this.allows(from) || !this.allows(to)) return [];
    if (this.clear(from, to)) return [to];
    const distance = (a, b) => Math.hypot((a[0] - b[0]) * 16, (a[1] - b[1]) * 9);
    const key = p => p.join(',');
    const nearest = point => {
      let result = null, best = Infinity;
      for (let x = this.step; x < 100; x += this.step) for (let y = this.step; y < 100; y += this.step) {
        const candidate = [x, y], score = distance(point, candidate);
        if (score < best && this.allows(candidate) && this.clear(point, candidate)) { result = candidate; best = score; }
      }
      return result;
    };
    const start = nearest(from), goal = nearest(to);
    if (!start || !goal) return [];
    const frontier = [{point: start, cost: 0, rank: distance(start, goal)}];
    const costs = new Map([[key(start), 0]]), parents = new Map();
    while (frontier.length) {
      frontier.sort((a, b) => a.rank - b.rank);
      const current = frontier.shift();
      if (current.cost > costs.get(key(current.point))) continue;
      if (key(current.point) === key(goal)) {
        const route = [to, goal];
        let cursor = goal;
        while (parents.has(key(cursor))) { cursor = parents.get(key(cursor)); route.push(cursor); }
        route.reverse();
        const simplified = [];
        let origin = from;
        while (route.length) {
          let end = route.length - 1;
          while (end > 0 && !this.clear(origin, route[end])) end--;
          origin = route[end]; simplified.push(origin); route.splice(0, end + 1);
        }
        return simplified;
      }
      for (const dx of [-this.step, 0, this.step]) for (const dy of [-this.step, 0, this.step]) {
        if (!dx && !dy) continue;
        const next = [current.point[0] + dx, current.point[1] + dy];
        if (!this.clear(current.point, next)) continue;
        const cost = current.cost + distance(current.point, next), id = key(next);
        if (cost >= (costs.get(id) ?? Infinity)) continue;
        costs.set(id, cost); parents.set(id, current.point);
        frontier.push({point: next, cost, rank: cost + distance(next, goal)});
      }
    }
    return [];
  }
}

export class Walker {
  constructor(mesh, position, speed = 230) {
    this.mesh = mesh;
    this.position = [...position];
    this.speed = speed;
    this.route = [];
    this.facing = 1;
    this.moving = false;
  }

  goTo(point) {
    this.route = this.mesh.path(this.position, point);
    return this.route.length > 0;
  }

  stop() { this.route = []; this.moving = false; }

  tick(seconds, direction = [0, 0]) {
    this.moving = false;
    const dt = Math.min(seconds, .05);
    if (direction[0] || direction[1]) {
      this.route = [];
      const length = Math.hypot(...direction);
      const dx = direction[0] / length * this.speed * dt / 16;
      const dy = direction[1] / length * this.speed * dt / 9;
      for (const [axis, offset] of [[0,dx],[1,dy]]) {
        const point = [...this.position]; point[axis] += offset;
        if (this.mesh.clear(this.position, point)) { this.moving ||= Math.hypot(point[0] - this.position[0], point[1] - this.position[1]) > .001; this.position = point; }
      }
      if (dx) this.facing = Math.sign(dx);
      return;
    }
    let budget = this.speed * dt;
    while (this.route.length && budget > 0) {
      const target = this.route[0], dx = (target[0] - this.position[0]) * 16, dy = (target[1] - this.position[1]) * 9;
      const length = Math.hypot(dx, dy);
      if (dx) this.facing = Math.sign(dx);
      if (length <= budget) { this.position = [...target]; this.route.shift(); budget -= length; }
      else { this.position = [this.position[0] + dx / length * budget / 16, this.position[1] + dy / length * budget / 9]; budget = 0; }
      this.moving = length > .001;
    }
  }
}
