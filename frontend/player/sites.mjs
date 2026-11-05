const response = await fetch('/sites.json');
if (!response.ok) throw new Error('Map site catalog unavailable');
export const sites = await response.json();
