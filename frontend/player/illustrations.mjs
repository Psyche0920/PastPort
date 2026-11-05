// Small interpretive illustrations for the source folders, not architectural surveys.
const arch = (x,y) => `M${x} ${y}v-8q5-12 10 0v8z`;
const dome = (x,y,w) => `M${x} ${y}q${w/2} ${-w} ${w} 0z`;
const motifs = {
  school:'M20 56V29h50v27M18 29l26-13 28 13M24 35h42'+arch(31,55)+arch(51,55),
  court:'M18 56V33h16v23M34 56V28h24v28M58 56V33h15v23'+dome(35,28,22)+arch(41,56),
  terrace:'M16 56h63l-5-10H21zM24 46V29h45v17M24 38h45M29 29l17-12 19 12'+arch(40,55),
  tomb:'M22 56V36l11-9h26l11 9v20z'+dome(32,27,28)+arch(42,56)+'M77 52V35m-4 7 4-11 5 11',
  orhan:'M19 56V37h20v19M39 56V31h22v25M61 56V40h15v16'+dome(20,37,17)+dome(39,31,22)+arch(45,56),
  mosque:'M24 56V38h41v18'+dome(26,38,36)+arch(39,56)+'M71 56V21l4-9 4 9v35m-11-23h14',
  courtyard:'M17 56h61V45H17zM23 45V32h49v13'+dome(36,32,24)+arch(21,56)+arch(43,56)+arch(64,56),
  spire:'M28 56V39h39v17'+dome(31,39,32)+arch(42,56)+'M16 56V25l4-12 4 12v31M72 56V25l4-12 4 12v31',
  house:'M20 56V36h54v20M15 36l32-17 31 17M24 41h46m-38 0v14m28-14v14m-14-14v14',
  fountain:'M18 55q26 10 57 0l-5-6H23zM40 49V34h14v15M32 35q13 8 30 0M44 31q2-18 9-14m-5 12q-5-10-12-8',
  lodge:'M24 56V34h44v22M19 34l27-17 28 17'+arch(40,56)+'M16 54v-9m62 9V37m-6 5 6-12 6 12',
  market:'M15 56V35h64v21M12 36l9-12h54l8 12zM20 36l8-12m9 12 4-12m9 12V24m11 12-3-12m14 12-7-12'+arch(25,56)+arch(43,56)+arch(62,56),
  gate:'M18 56V32h16v24m25 0V32h16v24M34 56V36q13-24 25 0v20'+arch(42,56)+'M18 32V25h5v4h6v-4h5v7m25 0v-7h5v4h6v-4h5v7',
  mausoleum:'M23 56V39l23-23 23 23v17zM23 39h46'+arch(41,56)+'M32 42v11m29-11v11',
  ulucami:'M23 56V40h49v16'+dome(23,40,16)+dome(39,40,16)+dome(55,40,17)+arch(42,56)+'M14 56V24l4-9 4 9v32m52 0V24l4-9 4 9v32',
  heilbronn:'M15 56V30h64v26M15 37h64m-55 6h9v7h-9zM44 43h9v7h-9zM64 43h9v7h-9zM23 26h48M40 21v-7l-8 6h12m-4-6v10m10-6q4-8 8-3 2 3-8 9h10',
};
export function illustration(name,index) {
  const sky=['#d87d5d','#80a69d','#cca45e','#96aaa1'][index%4];
  return `<svg viewBox="0 0 94 70" aria-hidden="true" style="--drift:${-index*.55}s">
    <rect width="94" height="70" fill="${sky}"/>
    <circle cx="72" cy="18" r="10" fill="#f6db93"/>
    <path d="M0 53l19-23 18 16 17-14 40 18v20H0z" fill="#365b55" opacity=".52"/>
    <path class="drift" d="M7 19h23q8-6-6-6-8-6-14 2H4" fill="none" stroke="#fff0bd" stroke-width="2"/>
    <path d="${motifs[name]}" fill="#f0cb90" fill-rule="evenodd" stroke="#51392e" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M0 63q20-9 42-3t52 0v10H0z" fill="#324f44"/>
    <path d="M4 65q12-6 24-2m30 2q15-7 29-5" fill="none" stroke="#d2ad6b" opacity=".7"/>
  </svg>`;
}
