import {DisplayLexicon} from '../player/game-display-locale.mjs';
import catalog from '../player/game-display-locales.json' with {type:'json'};
const lexicon=new DisplayLexicon(catalog);
export const gameDisplayText=(value,locale)=>{
 if(locale==='tr'&&value==='Inspect sources in the available scenes, sort clues, and decide what to deliver.')return 'Sahnelerdeki kaynakları inceleyin, ipuçlarını düzenleyin ve ne sunacağınıza karar verin.';
 return lexicon.translate(value,locale);
};
