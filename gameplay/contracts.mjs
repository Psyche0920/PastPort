/** Shared preparation contracts; independent of the frontend and the assembler. */
import {contentHash} from '../src/pastport/player/validation.mjs';

export class StoryPackageError extends Error {
  constructor(code, message) { super(message); this.name='StoryPackageError'; this.code=code; }
}

/** Pin reviewed museum data without importing the previous story or changing the review store. */
export function museumSnapshot(presentation) {
  const value=Object.fromEntries(['objects','tourId','shots','panoramaHashes','scenes','walkArea','sourceNotes','runtimeCapabilities'].map(key=>[key,presentation[key]]));
  if(presentation.spatialContext)value.spatialContext=structuredClone(presentation.spatialContext);
  return value;
}

export const museumSnapshotHash=async museum=>contentHash({snapshot:JSON.stringify(museumSnapshot(museum))});
