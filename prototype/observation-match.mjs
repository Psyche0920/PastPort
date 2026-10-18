/** A shuffled location-matching puzzle; checking never mutates story evidence. */
export class ObservationMatch {
  constructor(spots, random = Math.random) {
    if (!Array.isArray(spots) || spots.length < 2 || spots.length > 26 ||
        new Set(spots.map(spot => spot.id)).size !== spots.length ||
        spots.some(spot => typeof spot.id !== 'string' || !spot.id ||
          !Number.isFinite(spot.x) || !Number.isFinite(spot.y) ||
          spot.x < 0 || spot.x > 100 || spot.y < 0 || spot.y > 100)) {
      throw new Error('观察题需要不同且有效的照片位置');
    }
    this.options = spots.map((spot, index) => Object.freeze({...spot, number:index+1}));
    const ordered = spots.map((_, index) => index);
    let permutation;
    for (let attempt = 0; attempt < 32; attempt++) {
      permutation = [...ordered];
      for (let i = permutation.length-1; i > 0; i--) {
        const sample = random();
        if (!Number.isFinite(sample) || sample < 0 || sample >= 1) throw new Error('Invalid shuffle input');
        const j = Math.floor(sample*(i+1));
        [permutation[i], permutation[j]] = [permutation[j], permutation[i]];
      }
      if (permutation.every((value, index) => value !== index)) break;
    }
    // Guarantee shuffled correspondence even with an unlucky/deterministic RNG.
    if (!permutation.every((value, index) => value !== index)) permutation = [...ordered.slice(1),ordered[0]];
    this.markers = permutation.map((index, label) => Object.freeze({label:String.fromCharCode(65+label),
      spotId:spots[index].id, x:spots[index].x, y:spots[index].y}));
    this.assignments = new Map();
  }

  assign(optionId, markerLabel) {
    if (!this.options.some(option => option.id === optionId) || !this.markers.some(marker => marker.label === markerLabel)) throw new Error('未知的配对选项或照片位置');
    for (const [id, assigned] of this.assignments) if (assigned === markerLabel) this.assignments.delete(id);
    this.assignments.set(optionId,markerLabel);
  }

  check() {
    const correct = this.options.filter(option => this.markers.find(marker => marker.label === this.assignments.get(option.id))?.spotId === option.id).length;
    return Object.freeze({complete:correct === this.options.length, correct, total:this.options.length,
      missing:this.options.length-this.assignments.size});
  }
}
