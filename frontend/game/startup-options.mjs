/** Device preferences are UI-only and never change story/save authority. */
export const AUTO_LOD_KEY = 'pastport:player:auto-lod:v1';
export function readAutoLod(storage, presentation = {}) {
  try {
    const value = storage?.getItem(AUTO_LOD_KEY);
    if (value === 'on' || value === 'off') return value === 'on';
  } catch { /* Storage denial must not prevent play. */ }
  return presentation.startupPreparation === 'lod';
}
export function saveAutoLod(storage, enabled) {
  try { storage?.setItem(AUTO_LOD_KEY, enabled ? 'on' : 'off'); } catch { /* UI remains usable. */ }
}
