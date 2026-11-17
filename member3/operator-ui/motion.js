// Visual effects follow validated gateway snapshots. No job logic lives here.
const motionReduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function workshopEffect(kind,index){
 if(motionReduced())return;
 const floor=document.querySelector('.floor');
 const effect=document.createElement('div');
 effect.className='workshop-effect '+kind;
 effect.setAttribute('aria-hidden','true');
 if(kind==='toy-flight')effect.innerHTML=toyArt(index);
 else if(kind==='quality-pass')effect.innerHTML='<span>✓</span><i>✦</i><b>✧</b>';
 else if(kind==='quality-fail')effect.innerHTML='<span>↺</span><small>needs a little care</small>';
 else effect.innerHTML='<i></i><i></i><i></i><span>pop!</span>';
 floor.append(effect);
 setTimeout(()=>effect.remove(),1600);
}
function workshopCelebrate(){
 if(motionReduced())return;
 const floor=document.querySelector('.floor');
 const colors=['#ffdc70','#f4afa2','#a9cfdf','#b5d68c'];
 for(let i=0;i<24;i++){
  const piece=document.createElement('i');piece.className='confetti';
  piece.style.setProperty('--x',(4+(i*17)%93)+'%');
  piece.style.setProperty('--delay',(i%6)*.08+'s');
  piece.style.setProperty('--twist',(i%2?1:-1)*360+'deg');
  piece.style.background=colors[i%4];floor.append(piece);
  setTimeout(()=>piece.remove(),2800);
 }
}
function clearWorkshopEffects(){document.querySelectorAll('.workshop-effect,.confetti').forEach(node=>node.remove());}
